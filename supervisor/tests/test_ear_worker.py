"""Tests for ear worker — VAD state machine and wake word buffer logic."""

from __future__ import annotations

import struct
import time

import numpy as np
import pytest

from supervisor.workers.ear_worker import (
    CHUNK_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    EarWorker,
    _OWW_FRAME_BYTES,
    _VAD_FRAME_BYTES,
    _WW_COOLDOWN_S,
)


class _FakeNodeArg:
    def __init__(self, name: str, shape: list[object]):
        self.name = name
        self.shape = shape


class _FakeStateVadSession:
    def __init__(self):
        self._inputs = [
            _FakeNodeArg("input", [None, None]),
            _FakeNodeArg("state", [2, None, 128]),
            _FakeNodeArg("sr", []),
        ]
        self._outputs = [
            _FakeNodeArg("output", [None, 1]),
            _FakeNodeArg("stateN", [None, None, None]),
        ]
        self.last_feed: dict[str, object] | None = None
        self.next_state = np.full((2, 1, 128), 3.0, dtype=np.float32)

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, _output_names, feed):
        self.last_feed = feed
        return [np.array([[0.9]], dtype=np.float32), self.next_state.copy()]


class _FakeHCVadSession:
    def __init__(self):
        self._inputs = [
            _FakeNodeArg("input", [None, None]),
            _FakeNodeArg("h", [2, None, 64]),
            _FakeNodeArg("c", [2, None, 64]),
            _FakeNodeArg("sr", []),
        ]
        self._outputs = [
            _FakeNodeArg("output", [None, 1]),
            _FakeNodeArg("hn", [None, None, None]),
            _FakeNodeArg("cn", [None, None, None]),
        ]
        self.last_feed: dict[str, object] | None = None
        self.next_h = np.full((2, 1, 64), 5.0, dtype=np.float32)
        self.next_c = np.full((2, 1, 64), 7.0, dtype=np.float32)

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, _output_names, feed):
        self.last_feed = feed
        return [
            np.array([[0.9]], dtype=np.float32),
            self.next_h.copy(),
            self.next_c.copy(),
        ]


class _FakeUnsupportedVadSession:
    def __init__(self):
        self._inputs = [
            _FakeNodeArg("input", [None, None]),
            _FakeNodeArg("foo", [2, None, 64]),
            _FakeNodeArg("sr", []),
        ]
        self._outputs = [_FakeNodeArg("output", [None, 1])]
        self.run_calls = 0

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, _output_names, _feed):
        self.run_calls += 1
        return [np.array([[0.1]], dtype=np.float32)]


# ── VAD state machine tests ──────────────────────────────────────


class TestVADStateMachine:
    """Test the speech→silence→end_of_utterance detection logic."""

    def _make_worker(self) -> EarWorker:
        w = EarWorker()
        w._vad_silence_ms = 1000
        w._vad_min_speech_ms = 200
        return w

    def test_initial_state(self):
        w = self._make_worker()
        assert w._speech_detected is False
        assert w._silence_start_mono == 0.0
        assert w._speech_start_mono == 0.0

    def test_reset_clears_state(self):
        w = self._make_worker()
        w._speech_detected = True
        w._speech_start_mono = 1.0
        w._silence_start_mono = 2.0
        w._reset_vad_state()
        assert w._speech_detected is False
        assert w._speech_start_mono == 0.0
        assert w._silence_start_mono == 0.0

    def test_stop_listening_resets_vad(self):
        w = self._make_worker()
        w._listening = True
        w._speech_detected = True
        w._stop_listening()
        assert w._listening is False
        assert w._speech_detected is False

    def test_start_listening_sets_flag(self):
        w = self._make_worker()
        assert w._listening is False
        w._start_listening()
        assert w._listening is True

    def test_start_listening_idempotent(self):
        w = self._make_worker()
        w._start_listening()
        w._start_listening()  # should not raise
        assert w._listening is True

    def test_pause_resume_vad(self):
        w = self._make_worker()
        assert w._vad_paused is False
        w._vad_paused = True
        assert w._vad_paused is True
        w._vad_paused = False
        assert w._vad_paused is False


class TestVADSchemaCompatibility:
    def test_check_vad_uses_state_schema_and_updates_recurrent_state(self):
        w = EarWorker()
        session = _FakeStateVadSession()
        w._vad_session = session
        assert w._configure_vad_schema() is True
        assert w._vad_schema == "state"

        pcm = b"\x00\x00" * 512
        w._check_vad(pcm)

        assert session.last_feed is not None
        assert "state" in session.last_feed
        assert "h" not in session.last_feed
        assert "c" not in session.last_feed
        assert np.array_equal(w._vad_state, session.next_state)

    def test_check_vad_uses_hc_schema_and_updates_hidden_cell_state(self):
        w = EarWorker()
        session = _FakeHCVadSession()
        w._vad_session = session
        assert w._configure_vad_schema() is True
        assert w._vad_schema == "hc"

        pcm = b"\x00\x00" * 512
        w._check_vad(pcm)

        assert session.last_feed is not None
        assert "h" in session.last_feed
        assert "c" in session.last_feed
        assert "state" not in session.last_feed
        assert np.array_equal(w._vad_h, session.next_h)
        assert np.array_equal(w._vad_c, session.next_c)

    def test_reset_vad_state_resets_state_schema_tensor(self):
        w = EarWorker()
        w._vad_session = _FakeStateVadSession()
        assert w._configure_vad_schema() is True
        w._vad_state = np.full((2, 1, 128), 9.0, dtype=np.float32)

        w._reset_vad_state()

        assert w._vad_state is not None
        assert w._vad_state.shape == (2, 1, 128)
        assert np.count_nonzero(w._vad_state) == 0

    def test_reset_vad_state_resets_hc_schema_tensors(self):
        w = EarWorker()
        w._vad_session = _FakeHCVadSession()
        assert w._configure_vad_schema() is True
        w._vad_h = np.full((2, 1, 64), 9.0, dtype=np.float32)
        w._vad_c = np.full((2, 1, 64), 9.0, dtype=np.float32)

        w._reset_vad_state()

        assert w._vad_h is not None
        assert w._vad_c is not None
        assert w._vad_h.shape == (2, 1, 64)
        assert w._vad_c.shape == (2, 1, 64)
        assert np.count_nonzero(w._vad_h) == 0
        assert np.count_nonzero(w._vad_c) == 0

    def test_unsupported_schema_disables_vad_runtime(self):
        w = EarWorker()
        session = _FakeUnsupportedVadSession()
        w._vad_session = session

        assert w._configure_vad_schema() is False
        assert w._vad_session is None
        assert w._vad_schema == "disabled"

        pcm = b"\x00\x00" * 512
        w._check_vad(pcm)  # Should no-op and avoid inference errors.
        assert session.run_calls == 0


# ── Buffer accumulation tests ────────────────────────────────────


class TestBufferAccumulation:
    """Test that chunks accumulate to correct frame sizes."""

    def test_oww_frame_size(self):
        """80ms at 16kHz 16-bit = 2560 bytes."""
        assert _OWW_FRAME_BYTES == int(SAMPLE_RATE * SAMPLE_WIDTH * 0.08)
        assert _OWW_FRAME_BYTES == 2560

    def test_vad_frame_size(self):
        """512 samples * 2 bytes = 1024 bytes."""
        assert _VAD_FRAME_BYTES == 1024

    def test_chunk_size(self):
        """10ms at 16kHz 16-bit = 320 bytes."""
        assert CHUNK_BYTES == 320

    def test_oww_accumulates_8_chunks(self):
        """80ms / 10ms = 8 chunks needed for one OWW frame."""
        w = EarWorker()
        for i in range(7):
            w._ww_buffer.extend(b"\x00" * CHUNK_BYTES)
            assert len(w._ww_buffer) < _OWW_FRAME_BYTES
        w._ww_buffer.extend(b"\x00" * CHUNK_BYTES)
        assert len(w._ww_buffer) >= _OWW_FRAME_BYTES

    def test_vad_accumulates_about_3_chunks(self):
        """1024 / 320 ~ 3.2, so need ~4 chunks for one+ VAD frame."""
        w = EarWorker()
        total = 0
        for i in range(4):
            w._vad_buffer.extend(b"\x00" * CHUNK_BYTES)
            total += CHUNK_BYTES
        assert total >= _VAD_FRAME_BYTES


# ── Wake word cooldown tests ─────────────────────────────────────


class TestWakeWordCooldown:
    def test_cooldown_constant(self):
        assert _WW_COOLDOWN_S == 3.0

    def test_initial_cooldown_allows_detection(self):
        """First detection should not be blocked by cooldown."""
        w = EarWorker()
        assert w._last_ww_mono == 0.0
        # time.monotonic() will always be > 0 + 3.0 after system startup


# ── Health payload tests ─────────────────────────────────────────


class TestHealthPayload:
    def test_health_shows_state(self):
        w = EarWorker()
        h = w.health_payload()
        assert h["listening"] is False
        assert h["vad_paused"] is False
        assert h["speech_detected"] is False
        assert h["oww_loaded"] is False
        assert h["vad_loaded"] is False
        assert h["vad_schema"] == "disabled"

    def test_health_reflects_listening(self):
        w = EarWorker()
        w._listening = True
        h = w.health_payload()
        assert h["listening"] is True


# ── Socket framing tests ─────────────────────────────────────────


class TestMicSocketFraming:
    @pytest.mark.asyncio
    async def test_forward_skipped_without_socket(self):
        """No exception when mic socket is None."""
        w = EarWorker()
        await w._forward_to_mic_socket(b"\x00" * CHUNK_BYTES)  # should not raise

    @pytest.mark.asyncio
    async def test_stalled_reader_never_blocks_and_disconnects(self):
        """A reader that stops draining (AI worker lost the server) must not
        freeze the capture loop; the ear drops the socket instead (2026-11-10)."""
        import asyncio
        import socket

        w = EarWorker()
        ear_end, reader_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        ear_end.setblocking(False)
        w._mic_sock = ear_end
        try:
            chunk = b"\x00" * CHUNK_BYTES
            for _ in range(20_000):  # far more than kernel buffer + backlog cap
                await asyncio.wait_for(w._forward_to_mic_socket(chunk), 0.5)
                if w._mic_sock is None:
                    break
            assert w._mic_sock is None
            assert not w._mic_pending
        finally:
            ear_end.close()
            reader_end.close()

    @pytest.mark.asyncio
    async def test_draining_reader_gets_intact_frames(self):
        import socket

        w = EarWorker()
        ear_end, reader_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        ear_end.setblocking(False)
        w._mic_sock = ear_end
        try:
            pcm = b"\x01\x02" * (CHUNK_BYTES // 2)
            await w._forward_to_mic_socket(pcm)
            got = reader_end.recv(4096)
            assert struct.unpack("<H", got[:2])[0] == len(pcm)
            assert got[2:] == pcm
        finally:
            ear_end.close()
            reader_end.close()

    def test_frame_format(self):
        """Verify binary framing: [chunk_len:u16-LE][pcm_data]."""
        pcm = b"\x01\x02" * 160  # 320 bytes
        frame = struct.pack("<H", len(pcm)) + pcm
        assert len(frame) == 2 + 320
        decoded_len = struct.unpack("<H", frame[:2])[0]
        assert decoded_len == 320
        assert frame[2:] == pcm


# ── Multi-channel capture + XVF3800 voice direction ──────────────

from array import array  # noqa: E402

from supervisor.devices.xvf3800 import VoiceDirection  # noqa: E402
from supervisor.messages.types import EAR_EVENT_DOA  # noqa: E402
from supervisor.workers.ear_worker import select_channel  # noqa: E402


def _interleave(*chans: list[int]) -> bytes:
    out = array("h")
    for frame in zip(*chans):
        out.extend(frame)
    return out.tobytes()


class TestMultiChannel:
    def test_select_channel(self):
        data = _interleave([1, 2, 3], [10, 20, 30])
        assert array("h", select_channel(data, 2, 0)).tolist() == [1, 2, 3]
        assert array("h", select_channel(data, 2, 1)).tolist() == [10, 20, 30]

    def test_mono_passthrough(self):
        assert select_channel(b"\x01\x02", 1, 0) == b"\x01\x02"

    def test_take_channel_handles_split_frames(self):
        w = EarWorker()
        w._mic_channels, w._mic_channel = 2, 1
        data = _interleave([1, 2, 3, 4], [10, 20, 30, 40])
        out = (
            w._take_channel(data[:5])
            + w._take_channel(data[5:11])
            + w._take_channel(data[11:])
        )
        assert array("h", out).tolist() == [10, 20, 30, 40]
        assert not w._capture_rem

    async def test_config_parses_channels_and_xvf(self):
        from supervisor.messages.envelope import make_envelope
        from supervisor.messages.types import EAR_CONFIG_INIT

        w = EarWorker()
        env = make_envelope(
            msg_type=EAR_CONFIG_INIT,
            src="core",
            seq=1,
            payload={
                "mic_device": "match:reSpeaker",
                "mic_channels": 2,
                "mic_channel": 5,  # clamped to 1
                "xvf": {
                    "enabled": True,
                    "poll_hz": 200,
                    "doa_offset_deg": 45,
                    "doa_sign": -1,
                },
            },
        )
        await w.on_message(env)
        assert (w._mic_channels, w._mic_channel) == (2, 1)
        assert w._xvf_enabled is True
        assert w._doa_poll_hz == 50.0
        assert (w._doa_offset_deg, w._doa_sign) == (45.0, -1)


class TestVoiceDirection:
    def _worker(self, sent: list) -> EarWorker:
        w = EarWorker()
        w.send = lambda t, p=None, **kw: sent.append((t, p))  # type: ignore[method-assign]
        return w

    def test_speech_publishes_robot_frame_azimuth(self):
        sent: list = []
        w = self._worker(sent)
        w._doa_offset_deg = -90.0
        w._handle_voice_direction(VoiceDirection(100.0, True, 2.0, (0, 0, 0, 2.0)))
        assert sent[0][0] == EAR_EVENT_DOA
        assert sent[0][1]["speech"] is True
        assert sent[0][1]["azimuth_deg"] == pytest.approx(10.0)
        assert w.health_payload()["doa"]["azimuth_deg"] == pytest.approx(10.0)

    def test_speech_end_sent_once(self):
        sent: list = []
        w = self._worker(sent)
        quiet = VoiceDirection(None, False, 0.0, (0, 0, 0, 0))
        w._handle_voice_direction(quiet)
        assert sent == []
        w._handle_voice_direction(VoiceDirection(0.0, True, 1.0, (0, 0, 0, 1.0)))
        w._handle_voice_direction(quiet)
        w._handle_voice_direction(quiet)
        assert [p["speech"] for _, p in sent] == [True, False]


# ── Wake word speech gate (coughs, sneezes, barks) ───────────────


class _FakeOww:
    def __init__(self, score: float):
        self.score = score
        self.resets = 0

    def predict(self, _samples):
        return {"alexa": self.score}

    def reset(self):
        self.resets += 1


class TestWakeSpeechGate:
    def _worker(self, speech_prob: float | None, gate: float = 0.5):
        w = EarWorker()
        w._oww_model = _FakeOww(0.85)
        w._wake_speech_gate = gate
        w._recent_speech_prob = lambda: speech_prob  # type: ignore[method-assign]
        sent: list[tuple[str, dict]] = []
        w.send = lambda t, p=None: sent.append((t, p or {}))  # type: ignore[method-assign]
        return w, sent

    @staticmethod
    def _wakes(sent):
        from supervisor.messages.types import EAR_EVENT_WAKE_WORD

        return [p for t, p in sent if t == EAR_EVENT_WAKE_WORD]

    @pytest.mark.asyncio
    async def test_bark_without_speech_is_rejected(self):
        w, sent = self._worker(speech_prob=0.09)
        await w._check_wake_word(b"\x00\x00" * (_OWW_FRAME_BYTES // 2))
        assert self._wakes(sent) == []
        assert w._wake_rejected == 1
        assert w.health_payload()["wake_rejected_no_speech"] == 1
        assert w._oww_model.resets == 1

    @pytest.mark.asyncio
    async def test_spoken_wake_word_passes(self):
        w, sent = self._worker(speech_prob=0.93)
        await w._check_wake_word(b"\x00\x00" * (_OWW_FRAME_BYTES // 2))
        assert len(self._wakes(sent)) == 1
        assert w._wake_rejected == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("prob,gate", [(None, 0.5), (0.05, 0.0)])
    async def test_no_vad_or_gate_off_accepts(self, prob, gate):
        w, sent = self._worker(speech_prob=prob, gate=gate)
        await w._check_wake_word(b"\x00\x00" * (_OWW_FRAME_BYTES // 2))
        assert len(self._wakes(sent)) == 1

    def test_tuning_param(self):
        w = EarWorker()
        w._apply_tuning({"wake_speech_gate": 0.7})
        assert w._wake_speech_gate == 0.7
        w._apply_tuning({"wake_speech_gate": 5})
        assert w._wake_speech_gate == 0.95

    def test_chime_holdoff_tunable(self):
        w = EarWorker()
        w._apply_tuning({"chime_holdoff_ms": 250})
        w._start_listening(chime_holdoff=True)
        assert 0.2 < w._vad_holdoff_until - time.monotonic() <= 0.25
        w._stop_listening()
        w._start_listening(chime_holdoff=False)
        assert w._vad_holdoff_until == 0.0

    def test_recent_speech_prob_scans_last_second(self):
        w = EarWorker()
        w._vad_session = _FakeStateVadSession()
        w._vad_schema = "state"
        w._vad_state_shape = (2, 1, 128)
        w._recent_audio = bytearray(b"\x01\x00" * (SAMPLE_RATE))  # 1 s
        probs = iter([0.1] * 10 + [0.8] + [0.2] * 100)
        w._silero_prob = lambda _f: next(probs)  # type: ignore[method-assign]
        assert w._recent_speech_prob() == 0.8
