"""PlaybackStream: mixing, hard volume cap, silence when idle, cancel, drain."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from supervisor.audio.playback import (
    FRAME_BYTES,
    PlaybackStream,
    mix_frames,
    scale_frame,
)


def pcm(value: int, n_bytes: int = FRAME_BYTES) -> bytes:
    return np.full(n_bytes // 2, value, dtype=np.int16).tobytes()


def vals(frame: bytes) -> np.ndarray:
    return np.frombuffer(frame, dtype=np.int16)


class FakeSink:
    def __init__(self, fail_after: int | None = None, open_ok: bool = True) -> None:
        self.frames: list[bytes] = []
        self.opens = 0
        self.fail_after = fail_after
        self.open_ok = open_ok

    async def open(self) -> bool:
        self.opens += 1
        return self.open_ok

    async def write(self, frame: bytes) -> bool:
        if self.fail_after is not None and len(self.frames) >= self.fail_after:
            self.fail_after = None
            return False
        self.frames.append(frame)
        return True

    async def close(self) -> None:
        pass


def test_mix_saturates() -> None:
    out = vals(mix_frames(pcm(30000), pcm(10000)))
    assert (out == 32767).all()
    out = vals(mix_frames(pcm(-30000), pcm(-10000)))
    assert (out == -32768).all()


def test_scale() -> None:
    assert vals(scale_frame(pcm(10000), 0.5))[0] == 5000
    assert scale_frame(pcm(10000), 1.0) == pcm(10000)


def test_idle_is_silence() -> None:
    s = PlaybackStream(FakeSink())
    assert s.next_frame() == bytes(FRAME_BYTES)


def test_voice_and_fx_mix_and_cap() -> None:
    s = PlaybackStream(FakeSink(), max_volume=0.5)
    s.queue_voice(pcm(8000))
    s.queue_fx(pcm(4000))
    out = vals(s.next_frame())
    assert out[0] == 6000  # (8000 + 4000) * 0.5
    assert s.next_frame() == bytes(FRAME_BYTES)


def test_cap_applies_after_voice_fx() -> None:
    # voice_fx is where the user volume lives; the cap still applies after it.
    s = PlaybackStream(FakeSink(), max_volume=0.25, voice_fx=lambda f: f)
    s.queue_voice(pcm(20000))
    assert vals(s.next_frame())[0] == 5000


def test_voice_fx_sees_each_frame_and_partial_frames_pad() -> None:
    seen: list[int] = []
    s = PlaybackStream(FakeSink(), voice_fx=lambda f: (seen.append(len(f)), f)[1])
    s.queue_voice(pcm(100, FRAME_BYTES + 100))
    s.next_frame()
    s.next_frame()
    assert seen == [FRAME_BYTES, FRAME_BYTES]
    assert not s.voice_active


def test_fx_gain() -> None:
    s = PlaybackStream(FakeSink(), fx_gain=lambda: 0.0)
    s.queue_fx(pcm(9000))
    assert s.next_frame() == bytes(FRAME_BYTES)


def test_flush_voice_keeps_fx() -> None:
    s = PlaybackStream(FakeSink())
    s.queue_voice(pcm(1000) * 10)
    s.queue_fx(pcm(500))
    s.flush_voice()
    assert s.voice_pending_ms == 0 and not s.voice_active
    assert vals(s.next_frame())[0] == 500


@pytest.mark.asyncio
async def test_runs_on_a_clock_and_drains() -> None:
    sink = FakeSink()
    links: list[bool] = []
    s = PlaybackStream(sink, on_link=lambda up, _r: links.append(up))
    s.start()
    s.queue_voice(pcm(1000) * 5)  # 100 ms
    t0 = asyncio.get_running_loop().time()
    await asyncio.wait_for(s.drain_voice(), 1.0)
    elapsed = asyncio.get_running_loop().time() - t0
    await s.stop()
    assert links == [True, False]
    assert elapsed > 0.05  # paced, not dumped at once
    voiced = [f for f in sink.frames if f != bytes(FRAME_BYTES)]
    assert len(voiced) == 5


@pytest.mark.asyncio
async def test_reopens_after_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("supervisor.audio.playback._REOPEN_S", 0.01)
    sink = FakeSink(fail_after=2)
    links: list[bool] = []
    s = PlaybackStream(sink, on_link=lambda up, _r: links.append(up))
    s.start()
    for _ in range(50):
        if sink.opens >= 2 and len(sink.frames) > 3:
            break
        await asyncio.sleep(0.02)
    await s.stop()
    assert sink.opens >= 2
    assert links[:3] == [True, False, True]


@pytest.mark.asyncio
async def test_open_failure_reports_link_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("supervisor.audio.playback._REOPEN_S", 0.01)
    sink = FakeSink(open_ok=False)
    s = PlaybackStream(sink, on_link=lambda up, _r: None)
    s.start()
    await asyncio.sleep(0.05)
    await s.stop()
    assert sink.opens >= 2 and not s.link_up
