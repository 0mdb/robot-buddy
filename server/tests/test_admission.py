"""Tests for admission control and overload behavior."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.admission import PlanAdmissionGate
from app.llm.schemas import ModelPlan
from app.main import app
from app.tts.orpheus import TTSBusyError


class _FakeOllama:
    async def generate_plan(self, _state):
        await asyncio.sleep(0.2)
        return ModelPlan(actions=[{"action": "say", "text": "hello"}], ttl_ms=1000)


def _world_state(seq: int) -> dict:
    return {
        "robot_id": "robot-1",
        "seq": seq,
        "monotonic_ts_ms": 1000 + seq,
        "mode": "IDLE",
        "battery_mv": 8000,
        "range_mm": 1000,
        "trigger": "heartbeat",
    }


@pytest.mark.asyncio
async def test_plan_second_concurrent_request_gets_429():
    app.state.llm = _FakeOllama()
    app.state.plan_gate = PlanAdmissionGate(max_inflight=1)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = asyncio.create_task(client.post("/plan", json=_world_state(1)))
        await asyncio.sleep(0.02)
        second = await client.post("/plan", json=_world_state(2))
        first_resp = await first

    statuses = sorted([first_resp.status_code, second.status_code])
    assert statuses == [200, 429]
    if second.status_code == 429:
        assert second.json()["error"] == "planner_busy"


@pytest.mark.asyncio
async def test_tts_busy_no_fallback_returns_503(monkeypatch):
    class _BusyTTS:
        def debug_snapshot(self) -> dict:
            return {"loaded": False, "init_error": None}

        def stream(self, text: str, emotion: str = "neutral"):
            raise TTSBusyError("tts_busy_no_fallback")

    monkeypatch.setattr("app.routers.tts.get_tts", lambda: _BusyTTS())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/tts", json={"text": "hello", "emotion": "neutral"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "tts_busy_no_fallback"


@pytest.mark.asyncio
async def test_tts_empty_audio_returns_503(monkeypatch):
    class _EmptyTTS:
        def debug_snapshot(self) -> dict:
            return {"loaded": True, "init_error": "espeak_not_available"}

    monkeypatch.setattr("app.routers.tts.get_tts", lambda: _EmptyTTS())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/tts", json={"text": "hello", "emotion": "neutral"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "espeak_not_available"
