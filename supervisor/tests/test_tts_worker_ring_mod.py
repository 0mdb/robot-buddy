"""Tests for the TTS worker's ring modulator.

The key invariant is that the sine carrier stays phase-continuous across
chunk boundaries — otherwise the effect produces clicks at every 10 ms chunk.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from supervisor.workers.tts_worker import SAMPLE_RATE, TTSWorker


def _pcm_from_int16(samples: np.ndarray) -> bytes:
    return samples.astype(np.int16).tobytes()


def _int16_from_pcm(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32)


def _make_worker(hz: float, mix: float = 1.0) -> TTSWorker:
    w = TTSWorker()
    w._ring_mod_hz = hz
    w._ring_mod_mix = mix
    w._ring_mod_phase = 0.0
    return w


def test_disabled_when_hz_zero() -> None:
    w = _make_worker(hz=0.0)
    pcm_in = _pcm_from_int16(np.full(160, 10_000, dtype=np.int16))
    assert w._apply_ring_mod(pcm_in) == pcm_in


def test_disabled_when_mix_zero() -> None:
    w = _make_worker(hz=50.0, mix=0.0)
    pcm_in = _pcm_from_int16(np.full(160, 10_000, dtype=np.int16))
    assert w._apply_ring_mod(pcm_in) == pcm_in


def test_ring_mod_multiplies_by_sine() -> None:
    """With a DC input, output / input should equal sin(2π f t)."""
    hz = 50.0
    amp = 10_000
    n = 160
    w = _make_worker(hz=hz, mix=1.0)
    pcm_in = _pcm_from_int16(np.full(n, amp, dtype=np.int16))
    out = _int16_from_pcm(w._apply_ring_mod(pcm_in))

    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    expected = amp * np.sin(2.0 * math.pi * hz * t)
    # int16 rounding tolerates ~1 LSB of error.
    np.testing.assert_allclose(out, expected, atol=1.5)


@pytest.mark.parametrize("hz", [30.0, 50.0, 80.0])
def test_phase_continuity_across_chunks(hz: float) -> None:
    """A DC signal split across two chunks must reconstruct one smooth sine."""
    amp = 10_000
    chunk_samples = 160  # 10 ms at 16 kHz

    w = _make_worker(hz=hz, mix=1.0)

    chunk1 = _pcm_from_int16(np.full(chunk_samples, amp, dtype=np.int16))
    chunk2 = _pcm_from_int16(np.full(chunk_samples, amp, dtype=np.int16))

    out1 = _int16_from_pcm(w._apply_ring_mod(chunk1))
    out2 = _int16_from_pcm(w._apply_ring_mod(chunk2))
    joined = np.concatenate([out1, out2])

    # Reference: one continuous sine covering both chunks.
    total = chunk_samples * 2
    t = np.arange(total, dtype=np.float64) / SAMPLE_RATE
    expected = amp * np.sin(2.0 * math.pi * hz * t)

    np.testing.assert_allclose(joined, expected, atol=1.5)

    # No step-change at the boundary: sample[159] → sample[160] should be
    # close to one sample's worth of sine slope, not a fresh restart.
    boundary_delta = abs(joined[chunk_samples] - joined[chunk_samples - 1])
    max_single_step = amp * 2.0 * math.pi * hz / SAMPLE_RATE + 2.0
    assert boundary_delta <= max_single_step


def test_phase_wraps_without_drift_over_many_chunks() -> None:
    """Simulate 1 s of audio (100 chunks) and verify phase stays in [0, 1)."""
    w = _make_worker(hz=50.0, mix=1.0)
    chunk = _pcm_from_int16(np.full(160, 5_000, dtype=np.int16))
    for _ in range(100):
        w._apply_ring_mod(chunk)
    assert 0.0 <= w._ring_mod_phase < 1.0


def test_mix_blends_dry_and_wet() -> None:
    """mix=0.5 → output halfway between dry signal and pure ring mod."""
    hz = 50.0
    amp = 10_000
    n = 160
    w_wet = _make_worker(hz=hz, mix=1.0)
    w_half = _make_worker(hz=hz, mix=0.5)

    pcm_in = _pcm_from_int16(np.full(n, amp, dtype=np.int16))
    wet = _int16_from_pcm(w_wet._apply_ring_mod(pcm_in))
    half = _int16_from_pcm(w_half._apply_ring_mod(pcm_in))

    # half = amp * (0.5 + 0.5 * sine) = 0.5*amp + 0.5*wet
    expected = 0.5 * amp + 0.5 * wet
    np.testing.assert_allclose(half, expected, atol=1.5)
