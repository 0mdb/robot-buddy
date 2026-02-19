"""Tests for prompt formatting."""

from __future__ import annotations

from app.llm.prompts import SYSTEM_PROMPT, format_user_prompt
from app.llm.schemas import WorldState


def test_system_prompt_not_empty():
    assert len(SYSTEM_PROMPT) > 100


def test_system_prompt_mentions_actions():
    assert "say(" in SYSTEM_PROMPT
    assert "emote(" in SYSTEM_PROMPT
    assert "gesture(" in SYSTEM_PROMPT
    assert "skill(" in SYSTEM_PROMPT
    assert "move(" not in SYSTEM_PROMPT


def test_system_prompt_mentions_safety():
    assert (
        "kid-friendly" in SYSTEM_PROMPT.lower()
        or "age-appropriate" in SYSTEM_PROMPT.lower()
    )


def test_format_user_prompt_basic():
    ws = WorldState(
        robot_id="robot-1",
        seq=1,
        monotonic_ts_ms=1000,
        mode="IDLE",
        battery_mv=8000,
        range_mm=1000,
    )
    prompt = format_user_prompt(ws)
    assert "Mode: IDLE" in prompt
    assert "Battery: 8000 mV" in prompt
    assert "Range sensor: 1000 mm" in prompt
    assert "Trigger: heartbeat" in prompt


def test_format_user_prompt_ball_detected():
    ws = WorldState(
        robot_id="robot-1",
        seq=2,
        monotonic_ts_ms=1100,
        mode="WANDER",
        battery_mv=7500,
        range_mm=600,
        ball_detected=True,
        ball_confidence=0.93,
        ball_bearing_deg=15.3,
        vision_age_ms=120.0,
        planner_active_skill="investigate_ball",
        recent_events=["vision.ball_acquired", "mode.changed"],
        trigger="ball_seen",
    )
    prompt = format_user_prompt(ws)
    assert "Ball detected: True" in prompt
    assert "confidence: 0.93" in prompt
    assert "15.3" in prompt
    assert "Vision age: 120 ms" in prompt
    assert "Active skill: investigate_ball" in prompt
    assert "vision.ball_acquired" in prompt
    assert "ball_seen" in prompt


def test_format_user_prompt_faults():
    ws = WorldState(
        robot_id="robot-1",
        seq=3,
        monotonic_ts_ms=1200,
        mode="ERROR",
        battery_mv=6500,
        range_mm=200,
        faults=["ESTOP", "TILT"],
    )
    prompt = format_user_prompt(ws)
    assert "ESTOP, TILT" in prompt


def test_format_user_prompt_no_vision():
    ws = WorldState(
        robot_id="robot-1",
        seq=4,
        monotonic_ts_ms=1300,
        mode="IDLE",
        battery_mv=8000,
        range_mm=1000,
        clear_confidence=-1.0,
    )
    prompt = format_user_prompt(ws)
    assert "n/a" in prompt


def test_format_user_prompt_with_vision():
    ws = WorldState(
        robot_id="robot-1",
        seq=5,
        monotonic_ts_ms=1400,
        mode="WANDER",
        battery_mv=8000,
        range_mm=1000,
        clear_confidence=0.95,
    )
    prompt = format_user_prompt(ws)
    assert "95%" in prompt
