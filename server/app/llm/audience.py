"""Audience profiles and the audience block (~/vantage/docs/SIM-INTERACTION.md, stages 0 and 2).

A profile is data (``profiles/<id>.toml``): who Buddy is talking to, by kind and age. Both the
conversation prompt and the planner prompt take their audience wording from the default profile,
so the age range has one source.

The supervisor (or a test harness, as an oracle) may attach an ``audience`` dict to the
``/converse`` profile message, shaped like the design doc's audience estimate::

    {"present": [{"kind": "kid", "confidence": 0.9, "sources": ["oracle"], "age": 7}],
     "speaking": 0}

The fallback rules are fixed policy, not tunables:

1. Unknown or low-confidence is a kid; a kid of unknown age gets the generic child profile
   (the youngest *enrolled* child once the roster exists, stage 3).
2. Several present means the youngest present: an adult beside a child does not switch modes.
3. Animals never get conversation: the animal profile answers in robot sounds only.
4. Recognition never loosens safety: the content rules are in the prompt, not in a profile.

Roster ``member`` ids are accepted and deliberately never rendered into a prompt. Names reach the
model only through the roster (stage 3), never through this block.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

_PROFILE_DIR = Path(__file__).parent / "profiles"

DEFAULT_PROFILE_ID = "child"

KINDS = ("kid", "adult", "animal", "unknown")

# Below this, a detection counts as unknown (rule 1). A policy floor, not a tuning knob.
MIN_CONFIDENCE = 0.6


@dataclass(frozen=True, slots=True)
class AudienceProfile:
    id: str
    kind: str
    age_min: int | None = None
    age_max: int | None = None
    intro: str = ""
    speech: tuple[str, ...] = ()
    examples: tuple[dict[str, Any], ...] = ()

    @property
    def who(self) -> str:
        """How the prompts name this audience, e.g. ``children aged 4-8``."""
        if self.kind == "kid" and self.age_min is not None and self.age_max is not None:
            return f"children aged {self.age_min}-{self.age_max}"
        return {"kid": "children", "adult": "adults", "animal": "animals"}.get(
            self.kind, "people"
        )

    @property
    def intro_text(self) -> str:
        return self.intro.replace("{who}", self.who)


@cache
def load_profile(profile_id: str) -> AudienceProfile:
    path = _PROFILE_DIR / f"{profile_id}.toml"
    data = tomllib.loads(path.read_text())
    if data.get("id") != profile_id:
        raise ValueError(f"{path}: id {data.get('id')!r} does not match the file name")
    if data.get("kind") not in KINDS:
        raise ValueError(f"{path}: kind must be one of {KINDS}")
    for key in ("intro", "speech"):
        if not data.get(key):
            raise ValueError(f"{path}: {key} is required")
    for ex in data.get("example", []):
        if not ex.get("user") or not ex.get("text"):
            raise ValueError(f"{path}: every [[example]] needs user and text")
    return AudienceProfile(
        id=profile_id,
        kind=data["kind"],
        age_min=data.get("age_min"),
        age_max=data.get("age_max"),
        intro=data["intro"],
        speech=tuple(data["speech"]),
        examples=tuple(data.get("example", [])),
    )


def available_profiles() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in _PROFILE_DIR.glob("*.toml")))


@dataclass(frozen=True, slots=True)
class Member:
    kind: str
    confidence: float
    age: int | None
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Audience:
    present: tuple[Member, ...]
    speaking: int | None
    # From the robot's opt-in household roster: only the youngest enrolled child's age.
    youngest_kid_age: int | None = None


def parse_audience(raw: object) -> Audience | None:
    """Parse an audience dict leniently. Anything malformed is dropped, not guessed."""
    if not isinstance(raw, dict):
        return None
    present: list[Member] = []
    for m in raw.get("present") or []:
        if not isinstance(m, dict):
            continue
        kind = m.get("kind") if m.get("kind") in KINDS else "unknown"
        try:
            confidence = min(1.0, max(0.0, float(m.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        age = m.get("age")
        age = (
            age
            if isinstance(age, int) and not isinstance(age, bool) and 0 < age < 120
            else None
        )
        sources = tuple(str(s) for s in m.get("sources") or [] if isinstance(s, str))[
            :4
        ]
        present.append(Member(kind, confidence, age, sources))
    speaking = raw.get("speaking")
    if not (isinstance(speaking, int) and 0 <= speaking < len(present)):
        speaking = None
    household = raw.get("household")
    youngest = (
        household.get("youngest_kid_age") if isinstance(household, dict) else None
    )
    if not (
        isinstance(youngest, int)
        and not isinstance(youngest, bool)
        and 0 < youngest < 18
    ):
        youngest = None
    return Audience(tuple(present), speaking, youngest)


def _effective_kind(m: Member) -> str:
    """Rule 1: a low-confidence detection is unknown, and unknown counts as the youngest kid."""
    if m.kind == "unknown" or m.confidence < MIN_CONFIDENCE:
        return "kid"
    return m.kind


def _kid_profile_for_age(age: int) -> AudienceProfile:
    """The age-banded kid profile for an age; outside every band, the nearest band."""
    bands = [
        p
        for p in (
            load_profile(i) for i in available_profiles() if i != DEFAULT_PROFILE_ID
        )
        if p.kind == "kid" and p.age_min is not None and p.age_max is not None
    ]
    if not bands:
        return load_profile(DEFAULT_PROFILE_ID)
    for p in bands:
        if p.age_min <= age <= p.age_max:  # type: ignore[operator]
            return p
    return min(bands, key=lambda p: min(abs(age - p.age_min), abs(age - p.age_max)))  # type: ignore[operator]


def resolve_profile(audience: Audience | None) -> AudienceProfile:
    """Pick the profile the fallback rules allow.

    - Nothing known, or a child whose age is not known: the youngest enrolled child's profile
      when the household roster says who that is, else the generic child profile (rule 1).
    - Any child present: the profile for the youngest child present (rule 2).
    - Only confident adults (animals may be there too): adult.
    - Only animals: animal (rule 3).
    """
    default = load_profile(DEFAULT_PROFILE_ID)
    if audience is not None and audience.youngest_kid_age is not None:
        default = _kid_profile_for_age(audience.youngest_kid_age)
    if audience is None or not audience.present:
        return default
    kids = [m for m in audience.present if _effective_kind(m) == "kid"]
    if kids:
        ages = [m.age if m.kind == "kid" else None for m in kids]
        if any(a is None for a in ages):
            return default
        # Rule 2 is the youngest *present*; the roster only fills in an unknown (rule 1).
        return _kid_profile_for_age(min(a for a in ages if a is not None))
    kinds = {_effective_kind(m) for m in audience.present}
    if "adult" in kinds:
        return load_profile("adult")
    if kinds == {"animal"}:
        return load_profile("animal")
    return default


def render_audience_block(audience: Audience | None) -> str:
    """The AUDIENCE lines for the CURRENT STATE block. Empty when nothing was sent, so a robot
    that sends no audience gets exactly today's prompt."""
    if audience is None:
        return ""
    profile = resolve_profile(audience)
    if not audience.present:
        who = "nobody detected"
    else:
        parts = []
        for i, m in enumerate(audience.present):
            label = m.kind if m.age is None else f"{m.kind}, {m.age}"
            if _effective_kind(m) != m.kind:
                label += ", unsure"
            if i == audience.speaking:
                label += ", speaking"
            parts.append(label)
        who = "; ".join(parts)
    return f"AUDIENCE: {who}. Speak for {profile.who}."
