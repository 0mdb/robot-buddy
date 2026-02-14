"""Tests for the TTS endpoint and synthesiser."""

from __future__ import annotations

import struct

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tts.schemas import TtsRequest, TtsResult
from app.tts.synth import StubSynthesiser, _make_silent_wav, create_synthesiser


# ---------------------------------------------------------------------------
# Unit: TTS schemas
# ---------------------------------------------------------------------------


def test_tts_request_defaults():
    r = TtsRequest(text="Hello!")
    assert r.emotion == "neutral"
    assert r.intensity == 0.5


def test_tts_request_with_emotion():
    r = TtsRequest(text="Yay!", emotion="excited", intensity=0.9)
    assert r.emotion == "excited"
    assert r.intensity == 0.9


def test_tts_request_text_too_long():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TtsRequest(text="x" * 201)


def test_tts_result_fields():
    r = TtsResult(duration_ms=500, sample_rate=24000, format="wav", emotion="happy")
    assert r.cached is False
    assert r.duration_ms == 500


# ---------------------------------------------------------------------------
# Unit: WAV generation
# ---------------------------------------------------------------------------


def test_make_silent_wav_header():
    wav = _make_silent_wav(num_samples=100, sample_rate=24000)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt "
    assert wav[36:40] == b"data"


def test_make_silent_wav_size():
    num_samples = 480
    wav = _make_silent_wav(num_samples=num_samples, sample_rate=24000)
    # data chunk size = num_samples * 2 bytes (16-bit mono)
    data_size = struct.unpack_from("<I", wav, 40)[0]
    assert data_size == num_samples * 2


# ---------------------------------------------------------------------------
# Unit: StubSynthesiser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stub_synthesiser_returns_wav():
    synth = StubSynthesiser()
    audio, meta = await synth.synthesise("Hello!", "happy", 0.7)
    assert audio[:4] == b"RIFF"
    assert meta.format == "wav"
    assert meta.emotion == "happy"
    assert meta.duration_ms > 0


@pytest.mark.asyncio
async def test_stub_synthesiser_longer_text_longer_audio():
    synth = StubSynthesiser()
    _, short_meta = await synth.synthesise("Hi", "neutral", 0.5)
    _, long_meta = await synth.synthesise(
        "This is a much longer sentence!", "neutral", 0.5
    )
    assert long_meta.duration_ms > short_meta.duration_ms


# ---------------------------------------------------------------------------
# Unit: factory
# ---------------------------------------------------------------------------


def test_create_synthesiser_stub():
    synth = create_synthesiser()
    assert isinstance(synth, StubSynthesiser)


def test_create_synthesiser_unknown(monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "tts_backend", "nonexistent")
    with pytest.raises(ValueError, match="Unknown TTS backend"):
        create_synthesiser()


# ---------------------------------------------------------------------------
# Integration: /tts endpoint
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    app.state.tts = StubSynthesiser()
    return TestClient(app, raise_server_exceptions=False)


def test_tts_endpoint_returns_audio(client):
    resp = client.post(
        "/tts", json={"text": "Hello!", "emotion": "happy", "intensity": 0.8}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert int(resp.headers["x-duration-ms"]) > 0
    assert resp.headers["x-emotion"] == "happy"
    assert resp.content[:4] == b"RIFF"


def test_tts_endpoint_defaults(client):
    resp = client.post("/tts", json={"text": "Hi"})
    assert resp.status_code == 200
    assert resp.headers["x-emotion"] == "neutral"


def test_tts_endpoint_validation(client):
    resp = client.post("/tts", json={"text": "x" * 201})
    assert resp.status_code == 422


def test_tts_endpoint_synth_failure(client, monkeypatch):
    async def bad_synth(self, text, emotion, intensity):
        raise RuntimeError("GPU on fire")

    monkeypatch.setattr(StubSynthesiser, "synthesise", bad_synth)

    resp = client.post("/tts", json={"text": "Hi"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "tts_error"
