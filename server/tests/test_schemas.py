"""Tests for plan action schemas and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.schemas import (
    EmoteAction,
    GestureAction,
    Mood,
    MoveAction,
    PlanResponse,
    SayAction,
    SfxAction,
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


def test_say_emotion_defaults():
    a = SayAction(text="Hi!")
    assert a.emotion == "neutral"
    assert a.intensity == 0.5


def test_say_with_emotion():
    a = SayAction(text="A ball!", emotion="excited", intensity=0.9)
    assert a.emotion == "excited"
    assert a.intensity == 0.9


def test_say_intensity_bounds():
    with pytest.raises(ValidationError):
        SayAction(text="Hi!", intensity=1.5)

    with pytest.raises(ValidationError):
        SayAction(text="Hi!", intensity=-0.1)


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


# -- SfxAction ----------------------------------------------------------------


def test_sfx_valid():
    a = SfxAction(name="boop")
    assert a.action == "sfx"
    assert a.name == "boop"


def test_sfx_requires_name():
    with pytest.raises(ValidationError):
        SfxAction()


# -- GestureAction ------------------------------------------------------------


def test_gesture_valid():
    a = GestureAction(name="look_at", params={"bearing": 15.2})
    assert a.action == "gesture"
    assert a.params["bearing"] == 15.2


def test_gesture_empty_params():
    a = GestureAction(name="nod")
    assert a.params == {}


# -- MoveAction ---------------------------------------------------------------


def test_move_valid():
    a = MoveAction(v_mm_s=200, w_mrad_s=-100, duration_ms=2000)
    assert a.action == "move"


def test_move_speed_bounds():
    with pytest.raises(ValidationError):
        MoveAction(v_mm_s=301)

    with pytest.raises(ValidationError):
        MoveAction(v_mm_s=-301)

    with pytest.raises(ValidationError):
        MoveAction(w_mrad_s=501)


def test_move_duration_bounds():
    with pytest.raises(ValidationError):
        MoveAction(duration_ms=3001)

    with pytest.raises(ValidationError):
        MoveAction(duration_ms=-1)


# -- Mood ---------------------------------------------------------------------


def test_mood_defaults():
    m = Mood()
    assert m.valence == 0.0
    assert m.arousal == 0.0


def test_mood_bounds():
    m = Mood(valence=1.0, arousal=-1.0)
    assert m.valence == 1.0

    with pytest.raises(ValidationError):
        Mood(valence=1.5)

    with pytest.raises(ValidationError):
        Mood(arousal=-1.1)


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
            {"action": "say", "text": "A ball!", "emotion": "excited", "intensity": 0.8},
            {"action": "sfx", "name": "boop"},
            {"action": "gesture", "name": "look_at", "params": {"bearing": 15.0}},
            {"action": "move", "v_mm_s": 150, "w_mrad_s": 50, "duration_ms": 1500}
        ],
        "ttl_ms": 2000
    }"""
    plan = PlanResponse.model_validate_json(raw)
    assert len(plan.actions) == 5
    assert plan.actions[0].action == "emote"
    assert plan.actions[1].action == "say"
    assert plan.actions[1].emotion == "excited"
    assert plan.actions[2].action == "sfx"
    assert plan.actions[3].action == "gesture"
    assert plan.actions[4].action == "move"


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
    assert ws.mood.valence == 0.0
    assert ws.mood.arousal == 0.0
    assert ws.recent_actions == []


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
        mood={"valence": 0.7, "arousal": 0.5},
        recent_actions=["say:Whoa!", "emote:excited"],
    )
    assert ws.ball_detected is True
    assert ws.trigger == "ball_seen"
    assert ws.mood.valence == 0.7
    assert ws.recent_actions == ["say:Whoa!", "emote:excited"]
