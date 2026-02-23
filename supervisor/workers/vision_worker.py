"""Vision worker — camera capture + detection via NDJSON BaseWorker.

Replaces v1's multiprocessing-based vision_worker.py.  Runs CV at full
camera FPS internally but emits snapshots to Core at ≤ 10 Hz (§6.2).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    VISION_CONFIG_UPDATE,
    VISION_DETECTION_SNAPSHOT,
    VISION_FRAME_JPEG,
    VISION_LIFECYCLE_ERROR,
)
from supervisor.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

# Emission rate limits (Appendix C)
_SNAPSHOT_MIN_INTERVAL_S = 1.0 / 10  # 10 Hz max
_JPEG_MIN_INTERVAL_S = 1.0 / 5  # 5 Hz max


class VisionWorker(BaseWorker):
    domain = "vision"

    def __init__(self) -> None:
        super().__init__()
        # Config (updated via vision.config.update)
        self._mjpeg_enabled = False
        self._floor_hsv_low = (0, 0, 50)
        self._floor_hsv_high = (180, 80, 220)
        self._ball_hsv_low = (170, 80, 40)
        self._ball_hsv_high = (15, 255, 255)
        self._min_ball_radius = 8
        self._capture_size = (640, 480)
        self._process_size = (320, 240)

        # Stats
        self._frame_count = 0
        self._frame_seq = 0
        self._fps = 0.0
        self._fps_t0 = 0.0
        self._frames_dropped = 0
        self._last_error = ""
        self._camera_ok = False

        # Rate limiting
        self._last_snapshot_t = 0.0
        self._last_jpeg_t = 0.0

    async def on_message(self, envelope: Envelope) -> None:
        if envelope.type == VISION_CONFIG_UPDATE:
            p = envelope.payload
            self._mjpeg_enabled = bool(p.get("mjpeg_enabled", self._mjpeg_enabled))
            if "floor_hsv_low" in p:
                self._floor_hsv_low = tuple(p["floor_hsv_low"])
            if "floor_hsv_high" in p:
                self._floor_hsv_high = tuple(p["floor_hsv_high"])
            if "ball_hsv_low" in p:
                self._ball_hsv_low = tuple(p["ball_hsv_low"])
            if "ball_hsv_high" in p:
                self._ball_hsv_high = tuple(p["ball_hsv_high"])
            if "min_ball_radius" in p:
                self._min_ball_radius = int(p["min_ball_radius"])
            log.info("config updated")

    def health_payload(self) -> dict[str, Any]:
        return {
            "fps": round(self._fps, 1),
            "frames_processed": self._frame_seq,
            "frames_dropped": self._frames_dropped,
            "camera_ok": self._camera_ok,
            "last_error": self._last_error,
        }

    async def run(self) -> None:
        """Main vision loop — capture frames and run detection."""
        try:
            import cv2
            import numpy as np  # noqa: F401 — imported to verify availability
        except ImportError as e:
            self.send(VISION_LIFECYCLE_ERROR, {"error": f"missing dependency: {e}"})
            return

        # Import detectors
        try:
            from supervisor.inputs.detectors import detect_ball, detect_clear_path
        except ImportError:
            self.send(VISION_LIFECYCLE_ERROR, {"error": "detectors not available"})
            return

        # Open camera
        cam = None
        try:
            from picamera2 import Picamera2

            cam = Picamera2(0)
            cam.configure(
                cam.create_video_configuration(
                    main={"size": self._capture_size, "format": "RGB888"},
                )
            )
            cam.start()
            cam.capture_array()  # warm up
            self._camera_ok = True
            log.info("camera opened")
        except Exception as e:
            self._last_error = str(e)
            self._camera_ok = False
            self.send(VISION_LIFECYCLE_ERROR, {"error": f"camera: {e}"})
            log.warning("camera unavailable: %s", e)
            # Stay alive — health heartbeats keep going, camera_ok=False
            await self.shutdown_event.wait()
            return

        self._fps_t0 = time.monotonic()
        loop = asyncio.get_running_loop()

        try:

            def _capture_with_metadata() -> tuple[Any, int]:
                """Blocking capture that returns (rgb_array, t_cam_ns)."""
                request = cam.capture_request()
                try:
                    arr = request.make_array("main")
                    metadata = request.get_metadata()
                    t_cam_ns = metadata.get("SensorTimestamp", 0)
                    return arr, int(t_cam_ns)
                finally:
                    request.release()

            while self.running:
                # Capture in executor to avoid blocking the event loop
                try:
                    rgb, t_cam_ns = await loop.run_in_executor(
                        None, _capture_with_metadata
                    )
                except Exception as e:
                    self._last_error = str(e)
                    self._camera_ok = False
                    log.error("capture error: %s", e)
                    await asyncio.sleep(0.1)
                    continue

                # Process
                rgb = cv2.rotate(rgb, cv2.ROTATE_180)
                small = cv2.resize(rgb, self._process_size)

                clear_conf = detect_clear_path(
                    small, self._floor_hsv_low, self._floor_hsv_high
                )
                ball_result = detect_ball(
                    small,
                    self._ball_hsv_low,
                    self._ball_hsv_high,
                    self._min_ball_radius,
                )

                # FPS tracking
                self._frame_seq += 1
                self._frame_count += 1
                elapsed = time.monotonic() - self._fps_t0
                if elapsed > 5.0:
                    self._fps = self._frame_count / elapsed
                    self._frame_count = 0
                    self._fps_t0 = time.monotonic()

                # Emit snapshot at ≤ 10 Hz (last-value-wins coalescing)
                now = time.monotonic()
                if now - self._last_snapshot_t >= _SNAPSHOT_MIN_INTERVAL_S:
                    self._last_snapshot_t = now
                    t_det_done_ns = time.monotonic_ns()
                    self.send(
                        VISION_DETECTION_SNAPSHOT,
                        {
                            "frame_seq": self._frame_seq,
                            "t_cam_ns": t_cam_ns,
                            "t_det_done_ns": t_det_done_ns,
                            "clear_confidence": round(clear_conf, 3),
                            "ball_confidence": round(ball_result[0], 3)
                            if ball_result
                            else 0.0,
                            "ball_bearing_deg": round(ball_result[1], 1)
                            if ball_result
                            else 0.0,
                            "fps": round(self._fps, 1),
                        },
                    )

                # MJPEG frame at ≤ 5 Hz
                if (
                    self._mjpeg_enabled
                    and now - self._last_jpeg_t >= _JPEG_MIN_INTERVAL_S
                ):
                    self._last_jpeg_t = now
                    _, jpeg = cv2.imencode(
                        ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 50]
                    )
                    self.send(
                        VISION_FRAME_JPEG,
                        {
                            "frame_seq": self._frame_seq,
                            "data_b64": base64.b64encode(jpeg.tobytes()).decode(),
                        },
                    )

        except asyncio.CancelledError:
            pass
        finally:
            if cam:
                try:
                    cam.stop()
                except Exception:
                    pass


if __name__ == "__main__":
    worker_main(VisionWorker)
