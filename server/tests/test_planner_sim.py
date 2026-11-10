"""L1 planner suite, against a fake model (SIM-INTERACTION, the planner's say() path)."""

from __future__ import annotations

import json

import pytest

from app.eval.planner_sim import (
    SCENARIOS,
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
            assert w["ball_detected"] == (w["ball_confidence"] > 0.3)
            assert len(w["recent_events"]) <= 5
            if "new_events" in w:
                assert w["trigger"] == ("event" if w["new_events"] else "heartbeat")
                assert (
                    w["recent_events"][len(w["recent_events"]) - len(w["new_events"]) :]
                    == w["new_events"]
                )
            else:
                assert w["trigger"] == "periodic"  # legacy supervisor


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
    w = world("face.button.click")
    assert check_plan(w, None)
    assert "power talk" in check_plan(w, plan(say("I'm getting sleepy!")))[0]
    assert "power talk" in check_plan(w, plan(say("Time to recharge!")))[0]
    ev = "vision.ball_acquired"
    shut = check_plan(world(ev, ball_confidence=0.5), plan(say("Ooh, a ball!")))
    assert "ball" in shut[0]
    assert check_plan(world(ev, ball_confidence=0.9), plan(say("Ooh, a ball!"))) == []
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
    close = world("safety.obstacle_close", range_mm=300)
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
    assert "no new events" in check_plan(world(), plan(say("Hello!")))[0]
    # A legacy supervisor sends no new_events: speech there is measured, not failed.
    assert check_plan(world(legacy=True), plan(say("Hello!"))) == []
    assert "celebrated" in check_plan(world(faults=["STALL"]), plan(say("Awesome!")))[0]


def test_power_regex_leaves_ordinary_words_alone() -> None:
    w = world("face.button.click")
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
async def test_quiet_ticks_never_reach_the_model() -> None:
    seen: list = []
    r = await run_scenario(by_id("quiet"), fake(seen=seen), seed=0)
    assert seen == [] and all(t.skipped and t.plan["actions"] == [] for t in r.ticks)


@pytest.mark.asyncio
async def test_heard_applies_the_scheduler_cooldowns_and_repeats_count_openings() -> (
    None
):
    ball = json.dumps({"actions": [say("Ooh! A ball!")], "ttl_ms": 2000})
    again = json.dumps({"actions": [say("Ooh, a ball again!")], "ttl_ms": 2000})
    lost = json.dumps({"actions": [], "ttl_ms": 500})
    # ball_reacquired: acquired, lost, acquired, 5 s apart. Same text 10 s later is dropped.
    r = await run_scenario(by_id("ball_reacquired"), fake(ball, lost, ball), seed=0)
    assert [t.heard for t in r.ticks] == [["Ooh! A ball!"], [], []]
    # Reworded, it is heard, and counts as a repeat a child would notice.
    r = await run_scenario(by_id("ball_reacquired"), fake(ball, lost, again), seed=0)
    assert [t.heard for t in r.ticks] == [["Ooh! A ball!"], [], ["Ooh, a ball again!"]]
    row = next(
        line
        for line in format_report([r], title="t").splitlines()
        if line.startswith("| ball_reacquired")
    )
    assert row.split(" | ")[8] == "1"


def test_a_negated_ball_is_not_a_claim() -> None:
    w = world("vision.ball_lost")
    assert check_plan(w, plan(say("Hmm, no ball around. Let's explore!"))) == []
    assert check_plan(w, plan(say("Where did the ball go?"))) == []
    assert check_plan(w, plan(say("Wait. A ball!")))  # the second sentence claims one


def test_openings_ignore_leading_interjections() -> None:
    from app.eval.planner_sim import _opening

    assert _opening("Ooh! You pressed the button!") == _opening(
        "Yay! You pressed the button! 🎉"
    )
    assert _opening("Oh no! Uh oh. A ball!") == "a ball"
