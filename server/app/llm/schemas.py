"""Pydantic models for the plan request/response contract."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


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


# ---------------------------------------------------------------------------
# Plan actions (outgoing to supervisor)
# ---------------------------------------------------------------------------


class SayAction(BaseModel):
    action: Literal["say"] = "say"
    text: str = Field(max_length=200)


VALID_EMOTIONS = frozenset({
    "neutral", "happy", "excited", "curious", "sad", "scared",
    "angry", "surprised", "sleepy", "love", "silly", "thinking",
})


class EmoteAction(BaseModel):
    action: Literal["emote"] = "emote"
    name: str
    intensity: float = Field(ge=0.0, le=1.0, default=0.5)


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
    Union[SayAction, EmoteAction, GestureAction, MoveAction],
    Field(discriminator="action"),
]


class PlanResponse(BaseModel):
    """Bounded performance plan returned by the LLM."""

    actions: list[PlanAction] = Field(default_factory=list, max_length=5)
    ttl_ms: int = Field(default=2000, ge=500, le=5000)
