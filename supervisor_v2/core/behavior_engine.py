"""Priority-based twist source selection (MIGRATION.md § Core Tick Loop step 5)."""

from __future__ import annotations

from supervisor_v2.core.state import DesiredTwist, Mode, RobotState, WorldState
from supervisor_v2.core.skill_executor import SkillExecutor
from supervisor_v2.core.event_bus import PlannerEvent


class BehaviorEngine:
    """Pick twist source based on current mode."""

    def __init__(self, skill_executor: SkillExecutor) -> None:
        self._skill = skill_executor
        self._teleop_twist = DesiredTwist()

    def set_teleop_twist(self, v_mm_s: int, w_mrad_s: int) -> None:
        self._teleop_twist = DesiredTwist(v_mm_s, w_mrad_s)

    def step(
        self,
        robot: RobotState,
        world: WorldState,
        recent_events: list[PlannerEvent] | None = None,
    ) -> DesiredTwist:
        """Return the desired twist for this tick."""
        if robot.mode == Mode.TELEOP:
            return DesiredTwist(self._teleop_twist.v_mm_s, self._teleop_twist.w_mrad_s)

        if robot.mode == Mode.WANDER:
            return self._skill.step(
                robot,
                active_skill=world.active_skill,
                recent_events=recent_events,
                world=world,
            )

        # BOOT, IDLE, ERROR — no motion
        return DesiredTwist(0, 0)
