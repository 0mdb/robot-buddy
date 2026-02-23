"""Tests for supervisor_v2 API layer (http_server, ws_hub)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from supervisor_v2.api.http_server import create_app
from supervisor_v2.api.param_registry import (
    ParamRegistry,
    ParamDef,
    create_default_registry,
)
from supervisor_v2.api.ws_hub import WsHub
from supervisor_v2.core.state import Mode, RobotState, WorldState, DesiredTwist


# ── Fixtures ─────────────────────────────────────────────────────


class FakeTick:
    """Minimal TickLoop stand-in for API tests."""

    def __init__(self):
        self.robot = RobotState()
        self.world = WorldState()
        self._reflex = None
        self._face = None
        self._mode_requests: list[str] = []
        self._clear_calls = 0

    def request_mode(self, target: str) -> tuple[bool, str]:
        self._mode_requests.append(target)
        return True, "ok"

    def clear_error(self) -> tuple[bool, str]:
        self._clear_calls += 1
        return True, "ok"

    def set_teleop_twist(self, v: int, w: int) -> None:
        self.robot.twist_cmd = DesiredTwist(v_mm_s=v, w_mrad_s=w)

    def debug_devices(self) -> dict:
        return {"reflex": None, "face": None, "workers": {}}

    def debug_planner(self) -> dict:
        return {"scheduler": {}, "event_bus": {}, "speech_policy": {}}


class FakeWorkers:
    """Minimal WorkerManager stand-in."""

    def __init__(self):
        self._sent: list[tuple[str, str, dict]] = []
        self._alive: dict[str, bool] = {}

    def worker_alive(self, name: str) -> bool:
        return self._alive.get(name, False)

    async def send_to(
        self, name: str, msg_type: str, payload: dict | None = None
    ) -> bool:
        self._sent.append((name, msg_type, payload or {}))
        return True

    def worker_snapshot(self) -> dict:
        return {
            "vision": {"alive": False, "restart_count": 0, "last_seq": 0, "pid": None}
        }


@pytest.fixture
def api_deps():
    tick = FakeTick()
    registry = create_default_registry()
    ws_hub = WsHub()
    workers = FakeWorkers()
    return tick, registry, ws_hub, workers


@pytest.fixture
def client(api_deps):
    tick, registry, ws_hub, workers = api_deps
    app = create_app(tick, registry, ws_hub, workers)
    return TestClient(app), tick, registry, ws_hub, workers


# ── GET /status ──────────────────────────────────────────────────


class TestStatus:
    def test_returns_combined_state(self, client):
        tc, tick, *_ = client
        tick.robot.battery_mv = 7400
        tick.world.planner_connected = True
        resp = tc.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["battery_mv"] == 7400
        assert data["planner_connected"] is True

    def test_includes_mode(self, client):
        tc, tick, *_ = client
        tick.robot.mode = Mode.IDLE
        resp = tc.get("/status")
        assert resp.json()["mode"] == "IDLE"


# ── POST /actions ────────────────────────────────────────────────


class TestActions:
    def test_set_mode(self, client):
        tc, tick, *_ = client
        resp = tc.post("/actions", json={"action": "set_mode", "mode": "TELEOP"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert tick._mode_requests == ["TELEOP"]

    def test_set_mode_unknown(self, client):
        tc, tick, *_ = client
        resp = tc.post("/actions", json={"action": "set_mode", "mode": "FLYING"})
        assert resp.status_code == 400

    def test_clear_e_stop(self, client):
        tc, tick, *_ = client
        resp = tc.post("/actions", json={"action": "clear_e_stop"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert tick._clear_calls == 1

    def test_unknown_action(self, client):
        tc, tick, *_ = client
        resp = tc.post("/actions", json={"action": "dance"})
        assert resp.status_code == 400


# ── GET /params + POST /params ───────────────────────────────────


class TestParams:
    def test_get_params(self, client):
        tc, _, registry, *_ = client
        resp = tc.get("/params")
        assert resp.status_code == 200
        params = resp.json()
        assert isinstance(params, list)
        assert len(params) > 0
        names = [p["name"] for p in params]
        assert "telemetry_hz" in names

    def test_set_param(self, client):
        tc, _, registry, *_ = client
        resp = tc.post("/params", json={"items": {"telemetry_hz": 10}})
        assert resp.status_code == 200
        assert registry.get_value("telemetry_hz") == 10

    def test_set_param_invalid(self, client):
        tc, _, registry, *_ = client
        # telemetry_hz max is 50
        resp = tc.post("/params", json={"items": {"telemetry_hz": 999}})
        assert resp.status_code == 422

    def test_set_param_empty(self, client):
        tc, *_ = client
        resp = tc.post("/params", json={"items": {}})
        assert resp.status_code == 400


# ── GET /debug/* ─────────────────────────────────────────────────


class TestDebug:
    def test_debug_devices(self, client):
        tc, *_ = client
        resp = tc.get("/debug/devices")
        assert resp.status_code == 200

    def test_debug_planner(self, client):
        tc, *_ = client
        resp = tc.get("/debug/planner")
        assert resp.status_code == 200

    def test_debug_workers(self, client):
        tc, *_ = client
        resp = tc.get("/debug/workers")
        assert resp.status_code == 200
        data = resp.json()
        assert "vision" in data

    def test_debug_clocks(self, client):
        tc, *_ = client
        resp = tc.get("/debug/clocks")
        assert resp.status_code == 200
        data = resp.json()
        assert "reflex" in data
        assert "face" in data
        assert "state" in data["reflex"]


# ── GET /video ───────────────────────────────────────────────────


class TestVideo:
    def test_video_unavailable_without_vision(self, client):
        tc, _, _, _, workers = client
        workers._alive["vision"] = False
        resp = tc.get("/video")
        assert resp.status_code == 503


# ── WsHub ────────────────────────────────────────────────────────


class TestWsHub:
    def test_add_remove(self):
        hub = WsHub()
        ws = MagicMock()
        hub.add(ws)
        assert ws in hub._clients
        hub.remove(ws)
        assert ws not in hub._clients

    def test_broadcast_empty(self):
        hub = WsHub()
        # Should not raise
        hub.broadcast_telemetry({"mode": "IDLE"})

    def test_broadcast_schema(self):
        hub = WsHub()
        ws = MagicMock()
        # Simulate successful send
        future = asyncio.Future()
        future.set_result(None)
        ws.send_text = MagicMock(return_value=future)
        hub.add(ws)

        with patch("supervisor_v2.api.ws_hub.asyncio.ensure_future") as mock_ef:
            hub.broadcast_telemetry({"mode": "IDLE"})
            assert mock_ef.called
            # Check the envelope JSON
            # ensure_future receives a coroutine from ws.send_text(envelope)
            # The send_text was called with the serialized envelope
            ws.send_text.assert_called_once()
            envelope_str = ws.send_text.call_args[0][0]
            envelope = json.loads(envelope_str)
            assert envelope["schema"] == "supervisor_ws_v2"
            assert envelope["type"] == "telemetry"
            assert envelope["payload"]["mode"] == "IDLE"


# ── ParamRegistry ────────────────────────────────────────────────


class TestParamRegistry:
    def test_register_and_get(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="test", type="int", min=0, max=10, default=5))
        assert reg.get_value("test") == 5

    def test_set_value(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="test", type="int", min=0, max=10, default=5))
        ok, _ = reg.set("test", 7)
        assert ok
        assert reg.get_value("test") == 7

    def test_set_out_of_range(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="test", type="int", min=0, max=10, default=5))
        ok, reason = reg.set("test", 99)
        assert not ok

    def test_bulk_set_transactional(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="a", type="int", min=0, max=10, default=5))
        reg.register(ParamDef(name="b", type="int", min=0, max=10, default=5))
        # One valid, one invalid — both should fail
        results = reg.bulk_set({"a": 7, "b": 99})
        assert not results["b"][0]
        # "a" should NOT have been updated (transactional)
        assert reg.get_value("a") == 5

    def test_on_change_callback(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="test", type="int", min=0, max=10, default=5))
        changed = []
        reg.on_change(lambda name, val: changed.append((name, val)))
        reg.set("test", 8)
        assert changed == [("test", 8)]

    def test_default_registry_has_vision_params(self):
        reg = create_default_registry()
        assert reg.get("vision.floor_hsv_h_low") is not None
        assert reg.get("vision.ball_hsv_h_low") is not None
        assert reg.get("reflex.Kp") is not None
