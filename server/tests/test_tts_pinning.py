"""Tests for pinning Orpheus voice + model selection behavior."""

from __future__ import annotations

import struct

import numpy as np

from app.tts.orpheus import OrpheusTTS


def test_orpheus_tts_backend_passes_voice() -> None:
    class DummyModel:
        def __init__(self) -> None:
            self.seen_voice: str | None = None

        def generate_speech(self, **kwargs):
            self.seen_voice = str(kwargs.get("voice"))
            assert self.seen_voice == "tara"
            # Two int16 samples at 24 kHz so the resampler produces non-empty output.
            yield struct.pack("<2h", 0, 0)

    tts = OrpheusTTS(orpheus_voice="tara")
    tts._loaded = True
    tts._backend = "orpheus_tts"
    tts._model = DummyModel()

    audio = tts._synthesize_sync("Hello", "neutral")
    assert isinstance(audio, (bytes, bytearray))
    assert audio


def test_orpheus_speech_backend_prefixes_voice() -> None:
    def dummy_generate_speech(prompt: str) -> bytes:
        assert prompt.startswith("tara: <happy> Hello")
        return np.zeros(240, dtype=np.float32).tobytes()

    tts = OrpheusTTS(orpheus_voice="tara")
    tts._loaded = True
    tts._backend = "orpheus_speech"
    tts._legacy_generate_speech = dummy_generate_speech

    audio = tts._synthesize_sync("Hello", "happy")
    assert isinstance(audio, (bytes, bytearray))
