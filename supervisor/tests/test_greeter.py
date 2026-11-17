"""Greeting people by name (core/greeter.py) and its path through the tick loop.

Synthetic names and ids only (repo rule).
"""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.api.param_registry import create_default_registry
from supervisor.core.event_bus import PlannerEvent
from supervisor.core.greeter import (
    GENERIC_COOLDOWN_MS,
    MEMBER_COOLDOWN_MS,
    WAIT_MS,
    Greeter,
)
from supervisor.messages.types import TTS_CMD_SPEAK

NAMES = {"m_kid": "Test Kid", "m_adult": "Test Parent"}
APPEAR = ("vision.face_appeared", {"count": 1, "range_mm": 800})


def _ident(mid: str, rng: int = 800):
    return ("vision.person_identified", {"member_id": mid, "range_mm": rng})


def _g() -> Greeter:
    return Greeter(rng=random.Random(0))


def test_recognised_within_wait_greets_by_name_only():
    g = _g()
    assert g.on_event(*APPEAR, 0.0, NAMES) is None
    line = g.on_event(*_ident("m_kid"), 600.0, NAMES)
    assert line and "Test Kid" in line
    assert g.poll(WAIT_MS + 100) is None  # no generic "hi" after it


def test_stranger_gets_generic_after_wait():
    g = _g()
    g.on_event(*APPEAR, 0.0, NAMES)
    assert g.poll(WAIT_MS - 1) is None
    line = g.poll(WAIT_MS)
    assert line in ("Oh, hi!", "Hi there!", "Hello!")


def test_unknown_member_id_or_far_face_is_not_named():
    g = _g()
    g.on_event(*APPEAR, 0.0, NAMES)
    assert g.on_event(*_ident("m_gone"), 100.0, NAMES) is None  # not in roster
    assert g.on_event(*_ident("m_kid", rng=3500), 200.0, NAMES) is None  # far away
    assert g.on_event("vision.face_appeared", {"range_mm": 3500}, 0.0, NAMES) is None


def test_member_cooldown_and_late_recognition():
    g = _g()
    g.on_event(*APPEAR, 0.0, NAMES)
    assert g.on_event(*_ident("m_kid"), 500.0, NAMES)
    # Same visit, a second person recognised later: greeted only after the quiet gap.
    assert g.on_event(*_ident("m_adult"), 5000.0, NAMES) is None
    # Next visit, soon after: the kid is on cooldown, the parent is not.
    t = 120_000.0
    g.on_event(*APPEAR, t, NAMES)
    assert g.on_event(*_ident("m_kid"), t + 300, NAMES) is None
    g.on_event(*APPEAR, t + 1000, NAMES)
    assert "Test Parent" in g.on_event(*_ident("m_adult"), t + 1300, NAMES)
    # After the cooldown, the kid again.
    t2 = MEMBER_COOLDOWN_MS + 10_000
    g.on_event(*APPEAR, t2, NAMES)
    assert "Test Kid" in g.on_event(*_ident("m_kid"), t2 + 300, NAMES)


def test_generic_cooldown():
    g = _g()
    g.on_event(*APPEAR, 0.0, NAMES)
    assert g.poll(WAIT_MS)
    g.on_event(*APPEAR, 100_000.0, NAMES)
    assert g.poll(100_000.0 + WAIT_MS) is None
    t = GENERIC_COOLDOWN_MS + 10_000
    g.on_event(*APPEAR, t, NAMES)
    assert g.poll(t + WAIT_MS)


def test_face_lost_cancels_pending():
    g = _g()
    g.on_event(*APPEAR, 0.0, NAMES)
    g.on_event("vision.face_lost", {}, 500.0, NAMES)
    assert g.poll(WAIT_MS + 1) is None


# ── Tick loop ────────────────────────────────────────────────────


def _loop(quiet: bool = False):
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    reg = create_default_registry()
    reg.set("conversation.quiet_mode", quiet)
    loop = TickLoop(reflex=None, face=None, workers=workers, param_registry=reg)
    loop._household_names = dict(NAMES)
    loop._kinds_refresh_ms = 1e18  # keep the test's names (no roster file)
    return loop


def _spoken(loop) -> list[str]:
    return [
        c.args[2]["text"]
        for c in loop._workers.send_to.call_args_list
        if len(c.args) >= 3 and c.args[0] == "tts" and c.args[1] == TTS_CMD_SPEAK
    ]


def _evt(etype, payload, t, seq):
    return PlannerEvent(etype, payload, t, seq=seq)


@pytest.mark.asyncio
async def test_tick_loop_greets_by_name():
    loop = _loop()
    a = _evt(*APPEAR, 1000.0, 1)
    await loop._emit_worker_actions(1000.0, [a])
    b = _evt(*_ident("m_kid"), 1500.0, 2)
    await loop._emit_worker_actions(1500.0, [a, b])
    await loop._emit_worker_actions(1000.0 + WAIT_MS + 100, [a, b])
    (line,) = _spoken(loop)
    assert "Test Kid" in line


@pytest.mark.asyncio
async def test_tick_loop_generic_for_stranger():
    loop = _loop()
    a = _evt(*APPEAR, 1000.0, 1)
    await loop._emit_worker_actions(1000.0, [a])
    await loop._emit_worker_actions(1000.0 + WAIT_MS, [a])
    assert _spoken(loop) and _spoken(loop)[0] in ("Oh, hi!", "Hi there!", "Hello!")


@pytest.mark.asyncio
async def test_quiet_mode_silences_greeting():
    loop = _loop(quiet=True)
    a = _evt(*APPEAR, 1000.0, 1)
    b = _evt(*_ident("m_kid"), 1200.0, 2)
    await loop._emit_worker_actions(1200.0, [a, b])
    assert _spoken(loop) == []
    assert loop.world.say_dropped_reason["quiet_mode"] == 1


@pytest.mark.asyncio
async def test_no_greeting_mid_conversation():
    loop = _loop()
    loop._conversation_busy = lambda: True
    a = _evt(*APPEAR, 1000.0, 1)
    await loop._emit_worker_actions(1000.0, [a])
    await loop._emit_worker_actions(1000.0 + WAIT_MS, [a])
    assert _spoken(loop) == []


# ── Who is present, for the conversation profile ─────────────────


def _profile_loop(faces):
    import time

    loop = _loop()
    loop.world.household_kinds = {"m_kid": "kid", "m_adult": "adult"}
    loop._household_ages = {"m_kid": 9}
    loop.world.faces_held = faces
    loop.world.faces_seen_mono_ms = time.monotonic() * 1000.0
    return loop


def _base_profile():
    return {
        "audience": {
            "present": [{"kind": "unknown", "confidence": 0.0, "sources": []}],
            "speaking": 0,
            "household": {"members": []},
        }
    }


def test_recognised_kid_alone_is_the_speaker():
    loop = _profile_loop([{"member_id": "m_kid", "id_score": 0.7}])
    p = _base_profile()
    loop._add_present_faces(p)
    (kid,) = p["audience"]["present"]
    assert kid["kind"] == "kid" and kid["age"] == 9 and kid["name"] == "Test Kid"
    assert kid["confidence"] >= 0.75 and p["audience"]["speaking"] == 0


def test_adult_alone_keeps_a_possible_child():
    loop = _profile_loop([{"member_id": "m_adult", "id_score": 0.9}])
    p = _base_profile()
    loop._add_present_faces(p)
    kinds = [x["kind"] for x in p["audience"]["present"]]
    assert kinds == ["adult", "unknown"] and p["audience"]["speaking"] is None


def test_stranger_is_unknown_and_no_faces_keeps_roster_default():
    loop = _profile_loop([{"member_id": None}])
    p = _base_profile()
    loop._add_present_faces(p)
    assert p["audience"]["present"][0]["kind"] == "unknown"
    assert "name" not in p["audience"]["present"][0]

    loop = _profile_loop([])
    p = _base_profile()
    loop._add_present_faces(p)
    assert p == _base_profile()
