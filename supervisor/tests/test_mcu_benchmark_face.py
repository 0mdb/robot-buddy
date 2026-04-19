"""Tests for face MCU benchmark adapter — sample ingestion and metric computation."""

from __future__ import annotations

from supervisor.api.mcu_benchmark import ScenarioConfig
from supervisor.api.mcu_benchmark_face import FaceAdapter, _Accumulator


def _make_sample(
    *,
    window_frames: int = 64,
    frame_us_avg: int = 75000,
    frame_us_max: int = 80000,
    render_us_avg: int = 7500,
    render_us_max: int = 65000,
    eyes_us_avg: int = 12700,
    mouth_us_avg: int = 6900,
    border_us_avg: int = 23000,
    effects_us_avg: int = 17000,
    overlay_us_avg: int = 5,
    dirty_px_avg: int = 9600,
    spi_bytes_per_s: int = 192000,
    cmd_rx_to_apply_us_avg: int = 1000,
    sample_div: int = 1,
    seq: int = 1,
) -> dict:
    return {
        "window_frames": window_frames,
        "frame_us_avg": frame_us_avg,
        "frame_us_max": frame_us_max,
        "render_us_avg": render_us_avg,
        "render_us_max": render_us_max,
        "eyes_us_avg": eyes_us_avg,
        "mouth_us_avg": mouth_us_avg,
        "border_us_avg": border_us_avg,
        "effects_us_avg": effects_us_avg,
        "overlay_us_avg": overlay_us_avg,
        "dirty_px_avg": dirty_px_avg,
        "spi_bytes_per_s": spi_bytes_per_s,
        "cmd_rx_to_apply_us_avg": cmd_rx_to_apply_us_avg,
        "sample_div": sample_div,
        "seq": seq,
    }


class TestAccumulator:
    def test_reset_clears(self):
        acc = _Accumulator()
        acc.frame_us_avg_sum = 1000
        acc.sample_count = 5
        acc.frame_us_samples.append(42)
        acc.reset()
        assert acc.frame_us_avg_sum == 0.0
        assert acc.sample_count == 0
        assert len(acc.frame_us_samples) == 0


class TestFaceAdapterIngest:
    """Test ingestion and metric computation without network I/O."""

    def _make_adapter(self) -> FaceAdapter:
        return FaceAdapter("http://localhost:8080")

    def test_single_sample(self):
        import asyncio

        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle", target_samples=1)
        sample = _make_sample()

        asyncio.get_event_loop().run_until_complete(
            adapter.ingest_sample(scenario, sample)
        )
        result = adapter.compute_result(scenario)

        assert result.name == "idle"
        assert result.samples == 1
        assert result.metrics["frames"] == 64
        assert result.metrics["frame_us_avg"] == 75000
        assert result.metrics["frame_us_max"] == 80000
        assert result.metrics["fps_est"] > 13.0
        # p50 == p95 for single sample
        assert result.metrics["frame_us_p50"] == 75000.0
        assert result.metrics["frame_us_p95"] == 75000.0

    def test_multiple_samples_weighted(self):
        import asyncio

        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle", target_samples=2)

        # Two windows with different frame counts (weights)
        s1 = _make_sample(window_frames=64, frame_us_avg=70000, frame_us_max=75000)
        s2 = _make_sample(window_frames=128, frame_us_avg=80000, frame_us_max=90000)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(adapter.ingest_sample(scenario, s1))
        loop.run_until_complete(adapter.ingest_sample(scenario, s2))
        result = adapter.compute_result(scenario)

        # Weighted average: (70000*64 + 80000*128) / (64+128) = 76667
        assert result.metrics["frame_us_avg"] == round(
            (70000 * 64 + 80000 * 128) / (64 + 128)
        )
        assert result.metrics["frame_us_max"] == 90000
        assert result.metrics["frames"] == 192  # 64+128
        assert result.samples == 2

    def test_percentiles_with_spread(self):
        import asyncio

        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle", target_samples=20)
        loop = asyncio.get_event_loop()

        # 20 samples with increasing frame times
        for i in range(20):
            s = _make_sample(
                window_frames=64,
                frame_us_avg=70000 + i * 1000,
                border_us_avg=20000 + i * 500,
                mouth_us_avg=5000 + i * 100,
                seq=i,
            )
            loop.run_until_complete(adapter.ingest_sample(scenario, s))

        result = adapter.compute_result(scenario)
        assert result.samples == 20

        # p50 should be around the middle value
        assert 78000 < result.metrics["frame_us_p50"] < 82000
        # p95 should be near the top
        assert result.metrics["frame_us_p95"] >= 87000

    def test_legacy_fields_present(self):
        """Verify all v1 artifact fields are still produced."""
        import asyncio

        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle", target_samples=1)
        sample = _make_sample()
        asyncio.get_event_loop().run_until_complete(
            adapter.ingest_sample(scenario, sample)
        )
        result = adapter.compute_result(scenario)

        legacy_fields = [
            "frames",
            "frame_us_avg",
            "frame_us_max",
            "fps_est",
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
        for f in legacy_fields:
            assert f in result.metrics, f"missing legacy field: {f}"

    def test_new_percentile_fields_present(self):
        """Verify new p50/p95 fields are produced."""
        import asyncio

        adapter = self._make_adapter()
        scenario = ScenarioConfig(name="idle", target_samples=1)
        sample = _make_sample()
        asyncio.get_event_loop().run_until_complete(
            adapter.ingest_sample(scenario, sample)
        )
        result = adapter.compute_result(scenario)

        new_fields = [
            "frame_us_p50",
            "frame_us_p95",
            "render_us_p50",
            "render_us_p95",
            "border_us_p50",
            "border_us_p95",
            "mouth_us_p50",
            "mouth_us_p95",
        ]
        for f in new_fields:
            assert f in result.metrics, f"missing new field: {f}"
