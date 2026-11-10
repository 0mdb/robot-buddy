"""`learned_wander` as a harness-side SkillExecutor: the policy in place of patrol and avoid.

Vantage SIM-AUTONOMY.md, proposal 4 and decision B. Everything above those two branches of
`SkillExecutor.step` still runs as written: the OBSTACLE-latch escape, the no-progress retreat,
the planner's retreat/approach/scan/investigate skills. Everything after it still runs too: the
tick loop's `apply_safety()` governor and the reflex MCU. The policy is one more twist source
under the governor; it can ask, never bypass.

This lives in training, not `supervisor/`, on purpose. It is injected into the fast tier the same
way stage 2 injected tunables. A learned policy becomes a robot change only through a normal
commit to `supervisor/` after the full tier and a bench trial (README.md "Rules").
"""

from __future__ import annotations

from typing import Any

import numpy as np

import fast_env  # noqa: F401  (puts the supervisor on sys.path)
import policy
from supervisor.core.skill_executor import SkillExecutor
from supervisor.core.state import DesiredTwist, RobotState, WorldState


class LearnedSkillExecutor(SkillExecutor):
    def __init__(self, mlp: policy.Mlp, **tunables: Any) -> None:
        super().__init__(**tunables)
        self.mlp = mlp
        self.obs = policy.ObsBuilder()
        self._cur = np.zeros(policy.N_OBS)
        self.policy_ticks = 0

    def step(
        self,
        robot: RobotState,
        active_skill: str,
        recent_events: list | None = None,
        world: WorldState | None = None,
    ) -> DesiredTwist:
        # Observe every tick, whichever branch drives, so the history has no gaps and the
        # policy sees what the escape and recovery branches did.
        self._cur = self.obs.build(
            range_mm=robot.range_mm,
            range_status=robot.range_status,
            speed_l_mm_s=robot.speed_l_mm_s,
            speed_r_mm_s=robot.speed_r_mm_s,
            gyro_z_mrad_s=robot.gyro_z_mrad_s,
            capped_v_mm_s=robot.twist_capped.v_mm_s,
            capped_w_mrad_s=robot.twist_capped.w_mrad_s,
            tick_mono_ms=robot.tick_mono_ms,
        )
        out = super().step(robot, active_skill, recent_events, world)
        self.obs.last = policy.from_twist(out.v_mm_s, out.w_mrad_s)
        return out

    def _policy_twist(self) -> DesiredTwist:
        self.policy_ticks += 1
        v, w = policy.to_twist(self.mlp.act(self._cur))
        return DesiredTwist(v, w)

    def _patrol_drift(self, robot: RobotState) -> DesiredTwist:
        del robot
        return self._policy_twist()

    def _avoid_obstacle(self, robot: RobotState) -> DesiredTwist:
        del robot
        return self._policy_twist()
