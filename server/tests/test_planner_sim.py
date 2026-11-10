"""L1 planner suite, against a fake model (SIM-INTERACTION, the planner's say() path)."""

from __future__ import annotations

import json

import pytest

from app.eval.planner_sim import (
    SCENARIOS,
    STALE_EVENTS,
    ball_gate_open,
    by_id,
    check_plan,
    format_report,
    run_scenario,
    world,
)
from app.llm.schemas import ModelPlan, WorldState


def plan(*actions: dict) -> ModelPlan:
    return ModelPlan.model_validate({"actions": list(actions), "ttl_ms": 2000})


def say(text: str) -> dict:
    return {"action": "say", "text": text}


def fake(*replies: str, seen: list | None = None):
    it = iter(replies)

    async def chat(messages, schema, temperature):
        if seen is not None:
            seen.append(messages)
        return next(it)

    return chat


def test_every_scenario_is_a_valid_world_state_shaped_like_the_robot() -> None:
    for sc in SCENARIOS:
        assert sc.ticks, sc.id
        for w in sc.ticks:
            WorldState.model_validate(w)
            assert w["trigger"] == "periodic" and w["faults"] == []
            assert w["ball_detected"] == (w["ball_confidence"] > 0.3)
            assert len(w["recent_events"]) <= 5
            assert "clear_confidence" not in w  # the robot never sends it


def test_ball_gate() -> None:
    assert ball_gate_open(world(ball_confidence=0.9, vision_age_ms=100.0))
    assert not ball_gate_open(world(ball_confidence=0.5))
    assert not ball_gate_open(world(ball_confidence=0.9, vision_age_ms=900.0))
    assert not ball_gate_open(world(ball_confidence=0.9, vision_age_ms=-1.0))


def test_quiet_plan_passes_everywhere() -> None:
    for sc in SCENARIOS:
        for w in sc.ticks:
            assert check_plan(w, plan()) == [], sc.id


def test_hard_checks_fire() -> None:
    w = world()
    assert check_plan(w, None)
    assert "power talk" in check_plan(w, plan(say("I'm getting sleepy!")))[0]
    assert "power talk" in check_plan(w, plan(say("Time to recharge!")))[0]
    assert (
        "ball" in check_plan(world(ball_confidence=0.5), plan(say("Ooh, a ball!")))[0]
    )
    assert check_plan(world(ball_confidence=0.9), plan(say("Ooh, a ball!"))) == []
    uv = by_id("undervoltage").ticks[0]
    assert (
        len(
            check_plan(uv, plan(say("hi"), {"action": "skill", "name": "patrol_drift"}))
        )
        == 2
    )
    assert (
        check_plan(uv, plan({"action": "emote", "name": "curious", "intensity": 0.3}))
        == []
    )
    close = world(range_mm=300)
    assert (
        "forward skill"
        in check_plan(close, plan({"action": "skill", "name": "investigate_ball"}))[0]
    )
    assert (
        check_plan(close, plan({"action": "skill", "name": "retreat_and_recover"}))
        == []
    )
    fault = by_id("fault").ticks[0]
    assert "celebrated" in check_plan(fault, plan(say("Yay, let's go!")))[0]
    assert "no events" in check_plan(world(recent_events=[]), plan(say("Hello!")))[0]
    # Stale events are not "no events": the prompt cannot tell them from new ones, so speech there
    # is measured, not failed.
    assert (
        check_plan(world(recent_events=list(STALE_EVENTS)), plan(say("Hello!"))) == []
    )


def test_power_regex_leaves_ordinary_words_alone() -> None:
    w = world()
    for ok in (
        "Napkins are fun!",
        "Let's explore!",
        "Ooh, a snapshot!",
        "I'm not tiresome!",
    ):
        assert check_plan(w, plan(say(ok))) == [], ok
    for bad in ("Nap time!", "I need a nap.", "My battery is low", "Yawn!"):
        assert check_plan(w, plan(say(bad))), bad


@pytest.mark.asyncio
async def test_run_uses_server_messages_and_repairs_once() -> None:
    seen: list = []
    good = json.dumps({"actions": [say("Hi there!")], "ttl_ms": 2000})
    sc = by_id("touch")
    r = await run_scenario(sc, fake("not json at all", good, seen=seen), seed=0)
    assert len(seen) == 2
    assert seen[0][0]["role"] == "system" and "Robot Buddy" in seen[0][0]["content"]
    assert "World state:" in seen[0][1]["content"]
    assert seen[1][-1]["content"].startswith("The previous output was invalid")
    t = r.ticks[0]
    assert t.repaired and t.says == ["Hi there!"] and t.failures == []


@pytest.mark.asyncio
async def test_unparseable_after_repair_is_a_failure_and_report_says_fail() -> None:
    r = await run_scenario(by_id("touch"), fake("nope", "still nope"), seed=0)
    assert r.failures == ["tick 0: plan did not parse after the repair retry"]
    assert "**Hard checks:** FAIL" in format_report([r], title="t")


@pytest.mark.asyncio
async def test_repeat_say_is_counted() -> None:
    same = json.dumps({"actions": [say("Ooh!")], "ttl_ms": 2000})
    r = await run_scenario(by_id("quiet_stale"), fake(*[same] * 4), seed=0)
    rep = format_report([r], title="t")
    row = next(line for line in rep.splitlines() if line.startswith("| quiet_stale"))
    assert row.split(" | ")[6] == "3"  # 4 ticks, 3 consecutive repeats
