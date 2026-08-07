"""Priority-based twist source selection (MIGRATION.md § Core Tick Loop step 5)."""

from __future__ import annotations

import logging
import time

from supervisor.core.state import DesiredTwist, Mode, RobotState, WorldState
from supervisor.core.skill_executor import SkillExecutor
from supervisor.core.event_bus import PlannerEvent

log = logging.getLogger(__name__)

# Far enough in the past that a step() before any command has ever arrived reads
# as stale, rather than passing through the zero-initialised twist by luck.
_NEVER_SET_S = -1e9


class BehaviorEngine:
    """Pick twist source based on current mode."""

    def __init__(
        self, skill_executor: SkillExecutor, *, teleop_ttl_s: float = 0.5
    ) -> None:
        self._skill = skill_executor
        self._teleop_twist = DesiredTwist()
        self._teleop_ttl_s = teleop_ttl_s
        self._teleop_set_s = _NEVER_SET_S
        self._teleop_expired = False

    def set_teleop_twist(
        self, v_mm_s: int, w_mrad_s: int, *, now_s: float | None = None
    ) -> None:
        self._teleop_twist = DesiredTwist(v_mm_s, w_mrad_s)
        self._teleop_set_s = time.monotonic() if now_s is None else now_s
        self._teleop_expired = False

    def step(
        self,
        robot: RobotState,
        world: WorldState,
        recent_events: list[PlannerEvent] | None = None,
        *,
        now_s: float | None = None,
    ) -> DesiredTwist:
        """Return the desired twist for this tick."""
        if robot.mode == Mode.TELEOP:
            # Teleop commands expire. Over a link that can fail silently, "no new
            # command" is indistinguishable from "operator is holding the stick
            # still" — so it must never be read as "keep doing this". An operator
            # who is still there re-stamps this many times a second.
            now = time.monotonic() if now_s is None else now_s
            if now - self._teleop_set_s > self._teleop_ttl_s:
                if not self._teleop_expired:
                    log.warning(
                        "teleop command stale (> %.2f s) — zeroing twist",
                        self._teleop_ttl_s,
                    )
                    self._teleop_expired = True  # latched: don't spam at 50 Hz
                return DesiredTwist(0, 0)
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
