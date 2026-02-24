"""Tests for TTS resampling functions (pcm_float32_to_int16, pcm_int16_resample_to_int16)."""

from __future__ import annotations

import struct

import numpy as np

from app.tts.orpheus import (
    OUTPUT_SAMPLE_RATE,
    pcm_float32_to_int16,
    pcm_int16_resample_to_int16,
)


# --- pcm_float32_to_int16 ---


def test_float32_to_int16_identity_rate() -> None:
    """No resampling when src_rate matches output rate."""
    n = 100
    float_audio = np.full(n, 0.5, dtype=np.float32).tobytes()
    result = pcm_float32_to_int16(float_audio, src_rate=OUTPUT_SAMPLE_RATE)
    out = np.frombuffer(result, dtype=np.int16)
    assert len(out) == n
    assert np.all(np.abs(out - 16383) <= 1)


def test_float32_to_int16_resample_24k_to_16k() -> None:
    """Resample 24 kHz to 16 kHz produces correct sample count."""
    n = 2400  # 100 ms at 24 kHz
    float_audio = np.full(n, 0.25, dtype=np.float32).tobytes()
    result = pcm_float32_to_int16(float_audio, src_rate=24000)
    out = np.frombuffer(result, dtype=np.int16)
    assert len(out) == 1600  # 100 ms at 16 kHz


def test_float32_to_int16_max_duration_truncates() -> None:
    """max_duration_s truncates long audio before resampling."""
    n = 48000  # 2 seconds at 24 kHz
    float_audio = np.full(n, 0.1, dtype=np.float32).tobytes()
    result = pcm_float32_to_int16(float_audio, src_rate=24000, max_duration_s=1.0)
    out = np.frombuffer(result, dtype=np.int16)
    # 1 s at 24 kHz = 24000 samples -> resampled to 16 kHz = 16000
    assert len(out) == 16000


def test_float32_to_int16_clamps() -> None:
    """Values outside [-1, 1] are clamped."""
    float_audio = np.array([2.0, -2.0], dtype=np.float32).tobytes()
    result = pcm_float32_to_int16(float_audio, src_rate=OUTPUT_SAMPLE_RATE)
    out = np.frombuffer(result, dtype=np.int16)
    assert out[0] == 32767
    assert out[1] == -32767


def test_float32_to_int16_empty() -> None:
    """Empty / too-small input returns empty bytes."""
    assert pcm_float32_to_int16(b"") == b""
    assert pcm_float32_to_int16(b"\x00") == b""


# --- pcm_int16_resample_to_int16 ---


def test_int16_resample_identity() -> None:
    """No resampling when rates match — returns input unchanged."""
    pcm = struct.pack("<5h", 100, 200, 300, 400, 500)
    result = pcm_int16_resample_to_int16(pcm, src_rate=OUTPUT_SAMPLE_RATE)
    assert result == pcm


def test_int16_resample_24k_to_16k() -> None:
    """Resample 24 kHz to 16 kHz produces correct sample count."""
    n = 2400
    pcm = np.full(n, 1000, dtype=np.int16).tobytes()
    result = pcm_int16_resample_to_int16(pcm, src_rate=24000)
    out = np.frombuffer(result, dtype=np.int16)
    assert len(out) == 1600


def test_int16_resample_max_duration_truncates() -> None:
    """max_duration_s truncates long audio."""
    n = 48000  # 2 s at 24 kHz
    pcm = np.full(n, 500, dtype=np.int16).tobytes()
    result = pcm_int16_resample_to_int16(pcm, src_rate=24000, max_duration_s=1.0)
    out = np.frombuffer(result, dtype=np.int16)
    assert len(out) == 16000


def test_int16_resample_empty() -> None:
    """Empty / too-small input returns empty bytes."""
    assert pcm_int16_resample_to_int16(b"") == b""
    assert pcm_int16_resample_to_int16(b"\x00") == b""


def test_int16_resample_preserves_constant_value() -> None:
    """A constant-valued signal stays constant after resampling."""
    n = 2400
    pcm = np.full(n, 7777, dtype=np.int16).tobytes()
    result = pcm_int16_resample_to_int16(pcm, src_rate=24000)
    out = np.frombuffer(result, dtype=np.int16)
    assert np.all(out == 7777)


def test_float32_to_int16_preserves_constant_value() -> None:
    """A constant float signal maps to a constant int16 value."""
    n = 2400
    float_audio = np.full(n, 0.5, dtype=np.float32).tobytes()
    result = pcm_float32_to_int16(float_audio, src_rate=24000)
    out = np.frombuffer(result, dtype=np.int16)
    expected = int(0.5 * 32767)
    assert np.all(np.abs(out - expected) <= 1)
