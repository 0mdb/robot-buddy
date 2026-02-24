"""Shared lazy runtime objects for STT/TTS backends."""

from __future__ import annotations

import logging

from app.config import settings
from app.tts.orpheus import OrpheusTTS

log = logging.getLogger(__name__)

_stt = None
_tts: OrpheusTTS | None = None


def get_stt():
    global _stt
    if _stt is None:
        try:
            from app.stt.whisper import WhisperSTT

            _stt = WhisperSTT(
                model_size=settings.stt_model_size,
                device=settings.stt_device,
                compute_type=settings.stt_compute_type,
            )
        except ImportError:
            log.warning("faster-whisper not installed. STT unavailable.")
    return _stt


def get_tts() -> OrpheusTTS:
    global _tts
    if _tts is None:
        _tts = OrpheusTTS(
            model_name=settings.tts_model_name,
            backend=settings.tts_backend,
            voice=settings.tts_voice,
            orpheus_voice=settings.orpheus_voice,
            rate_wpm=settings.tts_rate_wpm,
        )
    return _tts


def debug_snapshot() -> dict:
    stt = get_stt()
    tts = get_tts()
    return {
        "stt": stt.debug_snapshot() if stt is not None else {"available": False},
        "tts": tts.debug_snapshot(),
    }
