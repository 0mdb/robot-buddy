"""Tests for MCU benchmark stats helpers and core lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

from supervisor.api.mcu_benchmark import (
    compare_artifacts,
    compute_stats,
    percentile,
    weighted_mean,
)


class TestWeightedMean:
    def test_basic(self):
        assert weighted_mean([10, 20], [1, 1]) == 15.0

    def test_weighted(self):
        # 10*3 + 20*1 = 50, total weight 4 => 12.5
        assert weighted_mean([10, 20], [3, 1]) == 12.5

    def test_empty(self):
        assert weighted_mean([], []) == 0.0

    def test_zero_weight(self):
        assert weighted_mean([10, 20], [0, 0]) == 0.0


class TestPercentile:
    def test_p50_odd(self):
        assert percentile([1, 2, 3, 4, 5], 50) == 3.0

    def test_p50_even(self):
        assert percentile([1, 2, 3, 4], 50) == 2.0

    def test_p95(self):
        vals = list(range(1, 101))  # 1..100
        assert percentile(vals, 95) == 95.0

    def test_p0(self):
        assert percentile([10, 20, 30], 0) == 10.0

    def test_p100(self):
        assert percentile([10, 20, 30], 100) == 30.0

    def test_empty(self):
        assert percentile([], 50) == 0.0

    def test_single(self):
        assert percentile([42], 50) == 42.0


class TestComputeStats:
    def test_basic(self):
        stats = compute_stats([1, 2, 3, 4, 5])
        assert stats["mean"] == 3.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["p50"] == 3.0

    def test_empty(self):
        stats = compute_stats([])
        assert stats["mean"] == 0.0
        assert stats["p50"] == 0.0

    def test_single(self):
        stats = compute_stats([42])
        assert stats["mean"] == 42.0
        assert stats["p50"] == 42.0
        assert stats["p95"] == 42.0


class TestCompareArtifacts:
    def _write_artifact(self, tmp: Path, name: str, scenarios: dict) -> str:
        artifact = {
            "version": 2,
            "scenarios": scenarios,
        }
        path = tmp / name
        path.write_text(json.dumps(artifact))
        return str(path)

    def test_pass_identical(self, tmp_path):
        scenarios = {"idle": {"frame_us_avg": 75000, "fps_est": 13.3}}
        a = self._write_artifact(tmp_path, "a.json", scenarios)
        b = self._write_artifact(tmp_path, "b.json", scenarios)
        report = compare_artifacts(a, b)
        assert report["overall_pass"] is True
        assert report["scenarios"]["idle"]["fps_drop_pct"] == 0.0

    def test_fail_large_drop(self, tmp_path):
        a_scenarios = {"idle": {"frame_us_avg": 75000}}
        # 5% slower => frame_us_avg = 78947
        b_scenarios = {"idle": {"frame_us_avg": 78947}}
        a = self._write_artifact(tmp_path, "a.json", a_scenarios)
        b = self._write_artifact(tmp_path, "b.json", b_scenarios)
        report = compare_artifacts(a, b, fps_threshold_pct=1.0)
        assert report["overall_pass"] is False
        assert report["scenarios"]["idle"]["fps_drop_pct"] > 1.0

    def test_missing_scenario_skipped(self, tmp_path):
        a = self._write_artifact(tmp_path, "a.json", {"idle": {"frame_us_avg": 75000}})
        b = self._write_artifact(tmp_path, "b.json", {"rage": {"frame_us_avg": 80000}})
        report = compare_artifacts(a, b)
        assert report["overall_pass"] is True
        assert len(report["scenarios"]) == 0
