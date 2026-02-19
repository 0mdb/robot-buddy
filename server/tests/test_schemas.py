"""Tests for plan action schemas and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.schemas import (
    EmoteAction,
    GestureAction,
    PlanResponse,
    SayAction,
    SkillAction,
    WorldState,
)


# -- SayAction ---------------------------------------------------------------


def test_say_valid():
    a = SayAction(text="Hello friend!")
    assert a.action == "say"
    assert a.text == "Hello friend!"


def test_say_too_long():
    with pytest.raises(ValidationError):
        SayAction(text="x" * 201)


# -- EmoteAction --------------------------------------------------------------


def test_emote_valid():
    a = EmoteAction(name="happy", intensity=0.8)
    assert a.action == "emote"
    assert a.intensity == 0.8


def test_emote_intensity_clamped():
    with pytest.raises(ValidationError):
        EmoteAction(name="happy", intensity=1.5)

    with pytest.raises(ValidationError):
        EmoteAction(name="happy", intensity=-0.1)


def test_emote_default_intensity():
    a = EmoteAction(name="curious")
    assert a.intensity == 0.5


def test_emote_invalid_name_rejected():
    with pytest.raises(ValidationError):
        EmoteAction(name="ecstatic", intensity=0.6)


def test_emote_alias_normalized():
    a = EmoteAction(name="tired", intensity=0.4)
    assert a.name == "sleepy"


# -- GestureAction ------------------------------------------------------------


def test_gesture_valid():
    a = GestureAction(name="look_at", params={"bearing": 15.2})
    assert a.action == "gesture"
    assert a.params["bearing"] == 15.2


def test_gesture_empty_params():
    a = GestureAction(name="nod")
    assert a.params == {}


def test_gesture_invalid_name_rejected():
    with pytest.raises(ValidationError):
        GestureAction(name="moonwalk")


def test_gesture_alias_normalized():
    a = GestureAction(name="x-eyes")
    assert a.name == "x_eyes"


# -- SkillAction --------------------------------------------------------------


def test_skill_valid():
    a = SkillAction(name="investigate_ball")
    assert a.action == "skill"
    assert a.name == "investigate_ball"


def test_skill_invalid_name_rejected():
    with pytest.raises(ValidationError):
        SkillAction(name="follow_person")


def test_move_action_rejected():
    with pytest.raises(ValidationError):
        PlanResponse(
            actions=[{"action": "move", "v_mm_s": 100, "w_mrad_s": 0, "duration_ms": 500}],
            ttl_ms=1000,
        )


# -- PlanResponse -------------------------------------------------------------


def test_plan_response_valid():
    plan = PlanResponse(
        actions=[
            SayAction(text="Hi!"),
            EmoteAction(name="happy", intensity=0.9),
        ],
        ttl_ms=2000,
    )
    assert len(plan.actions) == 2
    assert plan.ttl_ms == 2000


def test_plan_response_empty_actions():
    plan = PlanResponse(actions=[], ttl_ms=1000)
    assert plan.actions == []


def test_plan_response_too_many_actions():
    actions = [SayAction(text=f"line {i}") for i in range(6)]
    with pytest.raises(ValidationError):
        PlanResponse(actions=actions)


def test_plan_response_ttl_bounds():
    with pytest.raises(ValidationError):
        PlanResponse(ttl_ms=499)

    with pytest.raises(ValidationError):
        PlanResponse(ttl_ms=5001)


def test_plan_response_from_json():
    """Simulate parsing a raw JSON string from the LLM."""
    raw = """{
        "actions": [
            {"action": "emote", "name": "excited", "intensity": 0.9},
            {"action": "say", "text": "A ball!"},
            {"action": "gesture", "name": "look_at", "params": {"bearing": 15.0}},
            {"action": "skill", "name": "investigate_ball"}
        ],
        "ttl_ms": 2000
    }"""
    plan = PlanResponse.model_validate_json(raw)
    assert len(plan.actions) == 4
    assert plan.actions[0].action == "emote"
    assert plan.actions[1].action == "say"
    assert plan.actions[2].action == "gesture"
    assert plan.actions[3].action == "skill"


def test_plan_json_schema_has_discriminator():
    """Ensure the JSON schema uses the action discriminator."""
    schema = PlanResponse.model_json_schema()
    assert "properties" in schema
    assert "actions" in schema["properties"]


# -- WorldState ---------------------------------------------------------------


def test_world_state_minimal():
    ws = WorldState(mode="IDLE", battery_mv=8000, range_mm=1000)
    assert ws.trigger == "heartbeat"
    assert ws.faults == []


def test_world_state_full():
    ws = WorldState(
        mode="WANDER",
        battery_mv=7200,
        range_mm=350,
        faults=["OBSTACLE"],
        clear_confidence=0.6,
        ball_detected=True,
        ball_bearing_deg=22.5,
        speed_l_mm_s=100,
        speed_r_mm_s=95,
        v_capped=80,
        w_capped=0,
        trigger="ball_seen",
    )
    assert ws.ball_detected is True
    assert ws.trigger == "ball_seen"
