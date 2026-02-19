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
    ws = WorldState(mode="IDLE", battery_mv=8000, range_mm=1000)
    prompt = format_user_prompt(ws)
    assert "Mode: IDLE" in prompt
    assert "Battery: 8000 mV" in prompt
    assert "Range sensor: 1000 mm" in prompt
    assert "Trigger: heartbeat" in prompt


def test_format_user_prompt_ball_detected():
    ws = WorldState(
        mode="WANDER",
        battery_mv=7500,
        range_mm=600,
        ball_detected=True,
        ball_bearing_deg=15.3,
        trigger="ball_seen",
    )
    prompt = format_user_prompt(ws)
    assert "Ball detected: True" in prompt
    assert "15.3" in prompt
    assert "ball_seen" in prompt


def test_format_user_prompt_faults():
    ws = WorldState(
        mode="ERROR",
        battery_mv=6500,
        range_mm=200,
        faults=["ESTOP", "TILT"],
    )
    prompt = format_user_prompt(ws)
    assert "ESTOP, TILT" in prompt


def test_format_user_prompt_no_vision():
    ws = WorldState(mode="IDLE", battery_mv=8000, range_mm=1000, clear_confidence=-1.0)
    prompt = format_user_prompt(ws)
    assert "n/a" in prompt


def test_format_user_prompt_with_vision():
    ws = WorldState(
        mode="WANDER", battery_mv=8000, range_mm=1000, clear_confidence=0.95
    )
    prompt = format_user_prompt(ws)
    assert "95%" in prompt
