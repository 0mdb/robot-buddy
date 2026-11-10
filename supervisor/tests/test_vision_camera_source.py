"""The vision worker reads frames from a non-Picamera2 source (RB_CAMERA)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import cv2
import numpy as np
import pytest

from supervisor.messages.types import VISION_DETECTION_SNAPSHOT
from supervisor.workers.vision_worker import VisionWorker


def _write_clip(path: Path, frames: int = 30) -> None:
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (640, 480))
    assert out.isOpened()
    floor = np.full(
        (480, 640, 3), 128, dtype=np.uint8
    )  # mid-grey: inside the floor HSV band
    for _ in range(frames):
        out.write(floor)
    out.release()


@pytest.mark.asyncio
async def test_vision_worker_detects_from_a_cv2_source(tmp_path, monkeypatch) -> None:
    clip = tmp_path / "clip.avi"
    _write_clip(clip)
    monkeypatch.setenv("RB_CAMERA", str(clip))

    w = VisionWorker()
    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(w, "send", lambda t, p=None, **k: sent.append((t, p or {})))
    w._running = True
    task = asyncio.create_task(w.run())
    try:
        for _ in range(100):
            if any(t == VISION_DETECTION_SNAPSHOT for t, _ in sent):
                break
            await asyncio.sleep(0.02)
    finally:
        w._running = False
        w.shutdown_event.set()
        await asyncio.wait_for(task, 2)

    snaps = [p for t, p in sent if t == VISION_DETECTION_SNAPSHOT]
    assert snaps, f"no detection snapshot; sent={[t for t, _ in sent]}"
    assert w._camera_ok
    assert snaps[0]["clear_confidence"] > 0.5  # a grey floor fills the frame


@pytest.mark.asyncio
async def test_unopenable_source_reports_and_stays_alive(monkeypatch) -> None:
    monkeypatch.setenv("RB_CAMERA", "/nonexistent/camera")
    w = VisionWorker()
    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(w, "send", lambda t, p=None, **k: sent.append((t, p or {})))
    w._running = True
    task = asyncio.create_task(w.run())
    await asyncio.sleep(0.2)
    assert not task.done(), "worker must stay alive for heartbeats"
    w.shutdown_event.set()
    await asyncio.wait_for(task, 2)
    assert not w._camera_ok
    assert any("camera" in str(p.get("error", "")) for _, p in sent)
