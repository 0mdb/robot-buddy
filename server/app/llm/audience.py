"""Audience profiles and the audience block (~/vantage/docs/SIM-INTERACTION.md, stage 0).

A profile is data (``profiles/<id>.toml``): who Buddy is talking to, by kind and age. Both the
conversation prompt and the planner prompt take their audience wording from the default profile,
so the age range has one source.

The supervisor (or a test harness, as an oracle) may attach an ``audience`` dict to the
``/converse`` profile message, shaped like the design doc's audience estimate::

    {"present": [{"kind": "kid", "confidence": 0.9, "sources": ["oracle"], "age": 7}],
     "speaking": 0}

The fallback rules are fixed policy, not tunables:

1. Unknown or low-confidence is the youngest kid.
2. Several present means the youngest present: an adult beside a child does not switch modes.
3. Animals never get conversation (enforced from stage 2; stage 0 only reports it).
4. Recognition never loosens safety: the content rules are in the prompt, not in a profile.

Roster ``member`` ids are accepted and deliberately never rendered into a prompt. Names reach the
model only through the roster (stage 3), never through this block.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

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

    @property
    def who(self) -> str:
        """How the prompts name this audience, e.g. ``children aged 4-8``."""
        if self.kind == "kid" and self.age_min is not None and self.age_max is not None:
            return f"children aged {self.age_min}-{self.age_max}"
        return {"kid": "children", "adult": "adults", "animal": "animals"}.get(
            self.kind, "people"
        )


@cache
def load_profile(profile_id: str) -> AudienceProfile:
    path = _PROFILE_DIR / f"{profile_id}.toml"
    data = tomllib.loads(path.read_text())
    if data.get("id") != profile_id:
        raise ValueError(f"{path}: id {data.get('id')!r} does not match the file name")
    if data.get("kind") not in KINDS:
        raise ValueError(f"{path}: kind must be one of {KINDS}")
    return AudienceProfile(
        id=profile_id,
        kind=data["kind"],
        age_min=data.get("age_min"),
        age_max=data.get("age_max"),
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
    return Audience(tuple(present), speaking)


def _effective_kind(m: Member) -> str:
    """Rule 1: a low-confidence detection is unknown, and unknown counts as the youngest kid."""
    if m.kind == "unknown" or m.confidence < MIN_CONFIDENCE:
        return "kid"
    return m.kind


def resolve_profile(audience: Audience | None) -> AudienceProfile:
    """Pick the profile the fallback rules allow. Stage 0 has one profile, so this is always it;
    the rules are here so stage 2 only adds profile files."""
    default = load_profile(DEFAULT_PROFILE_ID)
    if audience is None or not audience.present:
        return default
    kinds = {_effective_kind(m) for m in audience.present}
    if "kid" in kinds:  # rule 2: any child present governs
        return default
    if kinds == {"adult"} and "adult" in available_profiles():
        return load_profile("adult")
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
