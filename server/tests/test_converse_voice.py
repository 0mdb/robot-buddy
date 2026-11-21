"""/converse + voice ID: one "speaker" message and one saved clip per kept turn, carrying
the face label the robot sent; a turn dropped by a late resume leaves nothing."""

from __future__ import annotations

from pathlib import Path
import pytest

from app.routers import converse as conv
from app.voice.config import VoiceConfig
from app.voice.service import VoiceService
from tests.test_converse_speculation import (  # noqa: F401 (fixtures)
    _audio,
    _run,
    _ScriptedWS,
    fakes,
    slow_gen,
)
from tests.test_voice_id import voice


class _Emb:
    name = "fake"

    def embed(self, pcm: bytes):
        return voice(0), len(pcm) / 32000


@pytest.fixture
def svc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VoiceService:
    s = VoiceService(
        VoiceConfig(
            capture=True, voice_id=True, data_dir=tmp_path, enroll_min_speech_s=0.05
        ),
        embedder=_Emb(),
    )
    monkeypatch.setattr(conv, "get_voice_service", lambda: s)
    return s


FACE = {"member_id": "owen", "score": 0.9, "faces": 1}


@pytest.mark.asyncio
@pytest.mark.usefixtures("fakes")
async def test_speaker_message_and_clip_per_turn(svc: VoiceService) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            {"type": "profile", "profile": {"face_speaker": FACE}},
            _audio(),
            {"type": "end_utterance"},
            0.1,
        ],
    )
    [spk] = [m for m in ws.sent if m["type"] == "speaker"]
    [tr] = [m for m in ws.sent if m["type"] == "transcription"]
    assert spk["turn_id"] == tr["turn_id"] and spk["learned"]
    [(_, side)] = svc.store.clips()
    assert side["text"] == "words 3200" and side["face"] == FACE
    assert svc.prints.count("owen") == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("fakes")
async def test_committed_speculation_saves_the_whole_utterance(
    svc: VoiceService,
) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            _audio(),
            {"type": "end_utterance", "tentative": True},
            0.05,
            _audio(),
            {"type": "end_utterance"},
            0.1,
        ],
    )
    [(_, side)] = svc.store.clips()
    assert side["audio_s"] == 0.2  # both halves (6400 bytes)


@pytest.mark.asyncio
@pytest.mark.usefixtures("slow_gen")
async def test_late_resume_keeps_only_the_merged_turn(svc: VoiceService) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            _audio(),
            {"type": "end_utterance"},
            0.05,
            {"type": "resume"},
            _audio(),
            {"type": "end_utterance"},
            0.3,
        ],
    )
    clips = svc.store.clips()
    assert [m["text"] for _, m in clips] == ["words 6400"]
    assert [m["type"] for m in ws.sent].count("speaker") == 1
