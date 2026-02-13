"""Vision process — runs detection in a separate OS process.

Communicates with the main supervisor process via multiprocessing queues.
The main process never imports picamera2 or runs OpenCV — zero GIL interference.
"""

from __future__ import annotations

import logging
import multiprocessing
from dataclasses import dataclass
from queue import Empty, Full

log = logging.getLogger(__name__)


@dataclass(slots=True)
class VisionSnapshot:
    """Output from the vision process."""

    clear_confidence: float = 0.0
    ball_confidence: float = 0.0
    ball_bearing_deg: float = 0.0
    timestamp_mono_ms: float = 0.0
    fps: float = 0.0


def _drain_and_put(q: multiprocessing.Queue, item) -> None:
    try:
        q.get_nowait()
    except Empty:
        pass
    try:
        q.put_nowait(item)
    except Full:
        pass


class VisionProcess:
    """Manages the vision child process and provides non-blocking access to results."""

    def __init__(
        self,
        camera_id: int = 0,
        capture_size: tuple[int, int] = (640, 480),
        process_size: tuple[int, int] = (320, 240),
    ) -> None:
        self._camera_id = camera_id
        self._capture_size = capture_size
        self._process_size = process_size
        self._result_q: multiprocessing.Queue = multiprocessing.Queue(maxsize=2)
        self._frame_q: multiprocessing.Queue = multiprocessing.Queue(maxsize=2)
        self._config_q: multiprocessing.Queue = multiprocessing.Queue(maxsize=2)
        self._proc: multiprocessing.Process | None = None
        self._latest_snap: VisionSnapshot | None = None
        self._latest_frame: bytes | None = None

    def start(self) -> None:
        from supervisor.inputs.vision_worker import vision_main

        self._proc = multiprocessing.Process(
            target=vision_main,
            args=(
                self._result_q,
                self._frame_q,
                self._config_q,
                self._camera_id,
                self._capture_size,
                self._process_size,
            ),
            daemon=True,
            name="vision-worker",
        )
        self._proc.start()
        log.info("vision: process started (pid=%s)", self._proc.pid)

    def stop(self) -> None:
        if self._proc and self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=3)
            log.info("vision: process stopped")
        self._proc = None

    def latest(self) -> VisionSnapshot | None:
        """Return the most recent VisionSnapshot, or None if unavailable.

        Non-blocking — drains the queue to get the freshest result.
        """
        while True:
            try:
                item = self._result_q.get_nowait()
                if item is None:
                    # Worker signalled "no camera"
                    self._latest_snap = None
                else:
                    self._latest_snap = item
            except Empty:
                break
        return self._latest_snap

    def latest_frame(self) -> bytes | None:
        """Return the most recent JPEG frame, or None.

        Non-blocking — drains the queue to get the freshest frame.
        """
        while True:
            try:
                self._latest_frame = self._frame_q.get_nowait()
            except Empty:
                break
        return self._latest_frame

    def set_mjpeg_enabled(self, enabled: bool) -> None:
        _drain_and_put(self._config_q, {"mjpeg": enabled})

    def update_config(self, cfg: dict) -> None:
        """Send config update to the vision worker (HSV thresholds, etc)."""
        _drain_and_put(self._config_q, cfg)

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()
