from __future__ import annotations

from supervisor.planner.skill_executor import SkillExecutor
from supervisor.state.datatypes import Mode, RobotState


def _state(**updates) -> RobotState:
    s = RobotState()
    s.mode = Mode.WANDER
    for k, v in updates.items():
        setattr(s, k, v)
    return s


def test_obstacle_priority_over_ball():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=200,
        ball_confidence=0.9,
        ball_bearing_deg=0.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="patrol_drift")
    assert twist.v_mm_s < 0 or twist.w_mrad_s != 0


def test_investigate_ball_turns_toward_bearing():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=900,
        ball_confidence=0.8,
        ball_bearing_deg=20.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="patrol_drift")
    assert twist.w_mrad_s > 0


def test_patrol_drift_when_idle():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=900,
        ball_confidence=0.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="patrol_drift")
    assert twist.v_mm_s > 0
    assert abs(twist.w_mrad_s) > 0

