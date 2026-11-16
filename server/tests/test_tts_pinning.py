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


def test_lead_trim_drops_leading_silence_keeps_a_little() -> None:
    import numpy as np

    from app.tts.orpheus import LeadTrim

    quiet = np.zeros(160, np.int16).tobytes()
    loud = (np.ones(160) * 2000).astype(np.int16).tobytes()
    t = LeadTrim(keep=6)
    out: list[bytes] = []
    for c in [quiet] * 50 + [loud] * 3 + [quiet] * 4:
        out += t.feed(c)
    out += t.flush()
    assert len(out) == 6 + 3 + 4  # 44 leading quiet chunks (440 ms) dropped
    assert out[6] == loud


def test_lead_trim_never_loses_a_quiet_clip() -> None:
    import numpy as np

    from app.tts.orpheus import LeadTrim

    quiet = np.zeros(160, np.int16).tobytes()
    t = LeadTrim(keep=6, max_hold=20)
    out: list[bytes] = []
    for _ in range(30):
        out += t.feed(quiet)
    out += t.flush()
    assert len(out) == 7 + 10  # the held 6 + the 20th at the cap, then passed through


def test_lead_trim_drops_trailing_silence_keeps_mid_pauses() -> None:
    import numpy as np

    from app.tts.orpheus import LeadTrim

    quiet = np.zeros(160, np.int16).tobytes()
    loud = (np.ones(160) * 2000).astype(np.int16).tobytes()
    t = LeadTrim(keep=6, tail_hold=60, tail_keep=15, bridge=5)
    out: list[bytes] = []
    clip = [loud] * 10 + [quiet] * 40 + [loud] * 10 + [quiet] * 60
    for c in clip:
        out += t.feed(c)
    out += t.flush()
    # Mid pause: 50 ms bridge sent (playback idled through the rest while it was
    # held); the 600 ms tail is cut to 150 ms.
    assert out == [loud] * 10 + [quiet] * 5 + [loud] * 10 + [quiet] * 15

    # A tail longer than the hold: the oldest pass through, the end is still cut.
    t = LeadTrim(keep=6, tail_hold=60, tail_keep=15)
    out = []
    for c in [loud] * 3 + [quiet] * 100:
        out += t.feed(c)
    out += t.flush()
    assert out == [loud] * 3 + [quiet] * (40 + 15)
