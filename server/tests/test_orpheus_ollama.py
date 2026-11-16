"""Orpheus on Ollama: token parsing and the 28-token SNAC window (no GPU, no server)."""

from __future__ import annotations

import sys
import types

from app.tts.orpheus_ollama import OllamaOrpheus, audio_code


def test_audio_code_matches_orpheus_tts() -> None:
    assert audio_code(10 + 5, 0) == 5
    assert audio_code(10 + 4096 + 7, 1) == 7
    assert audio_code(10 + 6 * 4096 + 1, 6) == 1
    assert audio_code(10 + 1, 7) == 1  # position wraps every 7


def test_generate_speech_decodes_sliding_windows(monkeypatch) -> None:
    calls: list[list[int]] = []
    fake = types.ModuleType("orpheus_tts.decoder")
    fake.convert_to_audio = lambda codes, count: (
        calls.append(list(codes)) or b"\x01\x00"
    )  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "orpheus_tts.decoder", fake)

    m = OllamaOrpheus("m", "http://x")
    nums = [10 + (i % 7) * 4096 + 100 + i for i in range(42)]  # 42 valid audio tokens
    monkeypatch.setattr(m, "_tokens", lambda prompt, voice: iter(nums))
    out = list(m.generate_speech(prompt="hi", voice="tara"))
    assert len(out) == 3  # windows ending at 28, 35, 42
    assert calls[0] == [100 + i for i in range(28)]
    assert calls[-1] == [100 + i for i in range(14, 42)]
