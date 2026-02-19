"""Tests for planner ordering and idempotency guards in Runtime."""

from __future__ import annotations

import time

from supervisor.devices.planner_client import PlannerPlan
from supervisor.runtime import Runtime


class _FakeReflex:
    connected = True


def _plan(*, plan_id: str, seq: int) -> PlannerPlan:
    return PlannerPlan(
        plan_id=plan_id,
        robot_id="robot-1",
        seq=seq,
        monotonic_ts_ms=1000 + seq,
        server_monotonic_ts_ms=1100 + seq,
        actions=[{"action": "skill", "name": "patrol_drift"}],
        ttl_ms=2000,
    )


def test_runtime_drops_out_of_order_plan_seq():
    runtime = Runtime(reflex=_FakeReflex(), robot_id="robot-1")
    runtime._planner_task_started_mono_ms = time.monotonic() * 1000.0

    runtime._apply_planner_plan(_plan(plan_id="p1", seq=10))
    runtime._apply_planner_plan(_plan(plan_id="p2", seq=9))

    assert runtime.state.planner_plan_dropped_out_of_order == 1
    assert runtime._planner_last_accepted_seq == 10


def test_runtime_dedupes_duplicate_plan_ids_within_ttl():
    runtime = Runtime(reflex=_FakeReflex(), robot_id="robot-1")
    runtime._planner_task_started_mono_ms = time.monotonic() * 1000.0

    runtime._apply_planner_plan(_plan(plan_id="dup", seq=1))
    runtime._apply_planner_plan(_plan(plan_id="dup", seq=2))

    assert runtime.state.planner_plan_dropped_duplicate == 1


def test_world_state_includes_robot_metadata_fields():
    runtime = Runtime(reflex=_FakeReflex(), robot_id="robot-xyz")
    runtime.state.tick_mono_ms = 123456.0

    world = runtime._build_world_state(req_seq=77)
    assert world["robot_id"] == "robot-xyz"
    assert world["seq"] == 77
    assert world["monotonic_ts_ms"] == 123456
