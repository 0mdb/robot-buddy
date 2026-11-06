"""Voice pipeline refactor for the reSpeaker Flex: worker restart replay,
wake-word barge-in, ear capture supervision, XVF settings, mic level."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.api.param_registry import (
    XVF_PARAMS,
    create_default_registry,
    xvf_settings_from_registry,
)
from supervisor.core.worker_manager import WorkerManager
from supervisor.devices.xvf3800 import PARAMS, FakeTransport, Xvf3800, XvfError
from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import (
    EAR_CMD_PAUSE_VAD,
    EAR_CMD_RESUME_VAD,
    EAR_CMD_SET_MIC_CHANNEL,
    EAR_CMD_START_LISTENING,
    EAR_CMD_STOP_LISTENING,
    EAR_CMD_XVF_SET,
    EAR_CONFIG_INIT,
    EAR_EVENT_WAKE_WORD,
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
    TTS_CMD_CANCEL,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_STARTED,
)
from supervisor.workers.ear_worker import EarWorker

# ── WorkerManager: replay after restart ──────────────────────────


class TestStickyReplay:
    def _manager(self) -> WorkerManager:
        wm = WorkerManager(on_event=AsyncMock())
        wm.register("ear", "x")
        return wm

    @pytest.mark.asyncio
    async def test_init_first_then_latest_settings(self) -> None:
        wm = self._manager()
        await wm.send_to("ear", EAR_CMD_SET_MIC_CHANNEL, {"channel": 1})
        await wm.send_to("ear", EAR_CONFIG_INIT, {"mic_device": "match:x"})
        await wm.send_to("ear", EAR_CMD_SET_MIC_CHANNEL, {"channel": 2})
        await wm.send_to("ear", EAR_CMD_START_LISTENING)  # not sticky
        await wm.send_to("ear", EAR_CMD_XVF_SET, {"settings": {"PP_MIN_NS": 0.1}})
        await wm.send_to("ear", EAR_CMD_XVF_SET, {"settings": {"AEC_ASROUTGAIN": 8.0}})

        sent: list[tuple[str, dict]] = []

        async def capture(
            name: str, t: str, payload: dict | None = None, **_kw
        ) -> bool:
            sent.append((t, dict(payload or {})))
            return True

        wm.send_to = capture  # type: ignore[method-assign]
        await wm._replay_sticky(wm._workers["ear"])

        assert sent[0] == (EAR_CONFIG_INIT, {"mic_device": "match:x"})
        types = [t for t, _ in sent]
        assert EAR_CMD_START_LISTENING not in types
        assert (EAR_CMD_SET_MIC_CHANNEL, {"channel": 2}) in sent
        assert (
            EAR_CMD_XVF_SET,
            {"settings": {"PP_MIN_NS": 0.1, "AEC_ASROUTGAIN": 8.0}},
        ) in sent

    @pytest.mark.asyncio
    async def test_restart_replays(self, monkeypatch: pytest.MonkeyPatch) -> None:
        wm = self._manager()
        wm._running = True
        wm._restart_backoff_min_s = 0.0
        await wm.send_to("ear", EAR_CONFIG_INIT, {"a": 1})
        launched: list[str] = []
        replayed: list[str] = []

        async def fake_launch(info) -> None:  # noqa: ANN001
            launched.append(info.name)

        async def fake_replay(info) -> None:  # noqa: ANN001
            replayed.append(info.name)

        monkeypatch.setattr(wm, "_launch", fake_launch)
        monkeypatch.setattr(wm, "_replay_sticky", fake_replay)
        await wm._restart(wm._workers["ear"])
        assert launched == ["ear"] and replayed == ["ear"]


# ── Tick loop: wake-word barge-in ────────────────────────────────


def _tick_loop(barge_in: bool):
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    loop = TickLoop(reflex=None, face=None, workers=workers, barge_in=barge_in)
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


class TestBargeIn:
    @pytest.mark.asyncio
    async def test_off_wake_word_ignored_while_speaking(self) -> None:
        loop = _tick_loop(barge_in=False)
        loop.world.speaking = True
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        await asyncio.sleep(0)
        assert loop.world.session_id == ""
        assert _sends(loop, "tts", TTS_CMD_CANCEL) == []

    @pytest.mark.asyncio
    async def test_off_pauses_vad_during_tts(self) -> None:
        loop = _tick_loop(barge_in=False)
        loop._handle_face_events(_env(TTS_EVENT_STARTED))
        loop._handle_face_events(_env(TTS_EVENT_CANCELLED))
        await asyncio.sleep(0)
        assert _sends(loop, "ear", EAR_CMD_PAUSE_VAD)
        assert _sends(loop, "ear", EAR_CMD_RESUME_VAD)

    @pytest.mark.asyncio
    async def test_on_wake_word_interrupts_and_starts_new_turn(self) -> None:
        loop = _tick_loop(barge_in=True)
        loop._start_conversation("wake_word")
        old = loop.world.session_id
        loop.world.speaking = True  # the reply is playing
        loop._workers.send_to.reset_mock()

        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        await asyncio.sleep(0)
        new = loop.world.session_id
        assert new and new != old
        assert _sends(loop, "tts", TTS_CMD_CANCEL)
        assert _sends(loop, "ear", EAR_CMD_STOP_LISTENING)
        assert _sends(loop, "ear", EAR_CMD_START_LISTENING)
        assert _sends(loop, "ear", EAR_CMD_PAUSE_VAD) == []

        # The interrupted reply's CANCELLED must not end the new session.
        loop.world.speaking = False
        loop._handle_face_events(_env(TTS_EVENT_CANCELLED))
        await asyncio.sleep(0)
        assert loop.world.session_id == new

    @pytest.mark.asyncio
    async def test_on_interrupts_planner_speech_without_session(self) -> None:
        loop = _tick_loop(barge_in=True)
        loop.world.speaking = True
        loop.world.speech_priority = 2
        loop._handle_face_events(_env(EAR_EVENT_WAKE_WORD))
        await asyncio.sleep(0)
        assert loop.world.session_id
        assert _sends(loop, "tts", TTS_CMD_CANCEL)


# ── XVF settings ─────────────────────────────────────────────────


class TestXvfSettings:
    def test_registry_defaults_write_nothing(self) -> None:
        reg = create_default_registry()
        assert xvf_settings_from_registry(reg) == {}

    def test_changed_params_map_to_chip(self) -> None:
        reg = create_default_registry()
        reg.set("ear.xvf.asr_out_gain", 16.0)
        assert xvf_settings_from_registry(reg) == {"AEC_ASROUTGAIN": 16.0}

    def test_every_param_maps_to_a_tunable_rw_param(self) -> None:
        from supervisor.devices.xvf3800 import TUNABLE

        for xvf, *_ in XVF_PARAMS.values():
            assert xvf in TUNABLE and PARAMS[xvf].access == "rw"

    def test_apply_settings_writes(self) -> None:
        t = FakeTransport()
        written = Xvf3800(t).apply_settings({"AEC_ASROUTGAIN": 8, "PP_MIN_NS": [0.1]})
        assert written == ["AEC_ASROUTGAIN", "PP_MIN_NS"]
        assert t.values["AEC_ASROUTGAIN"] == [8.0]

    def test_apply_rejects_non_tunable(self) -> None:
        with pytest.raises(XvfError):
            Xvf3800(FakeTransport()).apply_settings({"SAVE_CONFIGURATION": 1})


# ── Ear worker ───────────────────────────────────────────────────


def _ear() -> tuple[EarWorker, list[tuple[str, dict]]]:
    w = EarWorker()
    sent: list[tuple[str, dict]] = []
    w.send = lambda t, p=None, **_k: sent.append((t, dict(p or {})))  # type: ignore[method-assign]
    return w, sent


class _FakeProc:
    def __init__(self, data: bytes) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(data)
        self.stdout.feed_eof()  # arecord "dies" after this data
        self.returncode: int | None = None

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


class TestEarWorker:
    @pytest.mark.asyncio
    async def test_init_and_live_settings(self) -> None:
        w, _ = _ear()
        await w.on_message(
            _env(
                EAR_CONFIG_INIT,
                {
                    "mic_device": "match:reSpeaker",
                    "mic_channels": 6,
                    "xvf": {"settings": {"AEC_ASROUTGAIN": 8.0, "BOGUS": 1}},
                },
            )
        )
        assert w._mic_spec == "match:reSpeaker"
        assert w._xvf_settings == {"AEC_ASROUTGAIN": 8.0}
        await w.on_message(_env(EAR_CMD_SET_MIC_CHANNEL, {"channel": 9}))
        assert w._mic_channel == 5  # clamped to the 6 captured channels
        await w.on_message(_env(EAR_CMD_XVF_SET, {"settings": {"PP_MIN_NS": 0.2}}))
        assert w._xvf_settings == {"AEC_ASROUTGAIN": 8.0, "PP_MIN_NS": 0.2}

    @pytest.mark.asyncio
    async def test_settings_applied_when_board_opens(self) -> None:
        w, _ = _ear()
        t = FakeTransport()
        w._xvf = Xvf3800(t)
        w._xvf_settings = {"AEC_ASROUTGAIN": 8.0}
        await w._apply_xvf_settings(dict(w._xvf_settings))
        assert t.values["AEC_ASROUTGAIN"] == [8.0]
        assert w._xvf_applied == ["AEC_ASROUTGAIN"]

    @pytest.mark.asyncio
    async def test_arecord_restarts_and_re_resolves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("supervisor.workers.ear_worker._ARECORD_RETRY_MIN_S", 0.0)
        monkeypatch.setattr("supervisor.workers.ear_worker._ARECORD_RETRY_MAX_S", 0.0)
        w, sent = _ear()
        w._running = True
        w._mic_spec = "match:reSpeaker"
        cards = iter(["plughw:CARD=C16K6Ch,DEV=0", "plughw:CARD=C16K6Ch_1,DEV=0"])
        monkeypatch.setattr(
            "supervisor.workers.ear_worker.resolve_alsa_device",
            lambda spec: next(cards, None),
        )
        spawned: list[str] = []

        async def spawn(device: str) -> _FakeProc:
            spawned.append(device)
            if len(spawned) >= 2:
                w._running = False
            return _FakeProc(bytes(640))

        monkeypatch.setattr(w, "_spawn_arecord", spawn)
        await asyncio.wait_for(w._capture_supervisor(), 2.0)

        assert spawned == ["plughw:CARD=C16K6Ch,DEV=0", "plughw:CARD=C16K6Ch_1,DEV=0"]
        links = [
            t for t, _ in sent if t in (SYSTEM_AUDIO_LINK_UP, SYSTEM_AUDIO_LINK_DOWN)
        ]
        assert links == [
            SYSTEM_AUDIO_LINK_UP,
            SYSTEM_AUDIO_LINK_DOWN,
            SYSTEM_AUDIO_LINK_UP,
            SYSTEM_AUDIO_LINK_DOWN,
        ]
        assert w._arecord_restarts >= 1

    def test_input_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import numpy as np

        w, _ = _ear()
        now = [100.0]
        monkeypatch.setattr(
            "supervisor.workers.ear_worker.time.monotonic", lambda: now[0]
        )
        w._reset_level()
        tone = (np.full(16000, 3277, dtype=np.int16)).tobytes()  # -20 dBFS
        w._update_level(tone[: len(tone) // 2])
        now[0] = 101.1
        w._update_level(tone[len(tone) // 2 :])
        assert w._input_rms_dbfs == pytest.approx(-20.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_pause_resume_clear_vad_buffer(self) -> None:
        w, _ = _ear()
        w._vad_buffer.extend(b"\x01" * 500)
        await w.on_message(_env(EAR_CMD_PAUSE_VAD))
        assert not w._vad_buffer
        w._vad_buffer.extend(b"\x01" * 500)
        await w.on_message(_env(EAR_CMD_RESUME_VAD))
        assert not w._vad_buffer
