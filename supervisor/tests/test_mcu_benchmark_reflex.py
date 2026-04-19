"""Tests for reflex MCU benchmark adapter — sample ingestion and metric computation."""

from __future__ import annotations

import asyncio

from supervisor.api.mcu_benchmark import ScenarioConfig
from supervisor.api.mcu_benchmark_reflex import ReflexAdapter, _ReflexAccumulator


def _make_sample(
    *,
    seq: int = 1,
    age_ms: float = 5.0,
    speed_l_mm_s: int = 0,
    speed_r_mm_s: int = 0,
    fault_flags: int = 0,
    rx_mono_ms: float = 1000.0,
) -> dict:
    return {
        "window_frames": 1,
        "seq": seq,
        "age_ms": age_ms,
        "speed_l_mm_s": speed_l_mm_s,
        "speed_r_mm_s": speed_r_mm_s,
        "fault_flags": fault_flags,
        "rx_mono_ms": rx_mono_ms,
    }


class TestReflexAccumulator:
    def test_reset_clears(self):
        acc = _ReflexAccumulator()
        acc.total_samples = 5
        acc.state_periods_ms.append(20.0)
        acc.reset()
        assert acc.total_samples == 0
        assert len(acc.state_periods_ms) == 0


class TestReflexAdapterIngest:
    """Test ingestion and metric computation without network I/O."""

    def _make_adapter(self) -> ReflexAdapter:
        return ReflexAdapter("http://localhost:8080")

    def test_idle_metrics(self):
        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle_hold", target_samples=10)
        loop = asyncio.get_event_loop()

        # Simulate 10 state packets at ~50 Hz (20 ms apart)
        for i in range(10):
            s = _make_sample(
                seq=i,
                age_ms=5.0 + i * 0.5,
                rx_mono_ms=1000.0 + i * 20.0,
            )
            loop.run_until_complete(adapter.ingest_sample(scenario, s))

        result = adapter.compute_result(scenario)
        assert result.name == "idle_hold"
        assert result.samples == 10

        # 9 periods (first sample has no predecessor)
        assert result.metrics["state_rate_hz_mean"] > 40.0
        assert result.metrics["state_period_ms_p50"] == 20.0
        assert result.metrics["fault_nonzero_samples"] == 0
        assert result.metrics["fault_nonzero_pct"] == 0.0

    def test_fault_tracking(self):
        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle_hold", target_samples=4)
        loop = asyncio.get_event_loop()

        # 4 samples, 2 with faults
        for i in range(4):
            s = _make_sample(
                seq=i,
                fault_flags=1 if i % 2 == 0 else 0,
                rx_mono_ms=1000.0 + i * 20.0,
            )
            loop.run_until_complete(adapter.ingest_sample(scenario, s))

        result = adapter.compute_result(scenario)
        assert result.metrics["fault_nonzero_samples"] == 2
        assert result.metrics["fault_nonzero_pct"] == 50.0

    def test_step_response_metrics(self):
        adapter = self._make_adapter()
        adapter._acc.v_target_mm_s = 200.0
        scenario = ScenarioConfig(name="step_response", target_samples=5)
        loop = asyncio.get_event_loop()

        for i in range(5):
            s = _make_sample(
                seq=i,
                speed_l_mm_s=190 + i * 2,
                speed_r_mm_s=190 + i * 2,
                rx_mono_ms=1000.0 + i * 20.0,
            )
            loop.run_until_complete(adapter.ingest_sample(scenario, s))

        result = adapter.compute_result(scenario)
        assert "v_error_abs_mm_s_p50" in result.metrics
        assert "v_error_abs_mm_s_p95" in result.metrics
        assert "v_error_abs_mm_s_max" in result.metrics
        # All speeds are close to 200, error should be <= 10
        assert result.metrics["v_error_abs_mm_s_max"] <= 10.0

    def test_no_motion_metrics_for_idle(self):
        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle_hold", target_samples=3)
        loop = asyncio.get_event_loop()

        for i in range(3):
            s = _make_sample(seq=i, rx_mono_ms=1000.0 + i * 20.0)
            loop.run_until_complete(adapter.ingest_sample(scenario, s))

        result = adapter.compute_result(scenario)
        assert "v_error_abs_mm_s_p50" not in result.metrics
