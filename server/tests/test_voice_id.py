"""Voice ID: prints, capture, and the per-turn service (fake embedder, no model)."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import time
from pathlib import Path

import numpy as np
import pytest

from app.voice.capture import TurnAudioStore, read_wav
from app.voice.config import VoiceConfig
from app.voice.embed import speech_frames
from app.voice.prints import VoicePrintStore
from app.voice.service import VoiceService

DIM = 16


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def voice(i: int, jitter: float = 0.0, seed: int = 0) -> np.ndarray:
    """A synthetic speaker: axis i, with a little noise."""
    rng = np.random.default_rng(seed)
    v = np.zeros(DIM, np.float32)
    v[i] = 1.0
    return unit(v + jitter * rng.standard_normal(DIM).astype(np.float32))


def tone_pcm(seconds: float, amp: float = 0.3) -> bytes:
    t = np.arange(int(16000 * seconds)) / 16000
    return (amp * 32767 * np.sin(2 * np.pi * 220 * t)).astype("<i2").tobytes()


# -- prints ---------------------------------------------------------------


def test_match_needs_score_and_margin(tmp_path: Path) -> None:
    p = VoicePrintStore(tmp_path / "vp.json")
    for s in range(3):
        p.add("owen", voice(0, 0.2, s), speech_s=2, source="face")
        p.add("ben", voice(1, 0.2, s + 10), speech_s=2, source="face")
    m = p.match(voice(0, 0.2, 99), threshold=0.45, margin=0.08)
    assert m.member_id == "owen" and m.runner_id == "ben"
    # Halfway between the two: nobody leads clearly.
    mid = unit(voice(0) + voice(1))
    m = p.match(mid, threshold=0.45, margin=0.08)
    assert m.member_id is None and m.best_id in {"owen", "ben"}


def test_prints_persist_private_and_without_names(tmp_path: Path) -> None:
    path = tmp_path / "voice" / "vp.json"
    p = VoicePrintStore(path)
    assert p.add("m1", voice(0), speech_s=2.0, source="face")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    again = VoicePrintStore(path)
    assert again.count("m1") == 1
    assert set(json.loads(path.read_text())["members"]) == {"m1"}


def test_duplicate_rejected_and_full_set_drops_most_redundant(tmp_path: Path) -> None:
    p = VoicePrintStore(tmp_path / "vp.json", max_per_member=3)
    assert p.add("m", voice(0), speech_s=2, source="face")
    assert not p.add("m", voice(0), speech_s=2, source="face")  # same voice again
    p.add("m", voice(0, 0.3, 1), speech_s=2, source="face")
    p.add("m", voice(0, 0.3, 2), speech_s=2, source="face")
    p.add("m", voice(2), speech_s=2, source="face")  # an outlier: varied, kept
    assert p.count("m") == 3
    assert p.match(voice(2), threshold=0.0, margin=0.0).score > 0.3


def test_forget_and_keep_only(tmp_path: Path) -> None:
    p = VoicePrintStore(tmp_path / "vp.json")
    p.add("a", voice(0), speech_s=2, source="face")
    p.add("b", voice(1), speech_s=2, source="face")
    assert p.keep_only({"a"}) == ["b"]
    assert p.forget("a") and not p.forget("a")
    assert p.summary() == {}


# -- capture --------------------------------------------------------------


def test_capture_saves_private_wav_and_sidecar(tmp_path: Path) -> None:
    store = TurnAudioStore(tmp_path)
    pcm = tone_pcm(1.0)
    wav = store.save(
        pcm, {"turn_id": "t1", "text": "seven", "face": {"member_id": "o"}}
    )
    assert read_wav(wav) == pcm
    side = json.loads(wav.with_suffix(".json").read_text())
    assert side["text"] == "seven" and side["audio_s"] == 1.0
    for path in (wav, wav.with_suffix(".json")):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(wav.parent).st_mode) == 0o700
    assert store.forget_member("o") == 1 and store.clips() == []


def test_capture_prunes_old_days_and_oversize(tmp_path: Path) -> None:
    store = TurnAudioStore(tmp_path, keep_days=2, max_mb=0)
    now = time.time()
    store.save(tone_pcm(0.5), {"turn_id": "old"}, now=now - 5 * 86400)
    store.save(tone_pcm(0.5), {"turn_id": "y"}, now=now - 86400)
    store.save(tone_pcm(0.5), {"turn_id": "today"}, now=now)
    store.prune(now=now)
    # The 5-day-old day goes by age, yesterday by size (max 0 MB); today always stays.
    assert [m["turn_id"] for _, m in store.clips()] == ["today"]


def test_speech_frames_skips_silence() -> None:
    pcm = b"\x00\x00" * 16000 + tone_pcm(1.0) + b"\x00\x00" * 16000
    speech, s = speech_frames(pcm)
    assert 0.9 <= s <= 1.1 and len(speech) < 1.2 * 16000


# -- service --------------------------------------------------------------


class FakeEmbedder:
    name = "fake"

    def __init__(self) -> None:
        self.next: list[tuple[np.ndarray | None, float]] = []

    def embed(self, pcm: bytes):
        return self.next.pop(0)


def make_service(tmp_path: Path, **kw) -> tuple[VoiceService, FakeEmbedder]:
    cfg = VoiceConfig(capture=True, voice_id=True, data_dir=tmp_path, **kw)
    emb = FakeEmbedder()
    return VoiceService(cfg, embedder=emb), emb


async def done_task() -> asyncio.Task[None]:
    async def _noop() -> None:
        return None

    t = asyncio.create_task(_noop())
    await t
    return t


FACE_OWEN = {"member_id": "owen", "score": 0.8, "faces": 1}


@pytest.mark.asyncio
async def test_learns_from_a_clear_face_and_saves_the_clip(tmp_path: Path) -> None:
    svc, emb = make_service(tmp_path)
    sess = svc.session()
    emb.next.append((voice(0), 2.0))
    msg = await sess.process(
        tone_pcm(2.0),
        turn_task=await done_task(),
        turn_meta={"text": "I like rockets", "turn_id": "t1"},
        face=FACE_OWEN,
    )
    assert msg and msg["type"] == "speaker" and msg["learned"]
    assert svc.prints.count("owen") == 1
    [(_, side)] = svc.store.clips()
    assert side["learn"]["added"] and side["face"]["member_id"] == "owen"


@pytest.mark.parametrize(
    ("face", "speech_s", "text", "why"),
    [
        (None, 2.0, "hi", "no face label"),
        ({**FACE_OWEN, "faces": 2}, 2.0, "hi", "more than one face"),
        ({**FACE_OWEN, "score": 0.4}, 2.0, "hi", "face score low"),
        (FACE_OWEN, 0.8, "seven", "short"),
        (FACE_OWEN, 2.0, "  ", "no words"),
    ],
)
@pytest.mark.asyncio
async def test_does_not_learn_when_unsure(tmp_path, face, speech_s, text, why) -> None:
    svc, emb = make_service(tmp_path)
    emb.next.append((voice(0), speech_s))
    msg = await svc.session().process(
        b"\x00" * 100, turn_task=None, turn_meta={"text": text}, face=face
    )
    assert msg and not msg["learned"] and msg["learn_why"] == why


@pytest.mark.asyncio
async def test_off_camera_child_does_not_poison_parent_prints(tmp_path: Path) -> None:
    """Dad's face in view, Owen talking: the voice sounds like Owen, so Dad gets nothing."""
    svc, emb = make_service(tmp_path)
    for s in range(3):
        svc.prints.add("owen", voice(0, 0.2, s), speech_s=2, source="face")
        svc.prints.add("ben", voice(1, 0.2, s + 5), speech_s=2, source="face")
    emb.next.append((voice(0, 0.2, 42), 2.5))
    face_ben = {"member_id": "ben", "score": 0.9, "faces": 1}
    msg = await svc.session().process(
        b"", turn_task=None, turn_meta={"text": "eight"}, face=face_ben
    )
    assert msg["turn"]["member_id"] == "owen"
    assert not msg["learned"] and msg["learn_why"] == "sounds like owen"
    assert svc.prints.count("ben") == 3


@pytest.mark.asyncio
async def test_dropped_turn_is_discarded(tmp_path: Path) -> None:
    svc, emb = make_service(tmp_path)
    emb.next.append((voice(0), 2.0))

    async def _long() -> None:
        await asyncio.sleep(10)

    turn = asyncio.create_task(_long())
    proc = asyncio.create_task(
        svc.session().process(b"", turn_task=turn, turn_meta={}, face=FACE_OWEN)
    )
    await asyncio.sleep(0.01)
    turn.cancel()
    assert await proc is None
    assert svc.store.clips() == [] and svc.prints.count("owen") == 0


@pytest.mark.asyncio
async def test_session_average_names_short_answers(tmp_path: Path) -> None:
    """Short noisy clips each fall short alone; the conversation's average is clear."""
    svc, emb = make_service(tmp_path, match_score=0.6)
    for s in range(3):
        svc.prints.add("owen", voice(0, 0.1, s), speech_s=2, source="face")
        svc.prints.add("clark", voice(1, 0.1, s + 5), speech_s=2, source="face")
    sess = svc.session()
    msgs = []
    for s in range(6):
        emb.next.append((voice(0, 0.5, 100 + s), 0.6))
        msgs.append(
            await sess.process(b"", turn_task=None, turn_meta={"text": "7"}, face=None)
        )
    assert all(m["turn"]["member_id"] is None for m in msgs[:2])
    assert msgs[-1]["session"]["member_id"] == "owen"
    assert msgs[-1]["session"]["score"] > max(m["turn"]["score"] for m in msgs)


@pytest.mark.asyncio
async def test_roster_ids_prune_removed_members(tmp_path: Path) -> None:
    svc, _ = make_service(tmp_path)
    svc.prints.add("gone", voice(3), speech_s=2, source="face")
    svc.prints.add("kept", voice(4), speech_s=2, source="face")
    sess = svc.session()
    sess.update_profile({"roster_ids": ["kept"], "face_speaker": FACE_OWEN})
    assert set(svc.prints.summary()) == {"kept"}
    assert sess.face == FACE_OWEN
    sess.update_profile({})
    assert sess.face is None and set(svc.prints.summary()) == {"kept"}


@pytest.mark.asyncio
async def test_capture_only_saves_without_embedding(tmp_path: Path) -> None:
    cfg = VoiceConfig(capture=True, voice_id=False, data_dir=tmp_path)
    svc = VoiceService(cfg, embedder=object())
    msg = await svc.session().process(
        tone_pcm(1.0),
        turn_task=None,
        turn_meta={"text": "hi", "turn_id": "x"},
        face=None,
    )
    assert msg is None
    assert [m["turn_id"] for _, m in svc.store.clips()] == ["x"]
