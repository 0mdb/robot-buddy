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
        self._obstacle_close_mm = obstacle_close_mm
        self._obstacle_very_close_mm = obstacle_very_close_mm
        self._avoid_reverse_mm_s = avoid_reverse_mm_s
        self._avoid_turn_mrad_s = avoid_turn_mrad_s

    def step(
        self,
        state: RobotState,
        active_skill: str,
        recent_events: list | None = None,
    ) -> DesiredTwist:
        del recent_events  # Current policies are state-driven and deterministic.

        if self._is_obstacle_close(state):
            return self._avoid_obstacle(state)

        if active_skill == "greet_on_button":
            return DesiredTwist(0, 0)

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

    def _investigate_ball(self, state: RobotState) -> DesiredTwist:
        bearing = float(state.ball_bearing_deg)
        turn = _clamp_i(bearing * self._investigate_turn_gain, -600, 600)
        if abs(bearing) > self._investigate_turn_deadband_deg:
            return DesiredTwist(0, turn)
        return DesiredTwist(self._investigate_v_mm_s, turn)

    def _patrol_drift(self, state: RobotState) -> DesiredTwist:
        phase = int(state.tick_mono_ms // self._patrol_turn_flip_ms) % 2
        sign = 1 if phase == 0 else -1
        return DesiredTwist(self._patrol_v_mm_s, sign * self._patrol_w_mrad_s)
