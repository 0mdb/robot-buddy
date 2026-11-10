"""Deterministic motion skills for WANDER mode.

Adapted from v1: accepts both RobotState (MCU hardware) and WorldState
(vision/perception from workers). Ball confidence/bearing now in WorldState.
"""

from __future__ import annotations

from supervisor.devices.protocol import Fault, RangeStatus
from supervisor.core.state import DesiredTwist, RobotState, WorldState


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
        obstacle_escape_max_mm: int = 400,
        obstacle_escape_max_ms: int = 8000,
        no_progress_ms: int = 1000,
        no_progress_cmd_mm_s: int = 20,
        no_progress_cmd_mrad_s: int = 150,
        no_progress_ratio: float = 0.5,
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
        self._obstacle_escape_max_mm = obstacle_escape_max_mm
        self._obstacle_escape_max_ms = obstacle_escape_max_ms
        self._escape_since_ms: float | None = None
        self._escape_mm = 0.0
        self._no_progress_ms = no_progress_ms
        self._no_progress_cmd_mm_s = no_progress_cmd_mm_s
        self._no_progress_cmd_mrad_s = no_progress_cmd_mrad_s
        self._no_progress_ratio = no_progress_ratio
        self._stalled_since_ms: float | None = None
        self._recover_since_ms: float | None = None
        self._active_skill = ""
        self._active_skill_since_ms = 0.0

    def step(
        self,
        robot: RobotState,
        active_skill: str,
        recent_events: list | None = None,
        world: WorldState | None = None,
    ) -> DesiredTwist:
        del recent_events  # Current policies are state-driven and deterministic.
        if world is None:
            world = WorldState()
        skill_elapsed_ms = self._on_skill_tick(active_skill, robot.tick_mono_ms)

        if active_skill == "greet_on_button":
            return DesiredTwist(0, 0)

        # The reflex has latched OBSTACLE. Back away (reverse arc) whatever the sonar says now: at
        # a grazing angle a wall a few cm away reads TIMEOUT, so a range test would fall through
        # to a forward skill the fault gate rightly refuses, and the robot would wait forever.
        # Blind (no rear sensor), so bounded per latch by distance reversed (encoders), with a
        # time backstop for slipping tracks. The MCU releases at range_release_mm, or when blind
        # after backing off (safety.cpp).
        if robot.fault_flags & int(Fault.OBSTACLE):
            if self._escape_since_ms is None:
                self._escape_since_ms = float(robot.tick_mono_ms)
                self._escape_mm = 0.0
            wheels = (abs(robot.speed_l_mm_s) + abs(robot.speed_r_mm_s)) / 2
            self._escape_mm += wheels * max(0.0, robot.tick_dt_ms) / 1000.0
            if (
                self._escape_mm < self._obstacle_escape_max_mm
                and robot.tick_mono_ms - self._escape_since_ms
                < self._obstacle_escape_max_ms
            ):
                return DesiredTwist(self._avoid_reverse_mm_s, self._avoid_turn_mrad_s)
            return DesiredTwist(0, 0)
        self._escape_since_ms = None

        # No progress: last tick's governed command was real, yet the robot is achieving less than
        # no_progress_ratio of it — wheels (linear) or gyro (turning in place, where skid-steer
        # tracks can stall). It is pushing something its sensor cannot see (a wall at a grazing
        # angle reads TIMEOUT, a chair base sits under the beam), below the MCU's STALL threshold.
        # Run one retreat-and-recover cycle, then resume. Ratios, not absolutes: one encoder count
        # per telemetry period already reads ~14 mm/s.
        now_ms = float(robot.tick_mono_ms)
        if self._recover_since_ms is not None:
            elapsed = now_ms - self._recover_since_ms
            if elapsed < self._retreat_cycle_ms():
                return self._retreat_and_recover(elapsed)
            self._recover_since_ms = None
        cmd = robot.twist_capped
        k = self._no_progress_ratio
        if abs(cmd.v_mm_s) >= self._no_progress_cmd_mm_s:
            achieved = (abs(robot.speed_l_mm_s) + abs(robot.speed_r_mm_s)) / 2
            stalled = achieved < k * abs(cmd.v_mm_s)
        elif abs(cmd.w_mrad_s) >= self._no_progress_cmd_mrad_s:
            stalled = abs(robot.gyro_z_mrad_s) < k * abs(cmd.w_mrad_s)
        else:
            stalled = False
        if stalled:
            if self._stalled_since_ms is None:
                self._stalled_since_ms = now_ms
            elif now_ms - self._stalled_since_ms > self._no_progress_ms:
                self._stalled_since_ms = None
                self._recover_since_ms = now_ms
                return self._retreat_and_recover(0.0)
        else:
            self._stalled_since_ms = None

        if active_skill == "retreat_and_recover":
            return self._retreat_and_recover(skill_elapsed_ms)

        if active_skill == "approach_until_range":
            return self._approach_until_range(robot, world, skill_elapsed_ms)

        if self._is_obstacle_close(robot):
            return self._avoid_obstacle(robot)

        if active_skill == "avoid_obstacle":
            return self._avoid_obstacle(robot)

        if active_skill == "scan_for_target":
            return self._scan_for_target(robot, world, skill_elapsed_ms)

        if (
            active_skill == "investigate_ball"
            and world.ball_confidence >= self._investigate_min_conf
        ):
            return self._investigate_ball(robot, world)

        return self._patrol_drift(robot)

    def _is_obstacle_close(self, robot: RobotState) -> bool:
        if robot.range_status != int(RangeStatus.OK):
            return False
        return robot.range_mm > 0 and robot.range_mm < self._obstacle_close_mm

    def _avoid_obstacle(self, robot: RobotState) -> DesiredTwist:
        if robot.range_mm > 0 and robot.range_mm < self._obstacle_very_close_mm:
            return DesiredTwist(self._avoid_reverse_mm_s, self._avoid_turn_mrad_s)
        return DesiredTwist(0, self._avoid_turn_mrad_s)

    def _scan_for_target(
        self, robot: RobotState, world: WorldState, skill_elapsed_ms: float
    ) -> DesiredTwist:
        if world.ball_confidence >= self._investigate_min_conf:
            return self._investigate_ball(robot, world)

        phase = int(skill_elapsed_ms // self._scan_flip_ms) % 2
        sign = 1 if phase == 0 else -1
        return DesiredTwist(0, sign * self._scan_turn_mrad_s)

    def _approach_until_range(
        self, robot: RobotState, world: WorldState, skill_elapsed_ms: float
    ) -> DesiredTwist:
        if world.ball_confidence < self._approach_min_conf:
            return self._scan_for_target(robot, world, skill_elapsed_ms)

        turn = self._bearing_turn(world, gain=self._approach_turn_gain, max_abs=500)
        bearing = abs(float(world.ball_bearing_deg))

        if robot.range_status == int(RangeStatus.OK) and robot.range_mm > 0:
            if robot.range_mm <= self._approach_hard_stop_mm:
                return DesiredTwist(self._approach_backoff_mm_s, turn)
            if robot.range_mm < self._approach_range_min_mm:
                return DesiredTwist(int(self._approach_backoff_mm_s * 0.5), turn)
            if robot.range_mm <= self._approach_range_max_mm:
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

    def _retreat_cycle_ms(self) -> int:
        return self._retreat_reverse_ms + self._retreat_turn_ms + self._retreat_pause_ms

    def _retreat_and_recover(self, skill_elapsed_ms: float) -> DesiredTwist:
        cycle_ms = (
            self._retreat_reverse_ms + self._retreat_turn_ms + self._retreat_pause_ms
        )
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

    def _investigate_ball(self, robot: RobotState, world: WorldState) -> DesiredTwist:
        bearing = abs(float(world.ball_bearing_deg))
        turn = self._bearing_turn(world, gain=self._investigate_turn_gain, max_abs=600)
        if bearing > self._investigate_turn_deadband_deg:
            return DesiredTwist(0, turn)
        return DesiredTwist(self._investigate_v_mm_s, turn)

    def _patrol_drift(self, robot: RobotState) -> DesiredTwist:
        phase = int(robot.tick_mono_ms // self._patrol_turn_flip_ms) % 2
        sign = 1 if phase == 0 else -1
        return DesiredTwist(self._patrol_v_mm_s, sign * self._patrol_w_mrad_s)

    def _bearing_turn(self, world: WorldState, *, gain: float, max_abs: int) -> int:
        bearing = float(world.ball_bearing_deg)
        return _clamp_i(bearing * gain, -max_abs, max_abs)

    def _on_skill_tick(self, active_skill: str, tick_mono_ms: float) -> float:
        if active_skill != self._active_skill:
            self._active_skill = active_skill
            self._active_skill_since_ms = float(tick_mono_ms)
        return max(0.0, float(tick_mono_ms) - self._active_skill_since_ms)
