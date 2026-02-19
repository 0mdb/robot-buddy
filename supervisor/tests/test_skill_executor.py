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
    twist = ex.step(s, active_skill="investigate_ball")
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


def test_patrol_skill_ignores_ball_when_not_investigating():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=900,
        ball_confidence=1.0,
        ball_bearing_deg=20.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="patrol_drift")
    assert twist.v_mm_s > 0


def test_investigate_skill_requires_confidence_gate():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=900,
        ball_confidence=0.55,
        ball_bearing_deg=20.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="investigate_ball")
    assert twist.v_mm_s > 0


def test_scan_for_target_sweeps_and_flips_direction():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=900,
        ball_confidence=0.20,
        ball_bearing_deg=0.0,
        tick_mono_ms=1000.0,
    )
    first = ex.step(s, active_skill="scan_for_target")
    assert first.v_mm_s == 0
    assert first.w_mrad_s != 0

    s.tick_mono_ms = 2700.0
    second = ex.step(s, active_skill="scan_for_target")
    assert second.v_mm_s == 0
    assert second.w_mrad_s == -first.w_mrad_s


def test_scan_for_target_tracks_ball_when_confidence_high():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=900,
        ball_confidence=0.95,
        ball_bearing_deg=18.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="scan_for_target")
    assert twist.w_mrad_s > 0


def test_approach_until_range_moves_forward_when_far():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=1200,
        ball_confidence=0.90,
        ball_bearing_deg=0.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="approach_until_range")
    assert twist.v_mm_s > 0


def test_approach_until_range_holds_in_safe_band():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=500,
        ball_confidence=0.90,
        ball_bearing_deg=0.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="approach_until_range")
    assert twist.v_mm_s == 0
    assert twist.w_mrad_s == 0


def test_approach_until_range_backs_off_when_too_close():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=240,
        ball_confidence=0.90,
        ball_bearing_deg=0.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="approach_until_range")
    assert twist.v_mm_s < 0


def test_approach_until_range_falls_back_to_scan_when_target_weak():
    ex = SkillExecutor()
    s = _state(
        range_status=0,
        range_mm=1200,
        ball_confidence=0.20,
        ball_bearing_deg=0.0,
        tick_mono_ms=1000.0,
    )
    twist = ex.step(s, active_skill="approach_until_range")
    assert twist.v_mm_s == 0
    assert twist.w_mrad_s != 0


def test_retreat_and_recover_cycles_reverse_turn_pause():
    ex = SkillExecutor()
    s = _state(range_status=0, range_mm=900, tick_mono_ms=1000.0)
    reverse = ex.step(s, active_skill="retreat_and_recover")
    assert reverse.v_mm_s < 0
    assert reverse.w_mrad_s == 0

    s.tick_mono_ms = 2050.0
    turn = ex.step(s, active_skill="retreat_and_recover")
    assert turn.v_mm_s == 0
    assert turn.w_mrad_s != 0

    s.tick_mono_ms = 3200.0
    pause = ex.step(s, active_skill="retreat_and_recover")
    assert pause.v_mm_s == 0
    assert pause.w_mrad_s == 0
