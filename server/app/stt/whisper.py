"""Whisper STT integration using faster-whisper (CTranslate2)."""

from __future__ import annotations

import io
import logging
import wave
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

# Audio format expected by the transcriber
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1


class WhisperSTT:
    """Speech-to-text using faster-whisper.

    The model is loaded lazily on first transcribe() call to avoid
    blocking startup when STT isn't needed.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info(
                "Loading Whisper model %s on %s (%s)...",
                self._model_size,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            log.info("Whisper model loaded.")
        return self._model

    async def transcribe(self, pcm_audio: bytes) -> str:
        """Transcribe raw PCM audio (16-bit, 16 kHz, mono) to text.

        Runs the model synchronously in a thread to avoid blocking the event loop.
        """
        import asyncio

        return await asyncio.to_thread(self._transcribe_sync, pcm_audio)

    def _transcribe_sync(self, pcm_audio: bytes) -> str:
        """Synchronous transcription from raw PCM bytes."""
        if not pcm_audio:
            return ""

        model = self._ensure_model()

        # Wrap raw PCM as WAV in memory (faster-whisper accepts file-like objects)
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_audio)
        wav_buf.seek(0)

        segments, info = model.transcribe(
            wav_buf,
            language="en",
            vad_filter=True,
            beam_size=5,
        )

        text = " ".join(seg.text.strip() for seg in segments)
        log.info(
            "Transcribed %.1fs audio → %d chars (lang=%s prob=%.2f)",
            info.duration,
            len(text),
            info.language,
            info.language_probability,
        )
        return text
