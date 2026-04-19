"""Cross-MCU benchmark harness — shared core with target adapters.

Runs perf scenarios against face or reflex MCU via the supervisor's
debug surface, collects time-series samples, computes percentile stats,
and writes versioned JSON artifacts to docs/perf/.

Public API:
    start_benchmark()   — launch from WS command handler
    cancel_benchmark()  — cancel running benchmark
    get_status()        — poll from GET /debug/mcu_benchmark

CLI (standalone):
    python -m supervisor.api.mcu_benchmark --target face --base-url http://...
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from supervisor.messages.types import MCU_BENCHMARK_DONE, MCU_BENCHMARK_PROGRESS

if TYPE_CHECKING:
    from supervisor.api.conversation_capture import ConversationCapture

log = logging.getLogger(__name__)

# ── Stats helpers ────────────────────────────────────────────────────


def weighted_mean(values: list[int | float], weights: list[int | float]) -> float:
    """Weighted arithmetic mean. Returns 0.0 if total weight is zero."""
    total_w = sum(weights)
    if total_w <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def percentile(sorted_values: list[int | float], p: float) -> float:
    """Compute p-th percentile (0–100) from pre-sorted values.

    Uses nearest-rank method. Returns 0.0 for empty input.
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if p <= 0:
        return float(sorted_values[0])
    if p >= 100:
        return float(sorted_values[-1])
    idx = int(math.ceil(n * p / 100.0)) - 1
    return float(sorted_values[max(0, idx)])


def compute_stats(
    values: list[int] | list[float] | list[int | float],
) -> dict[str, float]:
    """Compute mean/min/max/p50/p95 for a list of values."""
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0}
    s = sorted(values)
    return {
        "mean": round(sum(values) / len(values), 1),
        "min": float(s[0]),
        "max": float(s[-1]),
        "p50": round(percentile(s, 50), 1),
        "p95": round(percentile(s, 95), 1),
    }


# ── Scenario + run state ────────────────────────────────────────────


@dataclass(slots=True)
class ScenarioConfig:
    """Definition of a single benchmark scenario."""

    name: str
    target_samples: int = 100
    settle_samples: int = 5
    timeout_s: float = 300.0


@dataclass(slots=True)
class ScenarioResult:
    """Collected metrics for one completed scenario."""

    name: str
    metrics: dict[str, Any] = field(default_factory=dict)
    samples: int = 0
    dropped: int = 0
    errors: int = 0
    elapsed_s: float = 0.0


@dataclass(slots=True)
class RunState:
    """Mutable state exposed via /debug/mcu_benchmark."""

    status: str = "idle"  # idle | running | completed | failed | cancelled
    target: str = ""
    profile: str = ""
    scenario_index: int = 0
    scenario_count: int = 0
    current_scenario: str = ""
    samples_collected: int = 0
    samples_target: int = 0
    started_at: str = ""
    error: str = ""
    artifact_path: str = ""


_run_state = RunState()


def get_status() -> dict[str, Any]:
    """Return current benchmark status for /debug/mcu_benchmark."""
    s = _run_state
    return {
        "status": s.status,
        "target": s.target,
        "profile": s.profile,
        "scenario_index": s.scenario_index,
        "scenario_count": s.scenario_count,
        "current_scenario": s.current_scenario,
        "samples_collected": s.samples_collected,
        "samples_target": s.samples_target,
        "started_at": s.started_at,
        "error": s.error,
        "artifact_path": s.artifact_path,
    }


# ── Target adapter interface ────────────────────────────────────────


class TargetAdapter(ABC):
    """Interface that face/reflex adapters must implement."""

    @abstractmethod
    async def prepare(self, base_url: str) -> None:
        """One-time setup (verify connectivity, cache initial state)."""

    @abstractmethod
    async def setup_scenario(self, scenario: ScenarioConfig) -> None:
        """Configure MCU for this scenario (set mood, conv state, etc.)."""

    @abstractmethod
    async def tick(self, now_s: float) -> dict[str, Any] | None:
        """Poll one sample. Return metrics dict or None if no new data."""

    @abstractmethod
    async def ingest_sample(
        self, scenario: ScenarioConfig, sample: dict[str, Any]
    ) -> None:
        """Accumulate a sample into internal accumulators."""

    @abstractmethod
    def compute_result(self, scenario: ScenarioConfig) -> ScenarioResult:
        """Finalize metrics for the completed scenario."""

    @abstractmethod
    async def teardown(self) -> None:
        """Reset MCU to idle state."""


# ── Run lifecycle ────────────────────────────────────────────────────

_benchmark_task: asyncio.Task[None] | None = None


def start_benchmark(
    target: str,
    profile: str,
    adapter: TargetAdapter,
    scenarios: list[ScenarioConfig],
    conv_capture: ConversationCapture | None = None,
    base_url: str = "http://localhost:8080",
    out_dir: str = "docs/perf",
    notes: list[str] | None = None,
) -> bool:
    """Start a benchmark run. Returns False if one is already running."""
    global _benchmark_task  # noqa: PLW0603
    if _benchmark_task and not _benchmark_task.done():
        log.warning("mcu_benchmark: run already in progress")
        return False
    _benchmark_task = asyncio.create_task(
        _run(
            target=target,
            profile=profile,
            adapter=adapter,
            scenarios=scenarios,
            conv_capture=conv_capture,
            base_url=base_url,
            out_dir=out_dir,
            notes=notes or [],
        )
    )
    return True


def cancel_benchmark() -> bool:
    """Cancel a running benchmark. Returns True if cancellation was sent."""
    global _benchmark_task  # noqa: PLW0603
    if _benchmark_task and not _benchmark_task.done():
        _benchmark_task.cancel()
        return True
    return False


async def _run(
    *,
    target: str,
    profile: str,
    adapter: TargetAdapter,
    scenarios: list[ScenarioConfig],
    conv_capture: ConversationCapture | None,
    base_url: str,
    out_dir: str,
    notes: list[str],
) -> None:
    """Execute the full benchmark lifecycle."""
    global _run_state  # noqa: PLW0603
    _run_state = RunState(
        status="running",
        target=target,
        profile=profile,
        scenario_count=len(scenarios),
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    results: dict[str, dict[str, Any]] = {}
    try:
        await adapter.prepare(base_url)

        for idx, scenario in enumerate(scenarios):
            _run_state.scenario_index = idx
            _run_state.current_scenario = scenario.name
            _run_state.samples_collected = 0
            _run_state.samples_target = scenario.target_samples

            result = await _run_scenario(adapter, scenario, conv_capture)
            results[scenario.name] = result.metrics
            results[scenario.name]["samples"] = result.samples
            results[scenario.name]["dropped"] = result.dropped
            results[scenario.name]["errors"] = result.errors
            results[scenario.name]["elapsed_s"] = round(result.elapsed_s, 1)

            if conv_capture:
                conv_capture.capture_event(
                    MCU_BENCHMARK_PROGRESS,
                    {
                        "target": target,
                        "scenario": scenario.name,
                        "index": idx,
                        "total": len(scenarios),
                        "metrics": result.metrics,
                    },
                )

        # Write artifact
        artifact = _build_artifact(
            target=target,
            profile=profile,
            base_url=base_url,
            scenarios=results,
            notes=notes,
        )
        artifact_path = _write_artifact(artifact, out_dir, target, profile)
        _run_state.artifact_path = artifact_path
        _run_state.status = "completed"

        if conv_capture:
            conv_capture.capture_event(
                MCU_BENCHMARK_DONE,
                {
                    "target": target,
                    "profile": profile,
                    "artifact_path": artifact_path,
                    "scenario_count": len(scenarios),
                },
            )
        log.info("mcu_benchmark: completed — %s", artifact_path)

    except asyncio.CancelledError:
        _run_state.status = "cancelled"
        log.info("mcu_benchmark: cancelled")
    except Exception as e:
        _run_state.status = "failed"
        _run_state.error = str(e)
        log.error("mcu_benchmark: failed — %s", e)
        if conv_capture:
            conv_capture.capture_event(
                MCU_BENCHMARK_DONE,
                {"target": target, "error": str(e)},
            )
    finally:
        try:
            await adapter.teardown()
        except Exception as e:
            log.warning("mcu_benchmark: teardown error — %s", e)


async def _run_scenario(
    adapter: TargetAdapter,
    scenario: ScenarioConfig,
    conv_capture: ConversationCapture | None,
) -> ScenarioResult:
    """Run a single scenario: setup, collect samples, compute result."""
    await adapter.setup_scenario(scenario)

    # Settle period — discard initial samples
    settled = 0
    t_settle_start = time.monotonic()
    while settled < scenario.settle_samples:
        if time.monotonic() - t_settle_start > 30.0:
            log.warning("scenario %s: settle timeout", scenario.name)
            break
        sample = await adapter.tick(time.monotonic())
        if sample is not None:
            settled += 1
        await asyncio.sleep(0.05)

    # Collection
    collected = 0
    dropped = 0
    errors = 0
    t_start = time.monotonic()
    deadline = t_start + scenario.timeout_s

    while collected < scenario.target_samples:
        now = time.monotonic()
        if now > deadline:
            log.warning(
                "scenario %s: timeout after %d/%d samples",
                scenario.name,
                collected,
                scenario.target_samples,
            )
            break

        try:
            sample = await adapter.tick(now)
        except Exception as e:
            errors += 1
            log.warning("scenario %s: tick error — %s", scenario.name, e)
            await asyncio.sleep(0.1)
            continue

        if sample is None:
            await asyncio.sleep(0.05)
            continue

        # Validate sample has meaningful data
        window_frames = sample.get("window_frames", 0)
        if window_frames <= 0:
            dropped += 1
            await asyncio.sleep(0.05)
            continue

        try:
            await adapter.ingest_sample(scenario, sample)
        except Exception as e:
            errors += 1
            log.warning("scenario %s: ingest error — %s", scenario.name, e)
            await asyncio.sleep(0.05)
            continue

        collected += 1
        _run_state.samples_collected = collected
        await asyncio.sleep(0.05)

    elapsed = time.monotonic() - t_start
    result = adapter.compute_result(scenario)
    result.elapsed_s = elapsed
    result.dropped = dropped
    result.errors = errors
    return result


# ── Artifact I/O ─────────────────────────────────────────────────────


def _build_artifact(
    *,
    target: str,
    profile: str,
    base_url: str,
    scenarios: dict[str, dict[str, Any]],
    notes: list[str],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": 2,
        "target": target,
        "profile": profile,
        "captured_at": now,
        "endpoint": base_url,
        "notes": notes,
        "scenarios": scenarios,
        "completed_at": now,
    }


def _write_artifact(
    artifact: dict[str, Any], out_dir: str, target: str, profile: str
) -> str:
    """Write artifact JSON and return the path."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{target}_{profile}_{date_str}.json"
    filepath = out_path / filename
    filepath.write_text(json.dumps(artifact, indent=2) + "\n")
    return str(filepath)


# ── Compare mode ─────────────────────────────────────────────────────


def compare_artifacts(
    path_a: str,
    path_b: str,
    *,
    fps_threshold_pct: float = 1.0,
) -> dict[str, Any]:
    """Compare two benchmark artifacts (A=baseline, B=test).

    Returns per-scenario delta report with pass/fail against fps_threshold_pct.
    """
    a = json.loads(Path(path_a).read_text())
    b = json.loads(Path(path_b).read_text())

    report: dict[str, Any] = {
        "baseline": path_a,
        "test": path_b,
        "threshold_pct": fps_threshold_pct,
        "scenarios": {},
        "overall_pass": True,
    }

    for name in a.get("scenarios", {}):
        if name not in b.get("scenarios", {}):
            continue
        sa = a["scenarios"][name]
        sb = b["scenarios"][name]

        # Compute FPS from frame_us_avg
        fps_a = 1_000_000.0 / sa["frame_us_avg"] if sa.get("frame_us_avg") else 0.0
        fps_b = 1_000_000.0 / sb["frame_us_avg"] if sb.get("frame_us_avg") else 0.0
        fps_drop_pct = ((fps_a - fps_b) / fps_a * 100.0) if fps_a > 0 else 0.0
        passed = fps_drop_pct <= fps_threshold_pct

        delta: dict[str, Any] = {
            "fps_a": round(fps_a, 2),
            "fps_b": round(fps_b, 2),
            "fps_drop_pct": round(fps_drop_pct, 2),
            "pass": passed,
        }

        # Delta for all numeric metrics
        for key in sa:
            if isinstance(sa[key], (int, float)) and key in sb:
                val_a = sa[key]
                val_b = sb[key]
                if val_a != 0:
                    delta[f"{key}_delta_pct"] = round(
                        (val_b - val_a) / val_a * 100.0, 2
                    )

        report["scenarios"][name] = delta
        if not passed:
            report["overall_pass"] = False

    return report


# ── CLI entry point ──────────────────────────────────────────────────


async def _cli_main(args: Any) -> None:
    """CLI main — runs benchmark against a live supervisor."""
    import httpx

    base_url = args.base_url.rstrip("/")

    # Verify supervisor is reachable
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{base_url}/status")
        resp.raise_for_status()
        log.info("supervisor reachable at %s", base_url)

    if args.compare:
        if len(args.compare) != 2:
            log.error("--compare requires exactly 2 artifact paths")
            return
        report = compare_artifacts(
            args.compare[0], args.compare[1], fps_threshold_pct=1.0
        )
        print(json.dumps(report, indent=2))
        return

    adapter: TargetAdapter
    scenarios: list[ScenarioConfig]
    if args.target == "face":
        from supervisor.api.mcu_benchmark_face import create_face_adapter

        adapter, scenarios = create_face_adapter(
            base_url=base_url,
            target_samples=args.samples,
        )
    elif args.target == "reflex":
        from supervisor.api.mcu_benchmark_reflex import create_reflex_adapter

        adapter, scenarios = create_reflex_adapter(
            base_url=base_url,
            target_samples=args.samples,
            allow_motion=args.allow_motion,
        )
    else:
        log.error("unknown target: %s", args.target)
        return

    # Run directly (no supervisor WS, standalone mode)
    started = start_benchmark(
        target=args.target,
        profile=args.profile or f"stage4_{args.target}",
        adapter=adapter,
        scenarios=scenarios,
        base_url=base_url,
        out_dir=args.out,
        notes=[f"CLI run, target={args.target}"],
    )
    if not started:
        log.error("failed to start benchmark")
        return

    # Poll until done
    while True:
        status = get_status()
        if status["status"] in ("completed", "failed", "cancelled"):
            break
        log.info(
            "  [%d/%d] %s — %d/%d samples",
            status["scenario_index"] + 1,
            status["scenario_count"],
            status["current_scenario"],
            status["samples_collected"],
            status["samples_target"],
        )
        await asyncio.sleep(2.0)

    final = get_status()
    if final["status"] == "completed":
        log.info("benchmark completed — artifact: %s", final["artifact_path"])
        # Print artifact
        artifact = json.loads(Path(final["artifact_path"]).read_text())
        print(json.dumps(artifact, indent=2))
    else:
        log.error("benchmark %s: %s", final["status"], final.get("error", ""))


def main() -> None:
    """CLI entry point."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Cross-MCU benchmark harness",
        prog="python -m supervisor.api.mcu_benchmark",
    )
    parser.add_argument(
        "--target",
        choices=["face", "reflex"],
        default="face",
        help="MCU target (default: face)",
    )
    parser.add_argument(
        "--profile",
        default="",
        help="Profile name for artifact filename (default: stage4_<target>)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Supervisor base URL",
    )
    parser.add_argument(
        "--out",
        default="docs/perf",
        help="Output directory for artifacts (default: docs/perf)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=100,
        help="Target samples per scenario (default: 100)",
    )
    parser.add_argument(
        "--allow-motion",
        action="store_true",
        help="Enable motion scenarios for reflex (safety opt-in)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "TEST"),
        help="Compare two artifact files instead of running",
    )
    args = parser.parse_args()
    asyncio.run(_cli_main(args))


if __name__ == "__main__":
    main()
