"""TTS synthesis abstraction with a stub backend.

The synthesiser interface is intentionally simple: text + emotion in,
audio bytes + metadata out.  When a real TTS model (Kokoro, StyleTTS2,
XTTS, etc.) is integrated, add a new class implementing the same
``synthesise`` signature and select it via ``TTS_BACKEND``.
"""

from __future__ import annotations

import io
import logging
import struct
from abc import ABC, abstractmethod

from app.config import settings
from app.tts.schemas import TtsResult

log = logging.getLogger(__name__)


class Synthesiser(ABC):
    """Base class for TTS backends."""

    @abstractmethod
    async def synthesise(
        self, text: str, emotion: str, intensity: float
    ) -> tuple[bytes, TtsResult]:
        """Return (wav_bytes, metadata)."""


class StubSynthesiser(Synthesiser):
    """Generates a short silent WAV — used for API development before a real model is wired up."""

    async def synthesise(
        self, text: str, emotion: str, intensity: float
    ) -> tuple[bytes, TtsResult]:
        sample_rate = settings.tts_sample_rate
        # ~0.5 s of silence, roughly proportional to text length
        num_samples = int(sample_rate * min(len(text) / 40, 5.0))
        duration_ms = int(num_samples / sample_rate * 1000)

        audio = _make_silent_wav(num_samples, sample_rate)

        meta = TtsResult(
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            format="wav",
            emotion=emotion,
            cached=False,
        )
        return audio, meta


def _make_silent_wav(num_samples: int, sample_rate: int) -> bytes:
    """Build a minimal 16-bit mono PCM WAV in memory."""
    bits_per_sample = 16
    num_channels = 1
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align

    buf = io.BytesIO()
    # RIFF header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    # fmt chunk
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))  # chunk size
    buf.write(
        struct.pack(
            "<HHIIHH",
            1,
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        )
    )
    # data chunk
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(b"\x00" * data_size)
    return buf.getvalue()


def create_synthesiser() -> Synthesiser:
    """Factory: pick backend based on config."""
    backend = settings.tts_backend.lower()
    if backend == "stub":
        log.info("Using stub TTS synthesiser (silent audio)")
        return StubSynthesiser()
    raise ValueError(f"Unknown TTS backend: {backend!r}")
