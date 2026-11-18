"""Late resume: the child goes on after the end of utterance, before Buddy's reply plays.
The ear keeps listening; the reply is dropped and the next end of utterance sends the
merged turn (the server keeps the first part's audio)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import (
    AI_CMD_END_UTTERANCE,
    AI_CMD_LATE_RESUME,
    AI_CONVERSATION_DONE,
    EAR_CMD_STOP_LISTENING,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_SPEECH_STARTED,
    EAR_EVENT_WAKE_WORD,
    TTS_CMD_CANCEL,
    TTS_EVENT_STARTED,
)


class _Params:
    def __init__(self, **values: Any) -> None:
        self._values = values

    def get_value(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def on_change(self, _cb: Any) -> None:
        pass


def _loop(late_ms: int = 3000):
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    params = _Params(**{"conversation.late_resume_ms": late_ms})
    loop = TickLoop(reflex=None, face=None, workers=workers, param_registry=params)
    loop.world.mic_link_up = True
    loop.world.spk_link_up = True
    return loop


def _env(t: str, payload: dict | None = None):
    return make_envelope(t, "test", 1, payload or {})


def _count(loop, worker: str, t: str) -> int:
    return sum(
        1
        for c in loop._workers.send_to.call_args_list
        if len(c.args) >= 2 and c.args[0] == worker and c.args[1] == t
    )


async def _settle() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_speech_after_the_end_of_utterance_drops_the_reply_and_keeps_listening():
    loop = _loop()
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    sid = loop.world.session_id
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    await _settle()
    assert _count(loop, "ear", EAR_CMD_STOP_LISTENING) == 0  # still listening
    loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED))
    await _settle()
    assert _count(loop, "ai", AI_CMD_LATE_RESUME) == 1
    assert loop.world.session_id == sid and loop.robot.face_listening
    assert loop._turn_watchdog_stage == ""  # listening again, no reply deadline
    # The merged utterance ends normally.
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    await _settle()
    assert _count(loop, "ai", AI_CMD_END_UTTERANCE) == 2


@pytest.mark.asyncio
async def test_the_window_closes_when_the_reply_starts():
    loop = _loop()
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    loop._handle_face_events(_env(TTS_EVENT_STARTED))
    await _settle()
    assert _count(loop, "ear", EAR_CMD_STOP_LISTENING) == 1
    loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED))
    await _settle()
    assert _count(loop, "ai", AI_CMD_LATE_RESUME) == 0


@pytest.mark.asyncio
async def test_the_window_times_out():
    loop = _loop(late_ms=50)
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    await asyncio.sleep(0.1)
    assert _count(loop, "ear", EAR_CMD_STOP_LISTENING) == 1
    loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED))
    await _settle()
    assert _count(loop, "ai", AI_CMD_LATE_RESUME) == 0


@pytest.mark.asyncio
async def test_off_stops_listening_at_the_end_of_utterance():
    loop = _loop(late_ms=0)
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    await _settle()
    assert _count(loop, "ear", EAR_CMD_STOP_LISTENING) == 1
    assert not loop._late_resume_open


@pytest.mark.asyncio
async def test_a_stale_chunk_of_the_dropped_reply_is_cancelled():
    loop = _loop()
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED))
    loop._handle_face_events(_env(TTS_EVENT_STARTED))  # reached the speaker anyway
    await _settle()
    assert _count(loop, "tts", TTS_CMD_CANCEL) == 1
    assert loop._ignore_next_tts_end


@pytest.mark.asyncio
async def test_session_end_closes_the_window():
    loop = _loop()
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    loop._handle_face_events(_env(AI_CONVERSATION_DONE))
    assert not loop._late_resume_open and loop._late_resume_timer is None


@pytest.mark.asyncio
async def test_a_weak_start_of_speech_does_not_drop_the_reply():
    """Owen's "90", then a 0.31 blip: the reply was dropped and he had to repeat (2026-11-18)."""
    loop = _loop()
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    await _settle()
    loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED, {"prob": 0.31}))
    await _settle()
    assert _count(loop, "ai", AI_CMD_LATE_RESUME) == 0
    loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED, {"prob": 0.9}))
    await _settle()
    assert _count(loop, "ai", AI_CMD_LATE_RESUME) == 1
