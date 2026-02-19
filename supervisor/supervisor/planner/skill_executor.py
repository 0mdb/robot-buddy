"""Deterministic motion skills for WANDER mode."""

from __future__ import annotations

from supervisor.devices.protocol import RangeStatus
from supervisor.state.datatypes import DesiredTwist, RobotState


def _clamp_i(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


class SkillExecutor:
    """Computes desired twist for deterministic autonomous skills."""

    def __init__(
        self,
        *,
        patrol_v_mm_s: int = 80,
        patrol_w_mrad_s: int = 120,
        patrol_turn_flip_ms: int = 4000,
        investigate_v_mm_s: int = 120,
        investigate_turn_gain: float = 22.0,
        investigate_turn_deadband_deg: float = 12.0,
        investigate_min_conf: float = 0.80,
        scan_turn_mrad_s: int = 260,
        scan_flip_ms: int = 1400,
        approach_v_mm_s: int = 110,
        approach_v_cautious_mm_s: int = 70,
        approach_turn_gain: float = 18.0,
        approach_turn_deadband_deg: float = 8.0,
        approach_min_conf: float = 0.70,
        approach_range_min_mm: int = 380,
        approach_range_max_mm: int = 650,
        approach_hard_stop_mm: int = 260,
        approach_backoff_mm_s: int = -80,
        retreat_reverse_mm_s: int = -120,
        retreat_reverse_ms: int = 900,
        retreat_turn_mrad_s: int = 420,
        retreat_turn_ms: int = 1100,
        retreat_pause_ms: int = 350,
        obstacle_close_mm: int = 450,
        obstacle_very_close_mm: int = 300,
        avoid_reverse_mm_s: int = -120,
        avoid_turn_mrad_s: int = 400,
    ) -> None:
        self._patrol_v_mm_s = patrol_v_mm_s
        self._patrol_w_mrad_s = patrol_w_mrad_s
        self._patrol_turn_flip_ms = patrol_turn_flip_ms
        self._investigate_v_mm_s = investigate_v_mm_s
        self._investigate_turn_gain = investigate_turn_gain
        self._investigate_turn_deadband_deg = investigate_turn_deadband_deg
        self._investigate_min_conf = investigate_min_conf
        self._scan_turn_mrad_s = scan_turn_mrad_s
        self._scan_flip_ms = scan_flip_ms
        self._approach_v_mm_s = approach_v_mm_s
        self._approach_v_cautious_mm_s = approach_v_cautious_mm_s
        self._approach_turn_gain = approach_turn_gain
        self._approach_turn_deadband_deg = approach_turn_deadband_deg
        self._approach_min_conf = approach_min_conf
        self._approach_range_min_mm = approach_range_min_mm
        self._approach_range_max_mm = approach_range_max_mm
        self._approach_hard_stop_mm = approach_hard_stop_mm
        self._approach_backoff_mm_s = approach_backoff_mm_s
        self._retreat_reverse_mm_s = retreat_reverse_mm_s
        self._retreat_reverse_ms = retreat_reverse_ms
        self._retreat_turn_mrad_s = retreat_turn_mrad_s
        self._retreat_turn_ms = retreat_turn_ms
        self._retreat_pause_ms = retreat_pause_ms
        self._obstacle_close_mm = obstacle_close_mm
        self._obstacle_very_close_mm = obstacle_very_close_mm
        self._avoid_reverse_mm_s = avoid_reverse_mm_s
        self._avoid_turn_mrad_s = avoid_turn_mrad_s
        self._active_skill = ""
        self._active_skill_since_ms = 0.0

    def step(
        self,
        state: RobotState,
        active_skill: str,
        recent_events: list | None = None,
    ) -> DesiredTwist:
        del recent_events  # Current policies are state-driven and deterministic.
        skill_elapsed_ms = self._on_skill_tick(active_skill, state.tick_mono_ms)

        if active_skill == "greet_on_button":
            return DesiredTwist(0, 0)

        if active_skill == "retreat_and_recover":
            return self._retreat_and_recover(skill_elapsed_ms)

        if active_skill == "approach_until_range":
            return self._approach_until_range(state, skill_elapsed_ms)

        if self._is_obstacle_close(state):
            return self._avoid_obstacle(state)

        if active_skill == "avoid_obstacle":
            return self._avoid_obstacle(state)

        if active_skill == "scan_for_target":
            return self._scan_for_target(state, skill_elapsed_ms)

        if (
            active_skill == "investigate_ball"
            and state.ball_confidence >= self._investigate_min_conf
        ):
            return self._investigate_ball(state)

        return self._patrol_drift(state)

    def _is_obstacle_close(self, state: RobotState) -> bool:
        if state.range_status != int(RangeStatus.OK):
            return False
        return state.range_mm > 0 and state.range_mm < self._obstacle_close_mm

    def _avoid_obstacle(self, state: RobotState) -> DesiredTwist:
        if state.range_mm > 0 and state.range_mm < self._obstacle_very_close_mm:
            return DesiredTwist(self._avoid_reverse_mm_s, self._avoid_turn_mrad_s)
        return DesiredTwist(0, self._avoid_turn_mrad_s)

    def _scan_for_target(self, state: RobotState, skill_elapsed_ms: float) -> DesiredTwist:
        if state.ball_confidence >= self._investigate_min_conf:
            return self._investigate_ball(state)

        phase = int(skill_elapsed_ms // self._scan_flip_ms) % 2
        sign = 1 if phase == 0 else -1
        return DesiredTwist(0, sign * self._scan_turn_mrad_s)

    def _approach_until_range(
        self, state: RobotState, skill_elapsed_ms: float
    ) -> DesiredTwist:
        if state.ball_confidence < self._approach_min_conf:
            return self._scan_for_target(state, skill_elapsed_ms)

        turn = self._bearing_turn(state, gain=self._approach_turn_gain, max_abs=500)
        bearing = abs(float(state.ball_bearing_deg))

        if state.range_status == int(RangeStatus.OK) and state.range_mm > 0:
            if state.range_mm <= self._approach_hard_stop_mm:
                return DesiredTwist(self._approach_backoff_mm_s, turn)
            if state.range_mm < self._approach_range_min_mm:
                return DesiredTwist(int(self._approach_backoff_mm_s * 0.5), turn)
            if state.range_mm <= self._approach_range_max_mm:
                if bearing <= self._approach_turn_deadband_deg:
                    return DesiredTwist(0, 0)
                return DesiredTwist(0, turn)
            forward = self._approach_v_mm_s
            if bearing > self._approach_turn_deadband_deg:
                forward = self._approach_v_cautious_mm_s
            return DesiredTwist(forward, turn)

        if bearing > self._approach_turn_deadband_deg:
            return DesiredTwist(0, turn)
        return DesiredTwist(self._approach_v_cautious_mm_s, turn)

    def _retreat_and_recover(self, skill_elapsed_ms: float) -> DesiredTwist:
        cycle_ms = self._retreat_reverse_ms + self._retreat_turn_ms + self._retreat_pause_ms
        if cycle_ms <= 0:
            return DesiredTwist(0, 0)

        phase_ms = int(skill_elapsed_ms) % cycle_ms
        cycle_idx = int(skill_elapsed_ms) // cycle_ms
        turn_sign = 1 if (cycle_idx % 2 == 0) else -1

        if phase_ms < self._retreat_reverse_ms:
            return DesiredTwist(self._retreat_reverse_mm_s, 0)
        if phase_ms < (self._retreat_reverse_ms + self._retreat_turn_ms):
            return DesiredTwist(0, turn_sign * self._retreat_turn_mrad_s)
        return DesiredTwist(0, 0)

    def _investigate_ball(self, state: RobotState) -> DesiredTwist:
        bearing = abs(float(state.ball_bearing_deg))
        turn = self._bearing_turn(state, gain=self._investigate_turn_gain, max_abs=600)
        if bearing > self._investigate_turn_deadband_deg:
            return DesiredTwist(0, turn)
        return DesiredTwist(self._investigate_v_mm_s, turn)

    def _patrol_drift(self, state: RobotState) -> DesiredTwist:
        phase = int(state.tick_mono_ms // self._patrol_turn_flip_ms) % 2
        sign = 1 if phase == 0 else -1
        return DesiredTwist(self._patrol_v_mm_s, sign * self._patrol_w_mrad_s)

    def _bearing_turn(self, state: RobotState, *, gain: float, max_abs: int) -> int:
        bearing = float(state.ball_bearing_deg)
        return _clamp_i(bearing * gain, -max_abs, max_abs)

    def _on_skill_tick(self, active_skill: str, tick_mono_ms: float) -> float:
        if active_skill != self._active_skill:
            self._active_skill = active_skill
            self._active_skill_since_ms = float(tick_mono_ms)
        return max(0.0, float(tick_mono_ms) - self._active_skill_since_ms)
