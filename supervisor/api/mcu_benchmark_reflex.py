"""Reflex MCU benchmark adapter — minimal metrics now, reusable later.

Uses supervisor-visible telemetry only (no firmware protocol changes).
Measures state update rate, jitter, age, and command-to-state latency
proxy from the debug surface.

Scenarios:
    idle_hold       — no motion, safe default (always available)
    step_response   — 200 mm/s forward step (requires --allow-motion)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from supervisor.api.mcu_benchmark import (
    ScenarioConfig,
    ScenarioResult,
    TargetAdapter,
    compute_stats,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class _ReflexAccumulator:
    """Per-scenario sample accumulator for reflex metrics."""

    # State rate tracking
    last_seq: int = -1
    last_rx_mono_ms: float = 0.0
    state_periods_ms: list[float] = field(default_factory=list)
    state_ages_ms: list[float] = field(default_factory=list)

    # Command-to-state latency proxy
    cmd_to_state_ms: list[float] = field(default_factory=list)

    # Fault tracking
    fault_nonzero_count: int = 0
    total_samples: int = 0

    # Motion scenario: velocity tracking error
    v_target_mm_s: float = 0.0
    v_error_abs: list[float] = field(default_factory=list)

    def reset(self) -> None:
        self.last_seq = -1
        self.last_rx_mono_ms = 0.0
        self.state_periods_ms.clear()
        self.state_ages_ms.clear()
        self.cmd_to_state_ms.clear()
        self.fault_nonzero_count = 0
        self.total_samples = 0
        self.v_target_mm_s = 0.0
        self.v_error_abs.clear()


class ReflexAdapter(TargetAdapter):
    """Adapter for reflex MCU benchmark scenarios."""

    def __init__(
        self,
        base_url: str,
        *,
        target_samples: int = 100,
        allow_motion: bool = False,
    ) -> None:
        self._base_url = base_url
        self._target_samples = target_samples
        self._allow_motion = allow_motion
        self._client: Any = None  # httpx.AsyncClient
        self._acc = _ReflexAccumulator()
        self._scenario_name: str = ""

    async def prepare(self, base_url: str) -> None:
        import httpx

        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=10.0)
        resp = await self._client.get(f"{base_url}/debug/devices")
        resp.raise_for_status()
        devices = resp.json()
        reflex = devices.get("reflex")
        if not reflex or not reflex.get("connected"):
            raise RuntimeError("reflex MCU not connected")
        log.info("reflex adapter: MCU connected, ready")

    async def setup_scenario(self, scenario: ScenarioConfig) -> None:
        self._acc.reset()
        self._scenario_name = scenario.name

        if scenario.name == "step_response":
            if not self._allow_motion:
                raise RuntimeError(
                    "step_response requires --allow-motion (safety opt-in)"
                )
            # Send a twist command to start moving
            self._acc.v_target_mm_s = 200.0
            await self._ws_cmd("twist", v=200, w=0)
        else:
            # idle_hold — ensure stopped
            await self._ws_cmd("twist", v=0, w=0)

        log.info("reflex scenario %s: setup complete", scenario.name)

    async def tick(self, now_s: float) -> dict[str, Any] | None:
        """Poll reflex state. Returns sample dict or None if stale."""
        resp = await self._client.get(f"{self._base_url}/debug/devices")
        resp.raise_for_status()
        devices = resp.json()

        reflex = devices.get("reflex", {})
        seq = reflex.get("last_state_seq", 0)
        age_ms = reflex.get("last_state_age_ms", 0.0)

        if seq == self._acc.last_seq:
            return None

        # Also get motion state from /status
        status_resp = await self._client.get(f"{self._base_url}/status")
        status_resp.raise_for_status()
        status = status_resp.json()

        return {
            "window_frames": 1,  # Each state packet is one "frame"
            "seq": seq,
            "age_ms": age_ms,
            "speed_l_mm_s": status.get("speed_l_mm_s", 0),
            "speed_r_mm_s": status.get("speed_r_mm_s", 0),
            "fault_flags": status.get("fault_flags", 0),
            "rx_mono_ms": time.monotonic() * 1000.0,
        }

    async def ingest_sample(
        self, scenario: ScenarioConfig, sample: dict[str, Any]
    ) -> None:
        a = self._acc
        seq = sample["seq"]
        rx_ms = sample["rx_mono_ms"]

        # State period (time between consecutive state packets)
        if a.last_rx_mono_ms > 0:
            period_ms = rx_ms - a.last_rx_mono_ms
            if period_ms > 0:
                a.state_periods_ms.append(period_ms)

        a.last_seq = seq
        a.last_rx_mono_ms = rx_ms

        # State age
        a.state_ages_ms.append(sample["age_ms"])

        # Fault tracking
        a.total_samples += 1
        if sample["fault_flags"] != 0:
            a.fault_nonzero_count += 1

        # Motion tracking error (step_response only)
        if scenario.name == "step_response" and a.v_target_mm_s > 0:
            v_meas = (sample["speed_l_mm_s"] + sample["speed_r_mm_s"]) / 2.0
            a.v_error_abs.append(abs(v_meas - a.v_target_mm_s))

    def compute_result(self, scenario: ScenarioConfig) -> ScenarioResult:
        a = self._acc

        # State rate
        period_stats = compute_stats(a.state_periods_ms)
        rate_hz = 1000.0 / period_stats["mean"] if period_stats["mean"] > 0 else 0.0

        metrics: dict[str, Any] = {
            "state_rate_hz_mean": round(rate_hz, 1),
            "state_period_ms_p50": period_stats["p50"],
            "state_period_ms_p95": period_stats["p95"],
            "state_period_ms_max": period_stats["max"],
        }

        # State age
        age_stats = compute_stats(a.state_ages_ms)
        metrics["state_age_ms_p50"] = age_stats["p50"]
        metrics["state_age_ms_p95"] = age_stats["p95"]
        metrics["state_age_ms_max"] = age_stats["max"]

        # Faults
        metrics["fault_nonzero_samples"] = a.fault_nonzero_count
        metrics["fault_nonzero_pct"] = (
            round(a.fault_nonzero_count / a.total_samples * 100.0, 2)
            if a.total_samples > 0
            else 0.0
        )

        # Motion metrics (step_response only)
        if scenario.name == "step_response" and a.v_error_abs:
            v_stats = compute_stats(a.v_error_abs)
            metrics["v_error_abs_mm_s_p50"] = v_stats["p50"]
            metrics["v_error_abs_mm_s_p95"] = v_stats["p95"]
            metrics["v_error_abs_mm_s_max"] = v_stats["max"]

        return ScenarioResult(
            name=scenario.name,
            metrics=metrics,
            samples=a.total_samples,
        )

    async def teardown(self) -> None:
        """Stop motion and clean up."""
        try:
            await self._ws_cmd("twist", v=0, w=0)
        except Exception as e:
            log.warning("reflex teardown error: %s", e)
        finally:
            if self._client:
                await self._client.aclose()
                self._client = None

    async def _ws_cmd(self, msg_type: str, **kwargs: Any) -> None:
        """Send a command via supervisor WS."""
        import websockets

        ws_url = self._base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        msg = {"type": msg_type, **kwargs}
        async with websockets.connect(f"{ws_url}/ws", open_timeout=5.0) as ws:
            await ws.send(__import__("json").dumps(msg))
            await asyncio.sleep(0.05)


def create_reflex_adapter(
    *,
    base_url: str,
    target_samples: int = 100,
    allow_motion: bool = False,
) -> tuple[ReflexAdapter, list[ScenarioConfig]]:
    """Factory — returns adapter + scenario list for reflex benchmark."""
    adapter = ReflexAdapter(
        base_url, target_samples=target_samples, allow_motion=allow_motion
    )
    scenarios = [
        ScenarioConfig(
            name="idle_hold", target_samples=target_samples, settle_samples=3
        ),
    ]
    if allow_motion:
        scenarios.append(
            ScenarioConfig(
                name="step_response",
                target_samples=target_samples,
                settle_samples=10,
                timeout_s=60.0,
            )
        )
    return adapter, scenarios
