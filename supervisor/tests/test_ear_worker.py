"""Tests for ear worker — VAD state machine and wake word buffer logic."""

from __future__ import annotations

import struct

from supervisor.workers.ear_worker import (
    CHUNK_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    EarWorker,
    _OWW_FRAME_BYTES,
    _VAD_FRAME_BYTES,
    _WW_COOLDOWN_S,
)


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

    def test_health_reflects_listening(self):
        w = EarWorker()
        w._listening = True
        h = w.health_payload()
        assert h["listening"] is True


# ── Socket framing tests ─────────────────────────────────────────


class TestMicSocketFraming:
    def test_forward_skipped_without_socket(self):
        """No exception when mic socket is None."""
        w = EarWorker()
        w._forward_to_mic_socket(b"\x00" * CHUNK_BYTES)  # should not raise

    def test_frame_format(self):
        """Verify binary framing: [chunk_len:u16-LE][pcm_data]."""
        pcm = b"\x01\x02" * 160  # 320 bytes
        frame = struct.pack("<H", len(pcm)) + pcm
        assert len(frame) == 2 + 320
        decoded_len = struct.unpack("<H", frame[:2])[0]
        assert decoded_len == 320
        assert frame[2:] == pcm
