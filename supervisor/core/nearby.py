"""Motion near people and animals: governor layer 8 (Vantage SIM-INTERACTION, stage 4).

A speed cap and a minimum standoff by the nearest present member's kind. It is the supervisor's
layer, additional to the other seven and never replacing one, so it holds whatever WANDER, the
planner, or a teleop client asks for. It can only lower speed.

Operator decisions (2026-11-10): tunable params that start conservative, with floors no tuning
can cross; the HUD names it NEARBY; positions arrive through POST /api/audience -- the sim's
oracle today, a detection worker later. Fixed policy, not tunables:

- An unknown kind, or a low-confidence detection, counts as a child (the most protective).
- Inside a member's standoff, Buddy does not move toward it: forward motion is stopped for a
  member ahead, reversing for one behind. Turning and moving away stay allowed.
- An estimate is held for ``HOLD_MS`` after it arrives (people do not vanish between frames),
  then dropped; with no estimate the layer does nothing, which is today's behaviour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

KINDS = ("kid", "adult", "animal", "unknown")
MIN_CONFIDENCE = 0.6
HOLD_MS = 2000.0
# A member within this many degrees of straight ahead (or straight behind) is "in the way".
IN_PATH_DEG = 60.0


@dataclass(frozen=True, slots=True)
class Member:
    kind: str
    range_mm: int
    # Robot frame, degrees: 0 straight ahead, positive to the left (CCW), +-180 behind.
    bearing_deg: float
    confidence: float = 1.0

    def policy_kind(self) -> str:
        """The kind whose limits apply: unknown or unsure is a child."""
        if (
            self.kind not in ("kid", "adult", "animal")
            or self.confidence < MIN_CONFIDENCE
        ):
            return "kid"
        return self.kind


# key -> (type, floor, max, step, doc). Defaults below. The floor is the point: no param change,
# from the dashboard or a tuner, can make Buddy faster or closer than this near anyone.
NEARBY_TUNABLES: dict[str, tuple[str, float, float, float, str]] = {
    "kid_near_mm": (
        "int",
        1000,
        4000,
        50,
        "Within this range of a child, speed is capped",
    ),
    "kid_cap_mm_s": ("int", 50, 250, 10, "Speed cap near a child (mm/s)"),
    "kid_standoff_mm": (
        "int",
        500,
        2000,
        50,
        "Never move toward a child closer than this",
    ),
    "adult_near_mm": (
        "int",
        600,
        3000,
        50,
        "Within this range of an adult, speed is capped",
    ),
    "adult_cap_mm_s": ("int", 80, 350, 10, "Speed cap near an adult (mm/s)"),
    "adult_standoff_mm": (
        "int",
        300,
        1500,
        50,
        "Never move toward an adult closer than this",
    ),
    "animal_near_mm": (
        "int",
        1000,
        4000,
        50,
        "Within this range of an animal, speed is capped",
    ),
    "animal_cap_mm_s": ("int", 50, 250, 10, "Speed cap near an animal (mm/s)"),
    "animal_standoff_mm": (
        "int",
        600,
        2500,
        50,
        "Never move toward an animal closer than this",
    ),
}

# Conservative starting values (operator, 2026-11-10).
_DEFAULTS: dict[str, int] = {
    "kid_near_mm": 1500,
    "kid_cap_mm_s": 120,
    "kid_standoff_mm": 800,
    "adult_near_mm": 1000,
    "adult_cap_mm_s": 200,
    "adult_standoff_mm": 500,
    "animal_near_mm": 1500,
    "animal_cap_mm_s": 100,
    "animal_standoff_mm": 1000,
}

_policy: dict[str, int] = dict(_DEFAULTS)


def nearby_defaults() -> dict[str, int]:
    return dict(_DEFAULTS)


def set_tunable(key: str, value: float) -> None:
    """Set one tunable, clamped to its floor and max: a tuner can never cross the floor."""
    if key not in NEARBY_TUNABLES:
        raise KeyError(key)
    _, lo, hi, _, _ = NEARBY_TUNABLES[key]
    _policy[key] = int(min(max(float(value), lo), hi))


def reset() -> None:
    _policy.clear()
    _policy.update(_DEFAULTS)


def current() -> dict[str, int]:
    return dict(_policy)


def _in_path(bearing_deg: float, reversing: bool) -> bool:
    b = (bearing_deg + 180.0) % 360.0 - 180.0
    return abs(b) >= 180.0 - IN_PATH_DEG if reversing else abs(b) <= IN_PATH_DEG


def limit(v_mm_s: int, members: list[Member]) -> tuple[int, str | None]:
    """The forward speed this layer allows, and the reason if it bound (else None).

    ``v_mm_s`` is the speed after the earlier layers. Only ``v`` is limited: turning in place
    is how Buddy gets away from someone, so it is left to the other layers."""
    allowed = abs(v_mm_s)
    reason: str | None = None
    reversing = v_mm_s < 0
    for m in members:
        kind = m.policy_kind()
        near = _policy[f"{kind}_near_mm"]
        if m.range_mm > near:
            continue
        cap = _policy[f"{kind}_cap_mm_s"]
        standoff = _policy[f"{kind}_standoff_mm"]
        if m.range_mm <= standoff and _in_path(m.bearing_deg, reversing):
            cap = 0
        if cap < allowed:
            allowed = cap
            reason = f"nearby={kind}@{m.range_mm}mm"
    return int(math.copysign(allowed, v_mm_s)) if allowed else 0, reason
