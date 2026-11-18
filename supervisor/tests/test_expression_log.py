"""Logs that answer "why did Buddy look/sound like that": expression requests with their
source, face mood changes, and per-turn reply timing. No words in any of them."""

from __future__ import annotations

import logging

import pytest

from supervisor.devices.protocol import FaceMood
from supervisor.messages.types import (
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_WAKE_WORD,
    TTS_EVENT_STARTED,
)
from supervisor.tests.test_turn_watchdog import _env, _tick_loop


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def test_planner_emote_is_logged_with_its_source(caplog) -> None:
    loop = _tick_loop()
    with caplog.at_level(logging.INFO, logger="supervisor.core.tick_loop"):
        loop._apply_emote({"name": "curious", "intensity": 0.6})
    assert "expression request: planner curious (0.60)" in _lines(caplog)


def test_mood_change_logged_once_with_the_last_request(caplog) -> None:
    loop = _tick_loop()
    loop._note_expression("planner", "curious", 0.6)
    with caplog.at_level(logging.INFO, logger="supervisor.core.tick_loop"):
        loop._log_mood_change(int(FaceMood.CURIOUS), 0.6, "personality")
        loop._log_mood_change(int(FaceMood.CURIOUS), 0.7, "personality")  # same mood
    lines = [x for x in _lines(caplog) if x.startswith("face mood")]
    assert len(lines) == 1
    assert lines[0].startswith("face mood -> curious (0.60) via personality")
    assert "last request planner curious" in lines[0]


@pytest.mark.asyncio
async def test_turn_timing_logged_when_buddy_starts_talking(caplog) -> None:
    loop = _tick_loop()
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    with caplog.at_level(logging.INFO, logger="supervisor.core.tick_loop"):
        loop._handle_face_events(_env(TTS_EVENT_STARTED))
    (line,) = [x for x in _lines(caplog) if x.startswith("turn: ")]
    assert "after the end of speech" in line and "0 late resumes" in line
