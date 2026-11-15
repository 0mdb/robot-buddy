"""Wake-word follow-up: after a wake-word reply plays, Buddy listens briefly for
an answer without the wake word (2026-11-15)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.api.param_registry import create_default_registry
from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import (
    AI_CMD_START_CONVERSATION,
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_FIRST_AUDIO,
    EAR_CMD_START_LISTENING,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_SPEECH_STARTED,
    EAR_EVENT_WAKE_WORD,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_FINISHED,
    TTS_EVENT_STARTED,
)

WINDOW_S = 0.1


class _Params:
    def __init__(self, **values: float) -> None:
        self._values = values

    def get_value(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def on_change(self, _cb: Any) -> None:
        pass


def _tick_loop(window_s: float = WINDOW_S):
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    params = _Params(**{"conversation.follow_up_window_s": window_s})
    loop = TickLoop(reflex=None, face=None, workers=workers, param_registry=params)
    loop.world.mic_link_up = True
    loop.world.spk_link_up = True
    loop._FOLLOW_UP_DELAY_S = 0.01
    return loop


def _env(t: str, payload: dict | None = None):
    return make_envelope(t, "test", 1, payload or {})


def _count(loop, worker: str, t: str) -> int:
    return sum(
        1
        for c in loop._workers.send_to.call_args_list
        if len(c.args) >= 2 and c.args[0] == worker and c.args[1] == t
    )


def _wake_turn(loop, *, cancelled: bool = False) -> str:
    """A full wake-word turn: wake, speak, reply arrives and plays, server done."""
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    sid = loop.world.session_id
    assert sid
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    loop._handle_face_events(_env(AI_CONVERSATION_FIRST_AUDIO))
    loop._handle_face_events(_env(TTS_EVENT_STARTED))
    loop._handle_face_events(_env(AI_CONVERSATION_DONE))
    assert loop.world.session_id == ""  # wake-word sessions end on done
    loop._handle_face_events(
        _env(TTS_EVENT_CANCELLED if cancelled else TTS_EVENT_FINISHED)
    )
    return sid


class TestFollowUp:
    def test_param_registered(self) -> None:
        assert (
            create_default_registry().get_value("conversation.follow_up_window_s")
            == 6.0
        )

    @pytest.mark.asyncio
    async def test_listens_after_reply_without_wake_word(self) -> None:
        loop = _tick_loop()
        first = _wake_turn(loop)
        starts = _count(loop, "ai", AI_CMD_START_CONVERSATION)
        await asyncio.sleep(0.05)
        assert loop.world.session_id and loop.world.session_id != first
        assert loop.world.conversation_trigger == "wake_word"
        assert _count(loop, "ai", AI_CMD_START_CONVERSATION) == starts + 1
        assert _count(loop, "ear", EAR_CMD_START_LISTENING) == 2

    @pytest.mark.asyncio
    async def test_window_closes_when_nothing_heard(self) -> None:
        loop = _tick_loop()
        _wake_turn(loop)
        await asyncio.sleep(0.05)
        assert loop.world.session_id
        await asyncio.sleep(WINDOW_S * 2)
        assert loop.world.session_id == ""

    @pytest.mark.asyncio
    async def test_speech_keeps_session_and_chains(self) -> None:
        loop = _tick_loop()
        _wake_turn(loop)
        await asyncio.sleep(0.05)
        sid = loop.world.session_id
        loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED))
        await asyncio.sleep(WINDOW_S * 2)
        assert loop.world.session_id == sid  # window no longer applies
        # The follow-up's own reply opens another follow-up.
        loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
        loop._handle_face_events(_env(AI_CONVERSATION_FIRST_AUDIO))
        loop._handle_face_events(_env(TTS_EVENT_STARTED))
        loop._handle_face_events(_env(AI_CONVERSATION_DONE))
        loop._handle_face_events(_env(TTS_EVENT_FINISHED))
        await asyncio.sleep(0.05)
        assert loop.world.session_id and loop.world.session_id != sid

    @pytest.mark.asyncio
    async def test_no_follow_up_after_cancelled_reply(self) -> None:
        loop = _tick_loop()
        _wake_turn(loop, cancelled=True)
        await asyncio.sleep(0.05)
        assert loop.world.session_id == ""

    @pytest.mark.asyncio
    async def test_no_follow_up_after_non_conversation_speech(self) -> None:
        loop = _tick_loop()
        loop._handle_face_events(_env(TTS_EVENT_STARTED))  # planner / idle speech
        loop._handle_face_events(_env(TTS_EVENT_FINISHED))
        await asyncio.sleep(0.05)
        assert loop.world.session_id == ""

    @pytest.mark.asyncio
    async def test_disabled_at_zero(self) -> None:
        loop = _tick_loop(window_s=0.0)
        _wake_turn(loop)
        await asyncio.sleep(0.05)
        assert loop.world.session_id == ""


class TestReplyNotPreempted:
    """2026-11-15: "I have a ball" (planner say) cut off a wake-word reply that
    was still playing after its session ended on AI done; the cancelled reply
    then opened no follow-up and the game was lost."""

    def _reply_playing_after_done(self, loop) -> None:
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
        loop._handle_face_events(_env(AI_CONVERSATION_FIRST_AUDIO))
        loop._handle_face_events(_env(TTS_EVENT_STARTED))
        loop.world.speaking = True  # event_router sets this on TTS started
        loop._handle_face_events(_env(AI_CONVERSATION_DONE))
        assert loop.world.session_id == ""

    @pytest.mark.asyncio
    async def test_conversation_busy_while_reply_plays(self) -> None:
        loop = _tick_loop()
        self._reply_playing_after_done(loop)
        assert loop._conversation_busy()
        assert loop.world.speech_priority == 1

    @pytest.mark.asyncio
    async def test_planner_say_does_not_cancel_reply(self) -> None:
        from supervisor.messages.types import TTS_CMD_CANCEL, TTS_CMD_SPEAK

        loop = _tick_loop()
        self._reply_playing_after_done(loop)
        await loop._enqueue_say("I have a ball!", source="planner", priority=2)
        assert _count(loop, "tts", TTS_CMD_CANCEL) == 0
        assert _count(loop, "tts", TTS_CMD_SPEAK) == 0

    @pytest.mark.asyncio
    async def test_priority_resets_when_speech_ends(self) -> None:
        loop = _tick_loop()
        self._reply_playing_after_done(loop)
        loop.world.speaking = False
        loop._handle_face_events(_env(TTS_EVENT_FINISHED))
        assert loop.world.speech_priority == 3
        await asyncio.sleep(0.05)
        assert loop.world.session_id  # follow-up opened


class TestSpeculation:
    """The ear's tentative end of utterance starts the reply early (held server-side);
    resumed speech drops it. Only wake-word turns end on VAD."""

    @pytest.mark.asyncio
    async def test_pause_and_resume_forwarded_for_wake_word_turns(self) -> None:
        from supervisor.messages.types import (
            AI_CMD_SPECULATE,
            AI_CMD_SPECULATE_CANCEL,
            EAR_EVENT_SPEECH_RESUMED,
            EAR_EVENT_UTTERANCE_PAUSE,
        )

        loop = _tick_loop()
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        loop._handle_face_events(_env(EAR_EVENT_UTTERANCE_PAUSE, {"silence_ms": 450}))
        loop._handle_face_events(_env(EAR_EVENT_SPEECH_RESUMED))
        loop._handle_face_events(_env(EAR_EVENT_UTTERANCE_PAUSE, {"silence_ms": 450}))
        await asyncio.sleep(0)
        assert _count(loop, "ai", AI_CMD_SPECULATE) == 2
        assert _count(loop, "ai", AI_CMD_SPECULATE_CANCEL) == 1

    @pytest.mark.asyncio
    async def test_not_forwarded_without_a_wake_word_session(self) -> None:
        from supervisor.messages.types import (
            AI_CMD_SPECULATE,
            EAR_EVENT_UTTERANCE_PAUSE,
        )

        loop = _tick_loop()
        loop._handle_face_events(_env(EAR_EVENT_UTTERANCE_PAUSE))  # no session
        loop._start_conversation("ptt")
        loop._handle_face_events(_env(EAR_EVENT_UTTERANCE_PAUSE))  # PTT session
        await asyncio.sleep(0)
        assert _count(loop, "ai", AI_CMD_SPECULATE) == 0
