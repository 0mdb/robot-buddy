"""Shared lip-sync utilities for converting PCM audio chunks to face energy."""

from __future__ import annotations

import math
import struct


def compute_rms_energy(pcm_chunk: bytes, *, gain: float = 220.0) -> int:
    """Map int16 PCM chunk RMS to 0..255 energy for face mouth animation."""
    if len(pcm_chunk) < 2:
        return 0
    n_samples = len(pcm_chunk) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_chunk[: n_samples * 2])
    rms = math.sqrt(sum(s * s for s in samples) / n_samples) / 32768.0
    return max(0, min(255, int(rms * gain)))


class LipSyncTracker:
    """Applies smoothing to chunk RMS energy to reduce chatter/flicker."""

    def __init__(self, *, attack: float = 0.55, release: float = 0.25) -> None:
        self._attack = max(0.0, min(1.0, float(attack)))
        self._release = max(0.0, min(1.0, float(release)))
        self._value = 0.0

    def reset(self) -> None:
        self._value = 0.0

    def update_chunk(self, pcm_chunk: bytes) -> int:
        target = float(compute_rms_energy(pcm_chunk))
        alpha = self._attack if target > self._value else self._release
        self._value += (target - self._value) * alpha
        return max(0, min(255, int(self._value)))
