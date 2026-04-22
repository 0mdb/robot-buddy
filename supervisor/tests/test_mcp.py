"""Tests for the MCP server scaffold (Phase 0).

Covers the tool implementations directly + the /debug/mcp and /ws/mcp
endpoints. The MCP protocol itself (Streamable HTTP) is exercised by the
upstream `mcp` SDK's tests; here we verify the integration contract:

  * get_state returns a sensible subset of tick state
  * calls are recorded to the audit broadcaster
  * /debug/mcp exposes the ring buffer + success rate
  * /ws/mcp streams live entries and sends an initial snapshot
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.core.event_bus import PlannerEventBus
from supervisor.core.state import Mode
from supervisor.mcp import McpAuditBroadcaster
from supervisor.mcp.audit import McpAuditEntry
from supervisor.mcp.tools import (
    LOOK_BALL_ACQUIRE_CONF,
    LOOK_FRAME_STALE_MS,
    get_memory_impl,
    get_state_impl,
    look_impl,
    recent_events_impl,
)
from supervisor.tests.test_api import FakeTick, FakeWorkers


class FakeWorkersWithConsent(FakeWorkers):
    """FakeWorkers + memory_consent surfaced via worker_snapshot()."""

    def __init__(self, memory_consent: bool = False):
        super().__init__()
        self._memory_consent = memory_consent

    def worker_snapshot(self) -> dict:
        snap = super().worker_snapshot()
        snap["personality"] = {"health": {"memory_consent": self._memory_consent}}
        return snap


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def tick() -> FakeTick:
    return FakeTick()


@pytest.fixture
def audit() -> McpAuditBroadcaster:
    return McpAuditBroadcaster()


@pytest.fixture
def app_client():
    tick = FakeTick()
    registry = create_default_registry()
    ws_hub = WsHub()
    workers = FakeWorkers()
    app = create_app(tick, registry, ws_hub, workers)
    # TestClient's context manager drives FastAPI's lifespan, which starts
    # the MCP session manager.
    with TestClient(app) as tc:
        yield tc, tick


# ── get_state tool ───────────────────────────────────────────────


class TestGetStateTool:
    @pytest.mark.asyncio
    async def test_returns_curated_subset(self, tick, audit):
        tick.robot.mode = Mode.IDLE
        tick.robot.battery_mv = 7400
        result = await get_state_impl(tick, audit)
        assert result["mode"] == "IDLE"
        assert result["battery_mv"] == 7400
        # Verify trimming: raw speeds and clock state are not included.
        assert "speed_l" not in result
        assert "reflex_clock" not in result

    @pytest.mark.asyncio
    async def test_records_audit_entry_on_success(self, tick, audit):
        await get_state_impl(tick, audit)
        snap = audit.snapshot()
        assert len(snap) == 1
        assert snap[0]["tool"] == "get_state"
        assert snap[0]["ok"] is True
        assert snap[0]["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_records_audit_entry_on_failure(self, tick, audit):
        # Force tick.robot.to_dict() to raise.
        class Boom:
            def to_dict(self):
                raise RuntimeError("kaboom")

        tick.robot = Boom()
        with pytest.raises(RuntimeError):
            await get_state_impl(tick, audit)
        snap = audit.snapshot()
        assert len(snap) == 1
        assert snap[0]["ok"] is False
        assert "kaboom" in snap[0]["error"]


# ── Audit broadcaster ────────────────────────────────────────────


class TestAuditBroadcaster:
    def test_success_rate_tracks_per_tool(self, audit):
        audit.record(
            McpAuditEntry(
                ts_mono=0.0, tool="get_state", args={}, ok=True, latency_ms=1.0
            )
        )
        audit.record(
            McpAuditEntry(
                ts_mono=0.1, tool="get_state", args={}, ok=False, latency_ms=2.0
            )
        )
        audit.record(
            McpAuditEntry(ts_mono=0.2, tool="look", args={}, ok=True, latency_ms=3.0)
        )
        rates = audit.success_rate()
        assert rates["get_state"]["total"] == 2
        assert rates["get_state"]["rate"] == 0.5
        assert rates["look"]["rate"] == 1.0

    def test_ring_buffer_caps_size(self):
        a = McpAuditBroadcaster(ring_size=3)
        for i in range(5):
            a.record(
                McpAuditEntry(
                    ts_mono=float(i), tool="t", args={}, ok=True, latency_ms=0.0
                )
            )
        snap = a.snapshot()
        assert len(snap) == 3
        assert [e["ts_mono"] for e in snap] == [2.0, 3.0, 4.0]


# ── get_memory tool ──────────────────────────────────────────────


def _write_memory_file(path, entries):
    path.write_text(json.dumps({"version": 1, "entries": entries}))


class TestGetMemoryTool:
    @pytest.mark.asyncio
    async def test_missing_file_returns_empty(self, tmp_path, audit):
        result = await get_memory_impl(tmp_path / "nope.json", None, audit)
        assert result["entries"] == []
        assert result["entry_count"] == 0

    @pytest.mark.asyncio
    async def test_curated_shape_hides_bias_axes(self, tmp_path, audit):
        import time as time_mod

        p = tmp_path / "mem.json"
        _write_memory_file(
            p,
            [
                {
                    "tag": "likes_dinosaurs",
                    "category": "topic",
                    "valence_bias": 0.5,  # must be stripped
                    "arousal_bias": 0.2,
                    "initial_strength": 0.8,
                    "created_ts": time_mod.time() - 3600,
                    "last_reinforced_ts": time_mod.time(),
                    "reinforcement_count": 3,
                    "decay_lambda": 0.0,
                    "source": "llm_extract",
                },
            ],
        )
        result = await get_memory_impl(p, None, audit)
        e = result["entries"][0]
        assert e["tag"] == "likes_dinosaurs"
        assert e["category"] == "topic"
        assert e["strength"] == pytest.approx(0.8, abs=0.01)
        assert e["reinforcement_count"] == 3
        # Verbose internals must not leak through.
        assert "valence_bias" not in e
        assert "decay_lambda" not in e
        assert "source" not in e

    @pytest.mark.asyncio
    async def test_category_filter(self, tmp_path, audit):
        p = tmp_path / "mem.json"
        _write_memory_file(
            p,
            [
                {"tag": "lily", "category": "name", "initial_strength": 1.0},
                {"tag": "dinos", "category": "topic", "initial_strength": 0.8},
                {"tag": "rockets", "category": "topic", "initial_strength": 0.6},
            ],
        )
        result = await get_memory_impl(p, "topic", audit)
        tags = {e["tag"] for e in result["entries"]}
        assert tags == {"dinos", "rockets"}

    @pytest.mark.asyncio
    async def test_invalid_category_raises(self, tmp_path, audit):
        with pytest.raises(ValueError, match="unknown category"):
            await get_memory_impl(tmp_path / "ignored.json", "bogus", audit)
        snap = audit.snapshot()
        assert snap[-1]["tool"] == "get_memory"
        assert snap[-1]["ok"] is False

    @pytest.mark.asyncio
    async def test_sorted_strongest_first(self, tmp_path, audit):
        import time as time_mod

        now = time_mod.time()
        p = tmp_path / "mem.json"
        _write_memory_file(
            p,
            [
                # Faded: high decay_lambda over a long window.
                {
                    "tag": "faded",
                    "category": "topic",
                    "initial_strength": 1.0,
                    "last_reinforced_ts": now - 7 * 86400,
                    "decay_lambda": 1e-5,
                },
                # Fresh: no decay applied.
                {
                    "tag": "fresh",
                    "category": "topic",
                    "initial_strength": 0.5,
                    "last_reinforced_ts": now,
                    "decay_lambda": 1e-5,
                },
            ],
        )
        result = await get_memory_impl(p, None, audit)
        tags = [e["tag"] for e in result["entries"]]
        assert tags[0] == "fresh"


# ── recent_events tool ───────────────────────────────────────────


class _TickWithBus:
    """Minimal fake tick that exposes a real PlannerEventBus for tool tests."""

    def __init__(self):
        self._event_bus = PlannerEventBus()


class TestRecentEventsTool:
    @pytest.mark.asyncio
    async def test_empty_returns_zero(self, audit):
        tick = _TickWithBus()
        result = await recent_events_impl(tick, None, 10, audit)
        assert result["count"] == 0
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_returns_recent_and_respects_n(self, audit):
        tick = _TickWithBus()
        for i in range(12):
            tick._event_bus.emit(
                "face.button.press", {"button_id": i}, t_mono_ms=float(i)
            )
        result = await recent_events_impl(tick, None, 5, audit)
        assert result["count"] == 5
        # Most recent last (matches PlannerEventBus ordering).
        assert result["events"][-1]["payload"]["button_id"] == 11

    @pytest.mark.asyncio
    async def test_pattern_filter_case_insensitive(self, audit):
        tick = _TickWithBus()
        tick._event_bus.emit("face.button.press", {}, t_mono_ms=1.0)
        tick._event_bus.emit("ball.detected", {"conf": 0.9}, t_mono_ms=2.0)
        tick._event_bus.emit("obstacle.detected", {"mm": 400}, t_mono_ms=3.0)
        result = await recent_events_impl(tick, "BALL", 10, audit)
        assert result["count"] == 1
        assert result["events"][0]["type"] == "ball.detected"

    @pytest.mark.asyncio
    async def test_n_clamped_to_max(self, audit):
        tick = _TickWithBus()
        for i in range(80):
            tick._event_bus.emit("x", {"i": i}, t_mono_ms=float(i))
        result = await recent_events_impl(tick, None, 9999, audit)
        # event_bus max_events default is 100; latest(50) inside impl caps;
        # n is clamped to 50.
        assert result["count"] == 50


# ── look tool ─────────────────────────────────────────────────────


def _prime_tick_frame(
    tick: FakeTick,
    *,
    jpeg_b64: str = "ZmFrZS1qcGVnLWJ5dGVz",  # "fake-jpeg-bytes" base64
    age_ms: float = 100.0,
    ball_conf: float = 0.0,
    ball_bearing_deg: float = 0.0,
    frame_seq: int = 42,
) -> None:
    """Seed a FakeTick's world state with plausible vision values.

    age_ms is interpreted via vision_rx_mono_ms: we subtract age from the
    current monotonic clock so WorldState.vision_age_ms returns age_ms.
    Set age_ms<0 to mark no-frame (vision_rx_mono_ms=0).
    """
    import time as _time

    tick.world.latest_jpeg_b64 = jpeg_b64
    tick.world.ball_confidence = ball_conf
    tick.world.ball_bearing_deg = ball_bearing_deg
    tick.world.vision_frame_seq = frame_seq
    tick.world.vision_rx_mono_ms = (
        0.0 if age_ms < 0 else max(0.001, _time.monotonic() * 1000.0 - age_ms)
    )


class TestLookTool:
    @pytest.mark.asyncio
    async def test_consent_on_fresh_frame_returns_image(self, audit):
        tick = FakeTick()
        _prime_tick_frame(tick, ball_conf=0.8, ball_bearing_deg=12.3)
        workers = FakeWorkersWithConsent(memory_consent=True)

        content = await look_impl(tick, workers, hint="look at this", audit=audit)

        assert len(content) == 2
        img, meta = content[0], content[1]
        assert img.type == "image"
        assert img.mimeType == "image/jpeg"
        assert img.data == "ZmFrZS1qcGVnLWJ5dGVz"
        meta_json = json.loads(meta.text)
        assert meta_json["consent"] == "on"
        assert meta_json["ball_detected"] is True  # 0.8 >= threshold
        assert meta_json["ball_bearing_deg"] == 12.3
        assert meta_json["hint"] == "look at this"
        assert "reason" not in meta_json

    @pytest.mark.asyncio
    async def test_consent_off_omits_image(self, audit):
        tick = FakeTick()
        _prime_tick_frame(tick, ball_conf=0.9)
        workers = FakeWorkersWithConsent(memory_consent=False)

        content = await look_impl(tick, workers, hint=None, audit=audit)

        assert len(content) == 1
        assert content[0].type == "text"
        meta = json.loads(content[0].text)
        assert meta["consent"] == "off"
        assert meta["reason"] == "consent_off"
        # Ball detection metadata still flows through — only image is gated.
        assert meta["ball_detected"] is True

    @pytest.mark.asyncio
    async def test_stale_frame_omits_image(self, audit):
        tick = FakeTick()
        _prime_tick_frame(tick, age_ms=LOOK_FRAME_STALE_MS + 500)
        workers = FakeWorkersWithConsent(memory_consent=True)

        content = await look_impl(tick, workers, hint=None, audit=audit)

        assert len(content) == 1
        meta = json.loads(content[0].text)
        assert meta["reason"] == "stale"

    @pytest.mark.asyncio
    async def test_no_frame_omits_image(self, audit):
        tick = FakeTick()
        _prime_tick_frame(tick, jpeg_b64="", age_ms=-1)
        workers = FakeWorkersWithConsent(memory_consent=True)

        content = await look_impl(tick, workers, hint=None, audit=audit)

        assert len(content) == 1
        meta = json.loads(content[0].text)
        assert meta["reason"] == "no_frame"

    @pytest.mark.asyncio
    async def test_ball_threshold_is_acquire_conf(self, audit):
        tick = FakeTick()
        # Just above threshold
        _prime_tick_frame(tick, ball_conf=LOOK_BALL_ACQUIRE_CONF + 0.001)
        workers = FakeWorkersWithConsent(memory_consent=True)
        content = await look_impl(tick, workers, hint=None, audit=audit)
        assert json.loads(content[1].text)["ball_detected"] is True

        # Just below threshold
        _prime_tick_frame(tick, ball_conf=LOOK_BALL_ACQUIRE_CONF - 0.001)
        content = await look_impl(tick, workers, hint=None, audit=audit)
        # When consent on + fresh, content[1] is the text block
        assert json.loads(content[1].text)["ball_detected"] is False

    @pytest.mark.asyncio
    async def test_audit_never_contains_jpeg_bytes(self, audit):
        tick = FakeTick()
        _prime_tick_frame(tick)
        workers = FakeWorkersWithConsent(memory_consent=True)

        await look_impl(tick, workers, hint=None, audit=audit)

        entries = audit.snapshot()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["tool"] == "look"
        assert entry["ok"] is True
        # The base64 we seeded must not appear anywhere in the audit entry.
        for v in entry.values():
            assert "ZmFrZS1qcGVnLWJ5dGVz" not in repr(v)
        assert "image=y" in entry["result_summary"]
        assert "consent=on" in entry["result_summary"]

    @pytest.mark.asyncio
    async def test_worker_snapshot_failure_fails_closed(self, audit):
        class BrokenWorkers(FakeWorkers):
            def worker_snapshot(self) -> dict:
                raise RuntimeError("boom")

        tick = FakeTick()
        _prime_tick_frame(tick)
        content = await look_impl(tick, BrokenWorkers(), hint=None, audit=audit)

        # No image returned because the consent check failed closed.
        assert len(content) == 1
        meta = json.loads(content[0].text)
        assert meta["consent"] == "off"


# ── HTTP + WS endpoints ──────────────────────────────────────────


class TestDebugEndpoint:
    def test_empty_state(self, app_client):
        tc, _ = app_client
        resp = tc.get("/debug/mcp")
        assert resp.status_code == 200
        body = resp.json()
        assert body["recent"] == []
        assert body["success_rate"] == {}


class TestMcpMountExists:
    def test_mcp_route_is_mounted(self, app_client):
        tc, _ = app_client
        # FastMCP's streamable HTTP rejects GET without a session with 421
        # Misdirected Request. We just assert the route is wired (not a
        # 404 falling through to the static catch-all).
        resp = tc.get("/mcp/", follow_redirects=False)
        assert resp.status_code != 404


class TestWsMcp:
    def test_sends_snapshot_on_connect(self, app_client):
        tc, _ = app_client
        with tc.websocket_connect("/ws/mcp") as ws:
            msg = ws.receive_text()
            data = json.loads(msg)
            assert data["type"] == "snapshot"
            assert data["entries"] == []
