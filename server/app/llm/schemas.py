"""Pydantic models for the plan request/response contract."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

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
VALID_SKILLS = frozenset(
    {"patrol_drift", "investigate_ball", "avoid_obstacle", "greet_on_button"}
)


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_actions(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        actions = data.get("actions")
        if not isinstance(actions, list):
            return data

        normalized: list[object] = []
        changed = False
        for raw in actions:
            coerced = cls._coerce_action(raw)
            if coerced is None:
                normalized.append(raw)
                continue
            if coerced is not raw:
                changed = True
            normalized.append(coerced)

        if not changed:
            return data

        patched = dict(data)
        patched["actions"] = normalized
        return patched

    @classmethod
    def _coerce_action(cls, raw: object) -> dict | None:
        if isinstance(raw, BaseModel):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            return None

        def _tok(value: object) -> str:
            return value.strip().lower() if isinstance(value, str) else ""

        wrapper_name = _tok(raw.get("name"))
        explicit_action = _tok(raw.get("action"))
        params = raw.get("params")
        params_dict = params if isinstance(params, dict) else {}

        # Flatten common legacy shape: {"name":"emote","params":{"name":"happy",...}}
        # while preserving non-wrapper names.
        payload: dict[str, object] = dict(params_dict)
        for key, value in raw.items():
            if key in {"params", "name"}:
                continue
            payload[key] = value
        if wrapper_name and wrapper_name not in {"say", "emote", "gesture", "skill"}:
            payload.setdefault("name", wrapper_name)

        action_kind = explicit_action
        inferred_name: str | None = None

        if not action_kind and wrapper_name in {"say", "emote", "gesture", "skill"}:
            action_kind = wrapper_name

        # Recover malformed tags where action holds a concrete symbol (emotion/gesture/skill).
        if action_kind not in {"say", "emote", "gesture", "skill"}:
            token = action_kind or _tok(payload.get("name"))
            if token in VALID_SKILLS:
                action_kind = "skill"
                inferred_name = token
            else:
                emo = normalize_emotion_name(token)
                if emo is not None:
                    action_kind = "emote"
                    inferred_name = emo
                else:
                    gest = normalize_gesture_name(token, allow_body=True)
                    if gest is not None:
                        action_kind = "gesture"
                        inferred_name = gest
                    elif isinstance(payload.get("text"), str):
                        action_kind = "say"

        if action_kind == "say":
            text = payload.get("text")
            if not isinstance(text, str):
                return None
            text = text.strip()
            if not text:
                return None
            return {"action": "say", "text": text}

        if action_kind == "emote":
            name = inferred_name or normalize_emotion_name(_tok(payload.get("name")))
            if name is None:
                return None
            intensity_raw = payload.get("intensity", 0.5)
            intensity = (
                float(intensity_raw)
                if isinstance(intensity_raw, (int, float))
                else 0.5
            )
            return {"action": "emote", "name": name, "intensity": intensity}

        if action_kind == "gesture":
            name = inferred_name or normalize_gesture_name(
                _tok(payload.get("name")), allow_body=True
            )
            if name is None and "bearing" in payload:
                name = "look_at"
            if name is None:
                return None

            gesture_params: dict[str, object] = {}
            nested_params = payload.get("params")
            if isinstance(nested_params, dict):
                gesture_params.update(nested_params)

            for key, value in payload.items():
                if key in {"action", "name", "text", "intensity", "emotion", "params"}:
                    continue
                gesture_params.setdefault(key, value)
            return {"action": "gesture", "name": name, "params": gesture_params}

        if action_kind == "skill":
            name = inferred_name or _tok(payload.get("name"))
            if name not in VALID_SKILLS:
                return None
            return {"action": "skill", "name": name}

        return None
