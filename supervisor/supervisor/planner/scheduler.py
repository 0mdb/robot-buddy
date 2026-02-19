"""Planner action scheduling with TTL/cooldown/lock enforcement."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from supervisor.planner.validator import ValidatedPlannerPlan


@dataclass(slots=True)
class _QueuedAction:
    action: dict
    expires_mono_ms: float


class PlannerScheduler:
    def __init__(self) -> None:
        self._queue: deque[_QueuedAction] = deque()

        self._last_action_type_ms: dict[str, float] = {}
        self._last_action_key_ms: dict[str, float] = {}

        self._cooldown_type_ms = {
            "say": 3000,
            "emote": 600,
            "gesture": 800,
            "skill": 500,
        }
        self._cooldown_key_ms = {
            "say": 12000,
            "emote": 1800,
            "gesture": 2000,
            "skill": 500,
        }

        self.plan_dropped_stale = 0
        self.plan_dropped_cooldown = 0
        self.active_skill = "patrol_drift"

    def schedule_plan(
        self,
        plan: ValidatedPlannerPlan,
        *,
        now_mono_ms: float,
        issued_mono_ms: float,
    ) -> None:
        if now_mono_ms - issued_mono_ms > plan.ttl_ms:
            self.plan_dropped_stale += 1
            return

        expires_at = issued_mono_ms + plan.ttl_ms
        for action in plan.actions:
            action_type = str(action.get("action", ""))
            if self._on_cooldown(action, action_type, now_mono_ms):
                self.plan_dropped_cooldown += 1
                continue

            self._mark_action(action, action_type, now_mono_ms)

            if action_type == "skill":
                self.active_skill = str(action.get("name", self.active_skill))
                continue

            self._queue.append(_QueuedAction(action=action, expires_mono_ms=expires_at))

    def pop_due_actions(self, *, now_mono_ms: float, face_locked: bool) -> list[dict]:
        due: list[dict] = []
        while self._queue:
            item = self._queue.popleft()
            if item.expires_mono_ms < now_mono_ms:
                self.plan_dropped_stale += 1
                continue

            action_type = str(item.action.get("action", ""))
            if face_locked and action_type in {"emote", "gesture"}:
                self.plan_dropped_cooldown += 1
                continue
            due.append(item.action)
        return due

    def snapshot(self) -> dict:
        return {
            "active_skill": self.active_skill,
            "queue_depth": len(self._queue),
            "plan_dropped_stale": self.plan_dropped_stale,
            "plan_dropped_cooldown": self.plan_dropped_cooldown,
            "cooldowns": {
                "by_type": dict(self._last_action_type_ms),
                "by_key": dict(self._last_action_key_ms),
            },
            "queued_actions": [asdict(x) for x in self._queue],
        }

    def _on_cooldown(self, action: dict, action_type: str, now_mono_ms: float) -> bool:
        type_cd = self._cooldown_type_ms.get(action_type, 0)
        last_type = self._last_action_type_ms.get(action_type, -1e12)
        if now_mono_ms - last_type < type_cd:
            return True

        key = self._action_key(action, action_type)
        if key:
            key_cd = self._cooldown_key_ms.get(action_type, 0)
            last_key = self._last_action_key_ms.get(key, -1e12)
            if now_mono_ms - last_key < key_cd:
                return True
        return False

    def _mark_action(self, action: dict, action_type: str, now_mono_ms: float) -> None:
        self._last_action_type_ms[action_type] = now_mono_ms
        key = self._action_key(action, action_type)
        if key:
            self._last_action_key_ms[key] = now_mono_ms

    @staticmethod
    def _action_key(action: dict, action_type: str) -> str:
        if action_type == "say":
            text = str(action.get("text", "")).strip().lower()
            return f"say:{text}" if text else ""
        if action_type == "emote":
            name = str(action.get("name", "")).strip().lower()
            return f"emote:{name}" if name else ""
        if action_type == "gesture":
            name = str(action.get("name", "")).strip().lower()
            return f"gesture:{name}" if name else ""
        if action_type == "skill":
            name = str(action.get("name", "")).strip().lower()
            return f"skill:{name}" if name else ""
        return ""

