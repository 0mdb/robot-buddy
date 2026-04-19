"""Face MCU benchmark adapter — Stage 4 perf scenarios.

Polls face heartbeat perf data from the supervisor debug surface,
accumulates per-window samples, and produces legacy avg/max fields
(backward-compatible with v1 artifacts) plus new p50/p95 percentiles.

Scenarios (unchanged from baseline for continuity):
    idle              — neutral mood, no animation
    listening_proxy   — LISTENING conv state (border pulse)
    thinking_border   — THINKING conv state (heavy border animation)
    talking_energy    — talking + energy modulation
    rage_effects      — ANGRY mood + effects pipeline
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from supervisor.api.mcu_benchmark import (
    ScenarioConfig,
    ScenarioResult,
    TargetAdapter,
    compute_stats,
)

log = logging.getLogger(__name__)

# Face perf fields from heartbeat snapshot → artifact field names
_PERF_FIELDS = [
    "frame_us_avg",
    "frame_us_max",
    "render_us_avg",
    "render_us_max",
    "eyes_us_avg",
    "mouth_us_avg",
    "border_us_avg",
    "effects_us_avg",
    "overlay_us_avg",
    "dirty_px_avg",
    "spi_bytes_per_s",
    "cmd_rx_to_apply_us_avg",
]

# Fields for which we compute p50/p95 from per-window samples
_PERCENTILE_FIELDS = [
    "frame_us",
    "render_us",
    "border_us",
    "mouth_us",
]

# Scenario definitions — mood/conv-state/talking setup per scenario
_SCENARIO_SETUP: dict[str, dict[str, Any]] = {
    "idle": {
        "emotion": "neutral",
        "intensity": 1.0,
        "conv_state": None,
        "talking": False,
        "energy": 0,
    },
    "listening_proxy": {
        "emotion": "neutral",
        "intensity": 1.0,
        "conv_state": "LISTENING",
        "talking": False,
        "energy": 0,
    },
    "thinking_border": {
        "emotion": "neutral",
        "intensity": 1.0,
        "conv_state": "THINKING",
        "talking": False,
        "energy": 0,
    },
    "talking_energy": {
        "emotion": "happy",
        "intensity": 1.0,
        "conv_state": "SPEAKING",
        "talking": True,
        "energy": 180,
    },
    "rage_effects": {
        "emotion": "angry",
        "intensity": 1.0,
        "conv_state": None,
        "talking": False,
        "energy": 0,
    },
}

# Map conv state names to the integer values used by WS face_set_conv_state
_CONV_STATE_IDS: dict[str, int] = {
    "IDLE": 0,
    "ATTENTION": 1,
    "LISTENING": 2,
    "PTT": 3,
    "THINKING": 4,
    "SPEAKING": 5,
    "ERROR": 6,
    "DONE": 7,
}


@dataclass(slots=True)
class _Accumulator:
    """Per-scenario sample accumulator."""

    # Weighted-average accumulators (weight = window_frames)
    frame_us_avg_sum: float = 0.0
    frame_us_max_vals: list[int] = field(default_factory=list)
    render_us_avg_sum: float = 0.0
    render_us_max_vals: list[int] = field(default_factory=list)
    eyes_us_avg_sum: float = 0.0
    mouth_us_avg_sum: float = 0.0
    border_us_avg_sum: float = 0.0
    effects_us_avg_sum: float = 0.0
    overlay_us_avg_sum: float = 0.0
    dirty_px_avg_sum: float = 0.0
    spi_bytes_sum: float = 0.0
    cmd_rx_us_avg_sum: float = 0.0
    total_weight: float = 0.0
    sample_count: int = 0

    # Per-window raw values for percentile computation
    frame_us_samples: list[int] = field(default_factory=list)
    render_us_samples: list[int] = field(default_factory=list)
    border_us_samples: list[int] = field(default_factory=list)
    mouth_us_samples: list[int] = field(default_factory=list)

    def reset(self) -> None:
        self.frame_us_avg_sum = 0.0
        self.frame_us_max_vals.clear()
        self.render_us_avg_sum = 0.0
        self.render_us_max_vals.clear()
        self.eyes_us_avg_sum = 0.0
        self.mouth_us_avg_sum = 0.0
        self.border_us_avg_sum = 0.0
        self.effects_us_avg_sum = 0.0
        self.overlay_us_avg_sum = 0.0
        self.dirty_px_avg_sum = 0.0
        self.spi_bytes_sum = 0.0
        self.cmd_rx_us_avg_sum = 0.0
        self.total_weight = 0.0
        self.sample_count = 0
        self.frame_us_samples.clear()
        self.render_us_samples.clear()
        self.border_us_samples.clear()
        self.mouth_us_samples.clear()


class FaceAdapter(TargetAdapter):
    """Adapter for face MCU benchmark scenarios."""

    def __init__(self, base_url: str, *, target_samples: int = 100) -> None:
        self._base_url = base_url
        self._target_samples = target_samples
        self._client: Any = None  # httpx.AsyncClient
        self._acc = _Accumulator()
        self._last_hb_seq: int = -1

    async def prepare(self, base_url: str) -> None:
        import httpx

        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=10.0)
        # Verify face is connected
        resp = await self._client.get(f"{base_url}/debug/devices")
        resp.raise_for_status()
        devices = resp.json()
        face = devices.get("face")
        if not face or not face.get("connected"):
            raise RuntimeError("face MCU not connected")
        log.info("face adapter: MCU connected, ready")

    async def setup_scenario(self, scenario: ScenarioConfig) -> None:
        setup = _SCENARIO_SETUP.get(scenario.name)
        if not setup:
            raise ValueError(f"unknown face scenario: {scenario.name}")

        self._acc.reset()
        self._last_hb_seq = -1

        # Set face state (mood + intensity)
        await self._ws_cmd(
            "face_set_state",
            emotion=setup["emotion"],
            intensity=setup["intensity"],
            gaze_x=0.0,
            gaze_y=0.0,
            brightness=1.0,
        )

        # Set conv state if applicable
        if setup["conv_state"]:
            conv_id = _CONV_STATE_IDS.get(setup["conv_state"], 0)
            await self._ws_cmd("face_set_conv_state", conv_state=conv_id)
        else:
            # Reset to IDLE
            await self._ws_cmd("face_set_conv_state", conv_state=0)

        # Set talking state
        await self._ws_cmd(
            "face_set_talking",
            talking=setup["talking"],
            energy=setup["energy"],
        )

        log.info("face scenario %s: setup complete", scenario.name)

    async def tick(self, now_s: float) -> dict[str, Any] | None:
        """Poll face heartbeat perf. Returns sample dict or None if stale."""
        resp = await self._client.get(f"{self._base_url}/debug/devices")
        resp.raise_for_status()
        devices = resp.json()

        face = devices.get("face", {})
        hb = face.get("last_heartbeat")
        if not hb:
            return None

        perf = hb.get("perf", {})
        seq = hb.get("seq", 0)

        # Deduplicate — only return new heartbeat windows
        if seq == self._last_hb_seq:
            return None
        self._last_hb_seq = seq

        return {
            "window_frames": perf.get("window_frames", 0),
            "frame_us_avg": perf.get("frame_us_avg", 0),
            "frame_us_max": perf.get("frame_us_max", 0),
            "render_us_avg": perf.get("render_us_avg", 0),
            "render_us_max": perf.get("render_us_max", 0),
            "eyes_us_avg": perf.get("eyes_us_avg", 0),
            "mouth_us_avg": perf.get("mouth_us_avg", 0),
            "border_us_avg": perf.get("border_us_avg", 0),
            "effects_us_avg": perf.get("effects_us_avg", 0),
            "overlay_us_avg": perf.get("overlay_us_avg", 0),
            "dirty_px_avg": perf.get("dirty_px_avg", 0),
            "spi_bytes_per_s": perf.get("spi_bytes_per_s", 0),
            "cmd_rx_to_apply_us_avg": perf.get("cmd_rx_to_apply_us_avg", 0),
            "sample_div": perf.get("sample_div", 1),
            "seq": seq,
        }

    async def ingest_sample(
        self, scenario: ScenarioConfig, sample: dict[str, Any]
    ) -> None:
        w = sample["window_frames"]
        a = self._acc

        a.frame_us_avg_sum += sample["frame_us_avg"] * w
        a.frame_us_max_vals.append(sample["frame_us_max"])
        a.render_us_avg_sum += sample["render_us_avg"] * w
        a.render_us_max_vals.append(sample["render_us_max"])
        a.eyes_us_avg_sum += sample["eyes_us_avg"] * w
        a.mouth_us_avg_sum += sample["mouth_us_avg"] * w
        a.border_us_avg_sum += sample["border_us_avg"] * w
        a.effects_us_avg_sum += sample["effects_us_avg"] * w
        a.overlay_us_avg_sum += sample["overlay_us_avg"] * w
        a.dirty_px_avg_sum += sample["dirty_px_avg"] * w
        a.spi_bytes_sum += sample["spi_bytes_per_s"] * w
        a.cmd_rx_us_avg_sum += sample["cmd_rx_to_apply_us_avg"] * w
        a.total_weight += w
        a.sample_count += 1

        # Raw per-window averages for percentile computation
        a.frame_us_samples.append(sample["frame_us_avg"])
        a.render_us_samples.append(sample["render_us_avg"])
        a.border_us_samples.append(sample["border_us_avg"])
        a.mouth_us_samples.append(sample["mouth_us_avg"])

    def compute_result(self, scenario: ScenarioConfig) -> ScenarioResult:
        a = self._acc
        tw = a.total_weight if a.total_weight > 0 else 1.0

        # Legacy fields (weighted averages + max)
        metrics: dict[str, Any] = {
            "frames": int(a.total_weight),
            "frame_us_avg": round(a.frame_us_avg_sum / tw),
            "frame_us_max": max(a.frame_us_max_vals) if a.frame_us_max_vals else 0,
            "render_us_avg": round(a.render_us_avg_sum / tw),
            "render_us_max": max(a.render_us_max_vals) if a.render_us_max_vals else 0,
            "eyes_us_avg": round(a.eyes_us_avg_sum / tw),
            "mouth_us_avg": round(a.mouth_us_avg_sum / tw),
            "border_us_avg": round(a.border_us_avg_sum / tw),
            "effects_us_avg": round(a.effects_us_avg_sum / tw),
            "overlay_us_avg": round(a.overlay_us_avg_sum / tw),
            "dirty_px_avg": round(a.dirty_px_avg_sum / tw),
            "spi_bytes_per_s": round(a.spi_bytes_sum / tw),
            "cmd_rx_to_apply_us_avg": round(a.cmd_rx_us_avg_sum / tw),
        }

        # FPS estimate from weighted-average frame time
        frame_avg = metrics["frame_us_avg"]
        metrics["fps_est"] = round(1_000_000.0 / frame_avg, 2) if frame_avg > 0 else 0.0

        # New p50/p95 fields
        for field_name, samples in [
            ("frame_us", a.frame_us_samples),
            ("render_us", a.render_us_samples),
            ("border_us", a.border_us_samples),
            ("mouth_us", a.mouth_us_samples),
        ]:
            stats = compute_stats(samples)
            metrics[f"{field_name}_p50"] = stats["p50"]
            metrics[f"{field_name}_p95"] = stats["p95"]

        return ScenarioResult(
            name=scenario.name,
            metrics=metrics,
            samples=a.sample_count,
        )

    async def teardown(self) -> None:
        """Reset face to idle state."""
        try:
            await self._ws_cmd(
                "face_set_state",
                emotion="neutral",
                intensity=1.0,
                gaze_x=0.0,
                gaze_y=0.0,
                brightness=1.0,
            )
            await self._ws_cmd("face_set_conv_state", conv_state=0)
            await self._ws_cmd("face_set_talking", talking=False, energy=0)
        except Exception as e:
            log.warning("face teardown error: %s", e)
        finally:
            if self._client:
                await self._client.aclose()
                self._client = None

    async def _ws_cmd(self, msg_type: str, **kwargs: Any) -> None:
        """Send a command via the supervisor WS endpoint.

        Uses HTTP POST to /actions for mode changes, or sends a JSON
        command through a temporary WebSocket connection. For simplicity,
        we use the HTTP debug surface to send face commands via a small
        helper endpoint.

        Actually — the existing WS commands use the /ws endpoint which
        requires a persistent connection. For benchmark CLI use, we open
        a short-lived WS connection per command batch.
        """
        import websockets

        ws_url = self._base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        msg = {"type": msg_type, **kwargs}
        async with websockets.connect(f"{ws_url}/ws", open_timeout=5.0) as ws:
            await ws.send(__import__("json").dumps(msg))
            # Commands are fire-and-forget on /ws, no response expected
            # Small delay to ensure command is processed
            await asyncio.sleep(0.05)


def create_face_adapter(
    *,
    base_url: str,
    target_samples: int = 100,
) -> tuple[FaceAdapter, list[ScenarioConfig]]:
    """Factory — returns adapter + scenario list for Stage 4 face benchmark."""
    adapter = FaceAdapter(base_url, target_samples=target_samples)
    scenarios = [
        ScenarioConfig(name=name, target_samples=target_samples, settle_samples=5)
        for name in _SCENARIO_SETUP
    ]
    return adapter, scenarios
