"""Planner action validation and normalization."""

from __future__ import annotations

from dataclasses import dataclass


ALLOWED_SKILLS = frozenset(
    {
        "patrol_drift",
        "investigate_ball",
        "avoid_obstacle",
        "greet_on_button",
        "scan_for_target",
        "approach_until_range",
        "retreat_and_recover",
    }
)

ALLOWED_ACTIONS = frozenset({"say", "emote", "gesture", "skill"})


@dataclass(slots=True)
class ValidatedPlannerPlan:
    actions: list[dict]
    ttl_ms: int
    dropped_actions: int = 0


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class PlannerValidator:
    """Treat planner output as untrusted and coerce to bounded actions."""

    def __init__(
        self,
        *,
        min_ttl_ms: int = 500,
        max_ttl_ms: int = 5000,
        max_text_len: int = 200,
    ) -> None:
        self._min_ttl_ms = min_ttl_ms
        self._max_ttl_ms = max_ttl_ms
        self._max_text_len = max_text_len

    def validate(self, actions: list[dict], ttl_ms: int) -> ValidatedPlannerPlan:
        safe_actions: list[dict] = []
        dropped = 0

        ttl_ms_i = ttl_ms if isinstance(ttl_ms, int) else self._max_ttl_ms
        ttl_ms_i = max(self._min_ttl_ms, min(self._max_ttl_ms, ttl_ms_i))

        for raw in actions:
            if not isinstance(raw, dict):
                dropped += 1
                continue

            action = str(raw.get("action", "")).strip().lower()
            if action not in ALLOWED_ACTIONS:
                dropped += 1
                continue

            if action == "say":
                text = raw.get("text")
                if not isinstance(text, str):
                    dropped += 1
                    continue
                text = text.strip()
                if not text:
                    dropped += 1
                    continue
                safe_actions.append({"action": "say", "text": text[: self._max_text_len]})
                continue

            if action == "emote":
                name = str(raw.get("name", "")).strip().lower()
                if not name:
                    dropped += 1
                    continue
                intensity = raw.get("intensity", 0.7)
                if not isinstance(intensity, (int, float)):
                    intensity = 0.7
                safe_actions.append(
                    {
                        "action": "emote",
                        "name": name,
                        "intensity": _clamp_float(float(intensity), 0.0, 1.0),
                    }
                )
                continue

            if action == "gesture":
                name = str(raw.get("name", "")).strip().lower()
                if not name:
                    dropped += 1
                    continue
                safe_actions.append({"action": "gesture", "name": name})
                continue

            if action == "skill":
                name = str(raw.get("name", "")).strip().lower()
                if name not in ALLOWED_SKILLS:
                    dropped += 1
                    continue
                safe_actions.append({"action": "skill", "name": name})

        return ValidatedPlannerPlan(actions=safe_actions, ttl_ms=ttl_ms_i, dropped_actions=dropped)
