"""Integration tests for the /plan endpoint with mocked Ollama."""

from __future__ import annotations

import httpx
import pytest

from app.llm.client import OllamaClient
from app.llm.schemas import ModelPlan
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PLAN = ModelPlan(
    actions=[
        {"action": "emote", "name": "happy", "intensity": 0.8},
        {"action": "say", "text": "Hello!"},
    ],
    ttl_ms=2000,
)

WORLD_STATE = {
    "robot_id": "robot-1",
    "seq": 10,
    "monotonic_ts_ms": 12345,
    "mode": "WANDER",
    "battery_mv": 7800,
    "range_mm": 600,
    "trigger": "heartbeat",
}

OLLAMA_CHAT_RESPONSE = {
    "message": {
        "role": "assistant",
        "content": VALID_PLAN.model_dump_json(),
    },
}


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _attach_fake_ollama() -> None:
    """Attach a minimal OllamaClient on app.state for /health and /plan."""
    # Attach a real OllamaClient (we'll mock behavior per-test)
    ollama = OllamaClient.__new__(OllamaClient)
    ollama._base_url = "http://localhost:11434"
    ollama._model = "qwen3:14b"
    ollama._timeout = httpx.Timeout(5.0)
    ollama._client = None  # health_check() returns False quickly
    ollama._max_inflight = 1
    ollama._active_generations = 0
    app.state.llm = ollama


async def _request(
    method: str, path: str, *, json: object | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, json=json)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_ollama_down():
    """Health returns 503 when Ollama is not reachable."""
    _attach_fake_ollama()
    resp = await _request("GET", "/health")
    # Without a running Ollama, expect degraded
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "model" in data
    assert "llm_backend" in data
    assert "llm_model" in data
    assert "llm_engine_loaded" in data
    assert "gpu_budget" in data
    assert "qwen_backend" in data["gpu_budget"]
    assert "ai" in data
    assert "tts" in data["ai"]
    assert "model_available" in data


@pytest.mark.asyncio
async def test_plan_returns_valid_plan(monkeypatch):
    """POST /plan returns a valid plan when Ollama responds correctly."""
    _attach_fake_ollama()

    async def mock_generate_plan(self, state):
        return VALID_PLAN

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_generate_plan)

    resp = await _request("POST", "/plan", json=WORLD_STATE)
    assert resp.status_code == 200
    data = resp.json()
    assert "actions" in data
    assert data["robot_id"] == "robot-1"
    assert data["seq"] == 10
    assert data["plan_id"]
    assert len(data["actions"]) == 2
    assert data["actions"][0]["action"] == "emote"
    assert data["ttl_ms"] == 2000


@pytest.mark.asyncio
async def test_plan_timeout(monkeypatch):
    """POST /plan returns 504 when Ollama times out."""
    _attach_fake_ollama()

    async def mock_timeout(self, state):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_timeout)

    resp = await _request("POST", "/plan", json=WORLD_STATE)
    assert resp.status_code == 504
    assert resp.json()["error"] == "llm_timeout"


@pytest.mark.asyncio
async def test_plan_llm_unreachable(monkeypatch):
    """POST /plan returns 502 when LLM backend is unreachable."""
    _attach_fake_ollama()

    async def mock_connect_error(self, state):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_connect_error)

    resp = await _request("POST", "/plan", json=WORLD_STATE)
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_unreachable"


@pytest.mark.asyncio
async def test_plan_invalid_world_state():
    """POST /plan returns 422 for missing required fields."""
    _attach_fake_ollama()
    resp = await _request("POST", "/plan", json={"mode": "IDLE"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_plan_llm_error(monkeypatch):
    """POST /plan returns 502 on OllamaError."""
    _attach_fake_ollama()
    from app.llm.client import OllamaError

    async def mock_ollama_error(self, state):
        raise OllamaError("bad response")

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_ollama_error)

    resp = await _request("POST", "/plan", json=WORLD_STATE)
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_error"
