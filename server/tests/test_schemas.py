"""Tests for plan action schemas and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.schemas import (
    EmoteAction,
    GestureAction,
    ModelPlan,
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


@pytest.mark.parametrize(
    "skill_name",
    [
        "patrol_drift",
        "investigate_ball",
        "avoid_obstacle",
        "greet_on_button",
        "scan_for_target",
        "approach_until_range",
        "retreat_and_recover",
    ],
)
def test_skill_valid(skill_name: str):
    a = SkillAction(name=skill_name)
    assert a.action == "skill"
    assert a.name == skill_name


def test_skill_invalid_name_rejected():
    with pytest.raises(ValidationError):
        SkillAction(name="follow_person")


def test_move_action_rejected():
    with pytest.raises(ValidationError):
        ModelPlan(
            actions=[
                {"action": "move", "v_mm_s": 100, "w_mrad_s": 0, "duration_ms": 500}
            ],
            ttl_ms=1000,
        )


# -- PlanResponse -------------------------------------------------------------


def test_model_plan_valid():
    plan = ModelPlan(
        actions=[
            SayAction(text="Hi!"),
            EmoteAction(name="happy", intensity=0.9),
        ],
        ttl_ms=2000,
    )
    assert len(plan.actions) == 2
    assert plan.ttl_ms == 2000


def test_model_plan_empty_actions():
    plan = ModelPlan(actions=[], ttl_ms=1000)
    assert plan.actions == []


def test_model_plan_too_many_actions():
    actions = [SayAction(text=f"line {i}") for i in range(6)]
    with pytest.raises(ValidationError):
        ModelPlan(actions=actions)


def test_model_plan_ttl_bounds():
    with pytest.raises(ValidationError):
        ModelPlan(ttl_ms=499)

    with pytest.raises(ValidationError):
        ModelPlan(ttl_ms=5001)


def test_model_plan_from_json():
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
    plan = ModelPlan.model_validate_json(raw)
    assert len(plan.actions) == 4
    assert plan.actions[0].action == "emote"
    assert plan.actions[1].action == "say"
    assert plan.actions[2].action == "gesture"
    assert plan.actions[3].action == "skill"


def test_model_plan_from_legacy_json():
    """Accept legacy model output that uses name+params action objects."""
    raw = """{
        "actions": [
            {"name": "emote", "params": {"name": "excited", "intensity": 0.9}},
            {"name": "say", "params": {"text": "A ball!"}},
            {"name": "gesture", "params": {"name": "look_at", "params": {"bearing": 15.0}}},
            {"name": "skill", "params": {"name": "investigate_ball"}}
        ],
        "ttl_ms": 2000
    }"""
    plan = ModelPlan.model_validate_json(raw)
    assert len(plan.actions) == 4
    assert plan.actions[0].action == "emote"
    assert plan.actions[0].name == "excited"
    assert plan.actions[1].action == "say"
    assert plan.actions[1].text == "A ball!"
    assert plan.actions[2].action == "gesture"
    assert plan.actions[2].name == "look_at"
    assert plan.actions[2].params["bearing"] == 15.0
    assert plan.actions[3].action == "skill"
    assert plan.actions[3].name == "investigate_ball"


def test_model_plan_from_malformed_action_tags():
    """Recover from malformed action tags emitted by the LLM."""
    raw = """{
        "actions": [
            {"action": "excited", "intensity": 0.9},
            {"text": "Whoa! A ball!"},
            {"action": "look_at", "bearing": -0.1},
            {"action": "investigate_ball"}
        ],
        "ttl_ms": 2000
    }"""
    plan = ModelPlan.model_validate_json(raw)
    assert len(plan.actions) == 4
    assert plan.actions[0].action == "emote"
    assert plan.actions[0].name == "excited"
    assert plan.actions[1].action == "say"
    assert plan.actions[1].text == "Whoa! A ball!"
    assert plan.actions[2].action == "gesture"
    assert plan.actions[2].name == "look_at"
    assert plan.actions[2].params["bearing"] == -0.1
    assert plan.actions[3].action == "skill"
    assert plan.actions[3].name == "investigate_ball"


def test_model_plan_from_malformed_gesture_wrappers():
    """Recover malformed entries tagged as gesture but wrapped as other actions."""
    raw = """{
        "actions": [
            {"action": "gesture", "name": "say", "params": {"text": "Hello there!"}},
            {"action": "gesture", "name": "emote", "params": {"name": "happy", "intensity": 0.8}},
            {"action": "gesture", "name": "skill", "params": {"name": "investigate_ball"}}
        ],
        "ttl_ms": 2000
    }"""
    plan = ModelPlan.model_validate_json(raw)
    assert len(plan.actions) == 3
    assert plan.actions[0].action == "say"
    assert plan.actions[0].text == "Hello there!"
    assert plan.actions[1].action == "emote"
    assert plan.actions[1].name == "happy"
    assert plan.actions[2].action == "skill"
    assert plan.actions[2].name == "investigate_ball"


def test_model_plan_drops_malformed_wrapper_stubs():
    """Drop malformed wrapper-style actions missing required fields."""
    raw = """{
        "actions": [
            {"name": "emote", "intensity": 0.8},
            {"name": "say", "intensity": 0.8},
            {"action": "skill", "name": "patrol_drift"}
        ],
        "ttl_ms": 2000
    }"""
    plan = ModelPlan.model_validate_json(raw)
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "skill"
    assert plan.actions[0].name == "patrol_drift"


def test_plan_json_schema_has_discriminator():
    """Ensure the JSON schema uses the action discriminator."""
    schema = ModelPlan.model_json_schema()
    assert "properties" in schema
    assert "actions" in schema["properties"]


def test_plan_response_requires_metadata():
    with pytest.raises(ValidationError):
        PlanResponse(actions=[], ttl_ms=1000)


def test_plan_response_valid_with_metadata():
    plan = PlanResponse(
        plan_id="abc123",
        robot_id="robot-1",
        seq=42,
        monotonic_ts_ms=1000,
        server_monotonic_ts_ms=1020,
        actions=[{"action": "say", "text": "hello"}],
        ttl_ms=1500,
    )
    assert plan.plan_id == "abc123"
    assert plan.robot_id == "robot-1"
    assert plan.seq == 42


# -- WorldState ---------------------------------------------------------------


def test_world_state_minimal():
    ws = WorldState(
        robot_id="robot-1",
        seq=1,
        monotonic_ts_ms=1234,
        mode="IDLE",
        battery_mv=8000,
        range_mm=1000,
    )
    assert ws.trigger == "heartbeat"
    assert ws.faults == []
    assert ws.ball_confidence == 0.0
    assert ws.vision_age_ms == -1.0


def test_world_state_full():
    ws = WorldState(
        robot_id="robot-1",
        seq=2,
        monotonic_ts_ms=2345,
        mode="WANDER",
        battery_mv=7200,
        range_mm=350,
        faults=["OBSTACLE"],
        clear_confidence=0.6,
        ball_detected=True,
        ball_confidence=0.91,
        ball_bearing_deg=22.5,
        vision_age_ms=88.0,
        speed_l_mm_s=100,
        speed_r_mm_s=95,
        v_capped=80,
        w_capped=0,
        trigger="ball_seen",
    )
    assert ws.ball_detected is True
    assert ws.ball_confidence == 0.91
    assert ws.vision_age_ms == 88.0
    assert ws.trigger == "ball_seen"
