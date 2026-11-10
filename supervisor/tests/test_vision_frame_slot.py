"""The vision worker publishes its picture to a Vantage frame_shm slot (RB_FRAME_SHM, M4)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from supervisor.workers.vision_worker import VisionWorker, _load_frame_shm

VANTAGE = Path(
    os.environ.get("VANTAGE_SUPERVISOR_DIR") or Path.home() / "vantage/supervisor"
)
pytestmark = pytest.mark.skipif(
    not (VANTAGE / "frame_shm.py").exists(),
    reason="needs ~/vantage/supervisor/frame_shm.py",
)


def _write_clip(path: Path, w: int = 640, h: int = 480, frames: int = 60) -> None:
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (w, h))
    assert out.isOpened()
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 2] = (255, 0, 0)  # left half blue (BGR): orientation is checkable
    for _ in range(frames):
        out.write(img)
    out.release()


async def _run_until(w: VisionWorker, cond, timeout: float = 3.0) -> None:
    w._running = True
    task = asyncio.create_task(w.run())
    try:
        t = 0.0
        while not cond() and t < timeout:
            await asyncio.sleep(0.02)
            t += 0.02
    finally:
        w._running = False
        w.shutdown_event.set()
        await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_frames_reach_the_slot_rotated_and_stamped(tmp_path, monkeypatch) -> None:
    clip = tmp_path / "clip.avi"
    _write_clip(clip)
    slot = f"rb_test_slot_{os.getpid()}"
    monkeypatch.setenv("RB_CAMERA", str(clip))
    monkeypatch.setenv("RB_FRAME_SHM", slot)
    fs = _load_frame_shm()

    w = VisionWorker()  # default rotate_deg = 180
    monkeypatch.setattr(w, "send", lambda *a, **k: None)
    got: dict = {}

    def read() -> bool:
        if not got.get("reader"):
            try:
                got["reader"] = fs.FrameReader(slot)
            except FileNotFoundError:
                return False
        r = got["reader"]
        frame = r.read()
        if frame is not None:
            got["frame"] = (
                np.frombuffer(frame[0], np.uint8).reshape(r.height, r.width, 3),
                frame[2],
            )
        return "frame" in got

    t_before_us = __import__("time").monotonic_ns() // 1000
    await _run_until(w, read)
    assert "frame" in got, f"nothing in the slot; health={w.health_payload()}"
    img, t_us = got["frame"]
    assert img.shape == (480, 640, 3)
    # Rotated 180: the blue half is now on the right.
    assert img[240, 600, 0] > 200 and img[240, 40, 0] < 50
    assert t_before_us <= t_us <= __import__("time").monotonic_ns() // 1000
    assert w.health_payload()["frames_published"] > 0
    # Closed on shutdown: a reader holding the mapping is told, and reopens by name.
    with pytest.raises(fs.SlotGone):
        got["reader"].read()
    got["reader"].close()


@pytest.mark.asyncio
async def test_no_slot_unless_asked(tmp_path, monkeypatch) -> None:
    clip = tmp_path / "clip.avi"
    _write_clip(clip, frames=10)
    monkeypatch.setenv("RB_CAMERA", str(clip))
    monkeypatch.delenv("RB_FRAME_SHM", raising=False)
    w = VisionWorker()
    monkeypatch.setattr(w, "send", lambda *a, **k: None)
    await _run_until(w, lambda: w._frame_seq > 3)
    assert w._frame_seq > 3
    assert w.health_payload()["frames_published"] == 0


@pytest.mark.asyncio
async def test_a_missing_vantage_checkout_disables_video_not_vision(
    tmp_path, monkeypatch
) -> None:
    clip = tmp_path / "clip.avi"
    _write_clip(clip, frames=10)
    monkeypatch.setenv("RB_CAMERA", str(clip))
    monkeypatch.setenv("RB_FRAME_SHM", f"rb_test_missing_{os.getpid()}")
    monkeypatch.setenv("VANTAGE_SUPERVISOR_DIR", str(tmp_path / "nowhere"))
    w = VisionWorker()
    monkeypatch.setattr(w, "send", lambda *a, **k: None)
    await _run_until(w, lambda: w._frame_seq > 3)
    assert w._frame_seq > 3, "vision kept running"
    assert w.health_payload()["frames_published"] == 0
    assert w._frame_shm_failed, "video disabled once, cleanly"
