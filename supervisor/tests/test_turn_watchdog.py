"""Conversation turn watchdog: a turn whose reply never arrives (server stream
stalled) ends the session instead of holding it open (TODO 2026-11-10)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.api.param_registry import create_default_registry
from supervisor.devices.protocol import FaceConvState
from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import (
    AI_CMD_END_CONVERSATION,
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_FIRST_AUDIO,
    AI_CONVERSATION_TURN_ERROR,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_SPEECH_STARTED,
    EAR_EVENT_WAKE_WORD,
    TTS_CMD_CANCEL,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_FINISHED,
    TTS_EVENT_STARTED,
)

TURN_S = 0.05
REPLY_S = 0.15


class _Params:
    """Minimal registry stand-in so the budgets can be shorter than the param min."""

    def __init__(self, **overrides: float) -> None:
        self._values = overrides

    def get_value(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def on_change(self, _cb: Any) -> None:
        pass


def _tick_loop():
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    params = _Params(
        **{
            "conversation.turn_timeout_s": TURN_S,
            "conversation.reply_timeout_s": REPLY_S,
        }
    )
    loop = TickLoop(reflex=None, face=None, workers=workers, param_registry=params)
    loop.world.mic_link_up = True
    loop.world.spk_link_up = True
    return loop


def _env(t: str, payload: dict | None = None):
    return make_envelope(t, "test", 1, payload or {})


def _sends(loop, worker: str, t: str) -> list:
    return [
        c
        for c in loop._workers.send_to.call_args_list
        if len(c.args) >= 2 and c.args[0] == worker and c.args[1] == t
    ]


def _wake_and_speak(loop) -> str:
    """Wake word, then the kid finishes talking: the turn now waits on the server."""
    loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
    sid = loop.world.session_id
    assert sid
    loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
    assert loop._turn_watchdog_stage == "awaiting_reply"
    return sid


class TestTurnWatchdog:
    def test_params_registered(self) -> None:
        reg = create_default_registry()
        assert reg.get_value("conversation.turn_timeout_s") == 20.0
        assert reg.get_value("conversation.reply_timeout_s") == 60.0

    @pytest.mark.asyncio
    async def test_fires_when_no_reply_arrives(self) -> None:
        loop = _tick_loop()
        sid = _wake_and_speak(loop)
        await asyncio.sleep(TURN_S * 3)
        assert loop.world.session_id == ""
        assert loop._conv.state == FaceConvState.DONE
        assert loop._turn_watchdog_stage == ""
        ends = _sends(loop, "ai", AI_CMD_END_CONVERSATION)
        assert ends and ends[-1].args[2]["session_id"] == sid

    @pytest.mark.asyncio
    async def test_wake_word_after_expiry_starts_new_session(self) -> None:
        loop = _tick_loop()
        old = _wake_and_speak(loop)
        await asyncio.sleep(TURN_S * 3)
        assert loop.world.session_id == ""
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        new = loop.world.session_id
        assert new and new != old
        assert loop._conv.state == FaceConvState.ATTENTION

    @pytest.mark.asyncio
    async def test_first_audio_in_time_switches_to_reply_budget(self) -> None:
        loop = _tick_loop()
        sid = _wake_and_speak(loop)
        loop._handle_face_events(_env(AI_CONVERSATION_FIRST_AUDIO))
        assert loop._turn_watchdog_stage == "replying"
        await asyncio.sleep(TURN_S * 2)  # past the wait-for-reply budget
        assert loop.world.session_id == sid
        assert _sends(loop, "ai", AI_CMD_END_CONVERSATION) == []

    @pytest.mark.asyncio
    async def test_done_in_time_disarms(self) -> None:
        loop = _tick_loop()
        loop._start_conversation("ptt")  # PTT: done does not end the session
        loop._conv.set_state(FaceConvState.ATTENTION)
        loop._conv.ptt_held = True
        loop._toggle_ptt()  # PTT off → utterance end
        sid = loop.world.session_id
        assert loop._turn_watchdog_stage == "awaiting_reply"
        loop._handle_face_events(_env(AI_CONVERSATION_DONE))
        assert loop._turn_watchdog is None
        await asyncio.sleep(TURN_S * 3)
        assert loop.world.session_id == sid
        assert _sends(loop, "ai", AI_CMD_END_CONVERSATION) == []

    @pytest.mark.asyncio
    async def test_tts_finished_disarms(self) -> None:
        loop = _tick_loop()
        loop._start_conversation("ptt")
        loop._conv.set_state(FaceConvState.ATTENTION)
        loop._conv.ptt_held = True
        loop._toggle_ptt()
        sid = loop.world.session_id
        loop._handle_face_events(_env(TTS_EVENT_STARTED))
        loop._handle_face_events(_env(TTS_EVENT_FINISHED))
        assert loop._turn_watchdog is None
        await asyncio.sleep(REPLY_S * 1.5)
        # The multi-turn idle timeout (30 s default) owns the session now.
        assert loop.world.session_id == sid
        loop._cancel_multi_turn_timeout()

    @pytest.mark.asyncio
    async def test_stall_mid_reply_cancels_tts_and_ends(self) -> None:
        loop = _tick_loop()
        _wake_and_speak(loop)
        loop._handle_face_events(_env(TTS_EVENT_STARTED))
        loop.world.speaking = True  # event_router sets this in the real loop
        await asyncio.sleep(TURN_S * 2)
        assert loop.world.session_id  # reply budget is longer
        await asyncio.sleep(REPLY_S)
        assert loop.world.session_id == ""
        assert _sends(loop, "tts", TTS_CMD_CANCEL)

        # The stalled reply's CANCELLED must not end a session started meanwhile.
        loop.world.speaking = False
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        new = loop.world.session_id
        assert new
        loop._handle_face_events(_env(TTS_EVENT_CANCELLED))
        assert loop.world.session_id == new

    @pytest.mark.asyncio
    async def test_turn_error_ends_turn_immediately(self) -> None:
        loop = _tick_loop()
        _wake_and_speak(loop)
        loop._handle_face_events(_env(AI_CONVERSATION_TURN_ERROR, {"reason": "x"}))
        assert loop.world.session_id == ""
        assert loop._turn_watchdog is None

    @pytest.mark.asyncio
    async def test_not_armed_without_utterance_end(self) -> None:
        loop = _tick_loop()
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        sid = loop.world.session_id
        # Only the (8 s) wait for speech; the turn budget starts at the utterance end.
        assert loop._turn_watchdog_stage == "waiting_for_speech"
        await asyncio.sleep(TURN_S * 3)
        assert loop.world.session_id == sid


class TestSpeechWait:
    """After a wake word, a session where nobody starts speaking ends; it used to
    stream the mic to the server for minutes (overnight, 2026-11-17)."""

    def _loop(self):
        loop = _tick_loop()
        loop._param_registry = _Params(
            **{"conversation.speech_wait_s": TURN_S, "conversation.turn_timeout_s": 5.0}
        )
        return loop

    def test_param_registered(self) -> None:
        assert create_default_registry().get_value("conversation.speech_wait_s") == 8.0

    @pytest.mark.asyncio
    async def test_no_speech_after_wake_word_ends_the_session(self) -> None:
        loop = self._loop()
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        sid = loop.world.session_id
        assert loop._turn_watchdog_stage == "waiting_for_speech"
        await asyncio.sleep(TURN_S * 3)
        assert loop.world.session_id == ""
        ends = _sends(loop, "ai", AI_CMD_END_CONVERSATION)
        assert ends and ends[-1].args[2]["session_id"] == sid

    @pytest.mark.asyncio
    async def test_speech_started_keeps_the_session(self) -> None:
        loop = self._loop()
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        sid = loop.world.session_id
        loop._handle_face_events(_env(EAR_EVENT_SPEECH_STARTED))
        assert loop._turn_watchdog_stage == ""
        await asyncio.sleep(TURN_S * 3)
        assert loop.world.session_id == sid
        loop._handle_face_events(_env(EAR_EVENT_END_OF_UTTERANCE))
        assert loop._turn_watchdog_stage == "awaiting_reply"
