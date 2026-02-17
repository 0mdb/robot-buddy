"""Orpheus TTS integration — emotional text-to-speech with prosody tags.

Orpheus TTS is a 3B-parameter model that supports emotion tags like <happy>,
<sad>, <surprised>, etc. embedded directly in the input text. It produces
expressive, natural-sounding speech with emotional prosody.

Audio output: 24 kHz, mono, float32 → resampled to 16 kHz 16-bit PCM for
the robot's speaker.
"""

from __future__ import annotations

import logging
import struct
from collections.abc import AsyncIterator

log = logging.getLogger(__name__)

# Map robot emotion names → Orpheus prosody tags
EMOTION_TO_PROSODY_TAG: dict[str, str] = {
    "neutral": "",
    "happy": "<happy>",
    "excited": "<excited>",
    "curious": "",
    "sad": "<sad>",
    "scared": "<scared>",
    "angry": "<angry>",
    "surprised": "<surprised>",
    "sleepy": "<yawn>",
    "love": "<happy>",
    "silly": "<laughing>",
    "thinking": "",
}

# Output PCM format for the robot
OUTPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_WIDTH = 2  # 16-bit signed
OUTPUT_CHANNELS = 1
CHUNK_SAMPLES = 1600  # 100ms chunks at 16 kHz


def apply_prosody_tag(emotion: str, text: str) -> str:
    """Prepend the Orpheus emotion tag to the text."""
    tag = EMOTION_TO_PROSODY_TAG.get(emotion, "")
    if tag:
        return f"{tag} {text}"
    return text


def pcm_float32_to_int16(float_audio: bytes, *, src_rate: int = 24000) -> bytes:
    """Convert float32 audio to 16-bit signed PCM, with optional resampling.

    Simple linear resampling from src_rate to 16 kHz. For production quality,
    use a proper resampler (e.g. scipy.signal.resample_poly).
    """
    n_samples = len(float_audio) // 4
    float_samples = struct.unpack(f"<{n_samples}f", float_audio)

    # Resample if needed
    if src_rate != OUTPUT_SAMPLE_RATE:
        ratio = OUTPUT_SAMPLE_RATE / src_rate
        out_len = int(n_samples * ratio)
        resampled = []
        for i in range(out_len):
            src_idx = i / ratio
            idx = int(src_idx)
            if idx >= n_samples - 1:
                resampled.append(float_samples[-1])
            else:
                frac = src_idx - idx
                resampled.append(
                    float_samples[idx] * (1 - frac) + float_samples[idx + 1] * frac
                )
        float_samples = resampled

    # Convert to 16-bit signed
    int16_samples = []
    for s in float_samples:
        clamped = max(-1.0, min(1.0, s))
        int16_samples.append(int(clamped * 32767))

    return struct.pack(f"<{len(int16_samples)}h", *int16_samples)


class OrpheusTTS:
    """Text-to-speech using Orpheus TTS with emotion prosody.

    The model is loaded lazily on first synthesis call.
    """

    def __init__(
        self,
        model_name: str = "canopylabs/orpheus-3b-0.1-ft",
        device: str = "cuda",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._loaded = False

    def _ensure_model(self) -> None:
        if self._loaded:
            return

        log.info("Loading Orpheus TTS model %s on %s...", self._model_name, self._device)

        # Orpheus TTS loading depends on the specific package version.
        # The orpheus-speech package provides the generation pipeline.
        try:
            import orpheus_speech  # noqa: F401

            self._loaded = True
            log.info("Orpheus TTS model loaded.")
        except ImportError:
            log.warning(
                "orpheus-speech not installed. TTS will return empty audio. "
                "Install with: pip install orpheus-speech"
            )
            self._loaded = True  # Don't retry

    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """Synthesize speech from text with emotional prosody.

        Returns complete PCM audio (16-bit, 16 kHz, mono).
        """
        import asyncio

        return await asyncio.to_thread(self._synthesize_sync, text, emotion)

    def _synthesize_sync(self, text: str, emotion: str) -> bytes:
        """Synchronous synthesis."""
        self._ensure_model()
        tagged_text = apply_prosody_tag(emotion, text)

        try:
            from orpheus_speech import generate_speech

            audio_float32 = generate_speech(tagged_text)
            return pcm_float32_to_int16(audio_float32, src_rate=24000)
        except ImportError:
            log.debug("TTS unavailable, returning empty audio")
            return b""
        except Exception:
            log.exception("TTS synthesis failed for: %s", tagged_text[:80])
            return b""

    async def stream(self, text: str, emotion: str = "neutral") -> AsyncIterator[bytes]:
        """Stream PCM audio chunks as they're generated.

        Yields 100ms chunks of 16-bit 16 kHz mono PCM.
        Falls back to synthesize-then-chunk if streaming isn't supported.
        """
        # For now, synthesize full audio then yield in chunks.
        # True streaming requires deeper Orpheus integration.
        audio = await self.synthesize(text, emotion)

        chunk_bytes = CHUNK_SAMPLES * OUTPUT_SAMPLE_WIDTH
        offset = 0
        while offset < len(audio):
            yield audio[offset : offset + chunk_bytes]
            offset += chunk_bytes
