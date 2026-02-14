"""Pydantic models for the plan request/response contract."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Emotions — shared vocabulary for face, speech prosody, and mood
# ---------------------------------------------------------------------------

EMOTIONS: list[str] = [
    "happy",
    "sad",
    "surprised",
    "curious",
    "excited",
    "sleepy",
    "scared",
    "neutral",
    "love",
]

# ---------------------------------------------------------------------------
# Sound-effect identifiers (pre-baked audio on the Pi)
# ---------------------------------------------------------------------------

SFX_NAMES: list[str] = [
    "boop",
    "oof",
    "wheee",
    "beep_beep",
    "yawn",
    "giggle",
    "gasp",
    "hum",
]


# ---------------------------------------------------------------------------
# Mood (persistent emotional colouring)
# ---------------------------------------------------------------------------


class Mood(BaseModel):
    """Russell circumplex mood: valence (sad↔happy) × arousal (sleepy↔excited)."""

    valence: float = Field(ge=-1.0, le=1.0, default=0.0)
    arousal: float = Field(ge=-1.0, le=1.0, default=0.0)


# ---------------------------------------------------------------------------
# World state (incoming from supervisor)
# ---------------------------------------------------------------------------


class WorldState(BaseModel):
    """Compact snapshot of the robot's world, sent by the supervisor."""

    mode: str
    battery_mv: int
    range_mm: int
    faults: list[str] = Field(default_factory=list)
    clear_confidence: float = -1.0
    ball_detected: bool = False
    ball_bearing_deg: float = 0.0
    speed_l_mm_s: int = 0
    speed_r_mm_s: int = 0
    v_capped: float = 0.0
    w_capped: float = 0.0
    trigger: str = "heartbeat"
    mood: Mood = Field(default_factory=Mood)
    recent_actions: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Last few action summaries for continuity, e.g. ['say:Whoa!', 'emote:excited']",
    )


# ---------------------------------------------------------------------------
# Plan actions (outgoing to supervisor)
# ---------------------------------------------------------------------------


class SayAction(BaseModel):
    action: Literal["say"] = "say"
    text: str = Field(max_length=200)
    emotion: str = Field(default="neutral", description="Prosody hint for TTS")
    intensity: float = Field(
        ge=0.0, le=1.0, default=0.5, description="Emotion strength for TTS prosody"
    )


class EmoteAction(BaseModel):
    action: Literal["emote"] = "emote"
    name: str
    intensity: float = Field(ge=0.0, le=1.0, default=0.5)


class SfxAction(BaseModel):
    """Trigger a pre-baked sound effect (low-latency, no TTS needed)."""

    action: Literal["sfx"] = "sfx"
    name: str = Field(description="Sound effect identifier")


class GestureAction(BaseModel):
    action: Literal["gesture"] = "gesture"
    name: str
    params: dict = Field(default_factory=dict)


class MoveAction(BaseModel):
    action: Literal["move"] = "move"
    v_mm_s: int = Field(ge=-300, le=300, default=0)
    w_mrad_s: int = Field(ge=-500, le=500, default=0)
    duration_ms: int = Field(ge=0, le=3000, default=1000)


PlanAction = Annotated[
    Union[SayAction, EmoteAction, SfxAction, GestureAction, MoveAction],
    Field(discriminator="action"),
]


class PlanResponse(BaseModel):
    """Bounded performance plan returned by the LLM."""

    actions: list[PlanAction] = Field(default_factory=list, max_length=5)
    ttl_ms: int = Field(default=2000, ge=500, le=5000)
