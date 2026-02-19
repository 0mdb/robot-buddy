"""Pydantic models for the plan request/response contract."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

from app.llm.expressions import (
    CANONICAL_EMOTIONS,
    FACE_GESTURES,
    BODY_GESTURES,
    normalize_emotion_name,
    normalize_gesture_name,
)


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
    recent_events: list[str] = Field(default_factory=list)
    planner_active_skill: str = "patrol_drift"
    face_talking: bool = False
    face_listening: bool = False


# ---------------------------------------------------------------------------
# Plan actions (outgoing to supervisor)
# ---------------------------------------------------------------------------


class SayAction(BaseModel):
    action: Literal["say"] = "say"
    text: str = Field(max_length=200)


VALID_EMOTIONS = frozenset(CANONICAL_EMOTIONS)
VALID_GESTURES = frozenset(FACE_GESTURES + BODY_GESTURES)


class EmoteAction(BaseModel):
    action: Literal["emote"] = "emote"
    name: str
    intensity: float = Field(ge=0.0, le=1.0, default=0.5)

    @field_validator("name")
    @classmethod
    def _validate_emotion_name(cls, value: str) -> str:
        normalized = normalize_emotion_name(value)
        if normalized is None:
            allowed = ", ".join(CANONICAL_EMOTIONS)
            raise ValueError(f"unsupported emotion '{value}'. allowed: {allowed}")
        return normalized


class GestureAction(BaseModel):
    action: Literal["gesture"] = "gesture"
    name: str
    params: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_gesture_name(cls, value: str) -> str:
        normalized = normalize_gesture_name(value, allow_body=True)
        if normalized is None:
            allowed = ", ".join(FACE_GESTURES + BODY_GESTURES)
            raise ValueError(f"unsupported gesture '{value}'. allowed: {allowed}")
        return normalized


class SkillAction(BaseModel):
    action: Literal["skill"] = "skill"
    name: Literal[
        "patrol_drift",
        "investigate_ball",
        "avoid_obstacle",
        "greet_on_button",
    ]


PlanAction = Annotated[
    Union[SayAction, EmoteAction, GestureAction, SkillAction],
    Field(discriminator="action"),
]


class PlanResponse(BaseModel):
    """Bounded performance plan returned by the LLM."""

    actions: list[PlanAction] = Field(default_factory=list, max_length=5)
    ttl_ms: int = Field(default=2000, ge=500, le=5000)
