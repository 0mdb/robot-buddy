"""Vision worker — camera capture + detection via NDJSON BaseWorker.

Replaces v1's multiprocessing-based vision_worker.py.  Runs CV at full
camera FPS internally but emits snapshots to Core at ≤ 10 Hz (§6.2).
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import logging
import threading
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

        # Camera / ISP config (Picamera2/libcamera) — updated via vision.config.update
        self._rotate_deg = 180
        self._hfov_deg = 66.0
        self._af_mode = 2
        self._lens_position = 1.0
        self._ae_enable = 1
        self._exposure_time_us = 10_000
        self._analogue_gain = 1.0
        self._awb_enable = 1
        self._colour_gain_r = 1.0
        self._colour_gain_b = 1.0
        self._brightness = 0.0
        self._contrast = 1.0
        self._saturation = 1.0
        self._sharpness = 1.0
        self._jpeg_quality = 50

        # Controls are applied from the camera thread to avoid racing capture_request().
        self._pending_controls: dict[str, Any] = {}
        self._pending_controls_lock = threading.Lock()

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

        # Camera format ("BGR888" preferred; fallback to "RGB888" + convert)
        self._camera_main_format = "RGB888"

    def _build_libcamera_controls(self) -> dict[str, Any]:
        """Return libcamera control dict for current camera/ISP settings."""
        controls: dict[str, Any] = {}

        af_mode = int(self._af_mode)
        controls["AfMode"] = af_mode
        if af_mode == 0:
            controls["LensPosition"] = float(self._lens_position)

        ae_enable = bool(int(self._ae_enable))
        controls["AeEnable"] = ae_enable
        if not ae_enable:
            controls["ExposureTime"] = int(self._exposure_time_us)
            controls["AnalogueGain"] = float(self._analogue_gain)

        awb_enable = bool(int(self._awb_enable))
        controls["AwbEnable"] = awb_enable
        if not awb_enable:
            controls["ColourGains"] = (
                float(self._colour_gain_r),
                float(self._colour_gain_b),
            )

        controls["Brightness"] = float(self._brightness)
        controls["Contrast"] = float(self._contrast)
        controls["Saturation"] = float(self._saturation)
        controls["Sharpness"] = float(self._sharpness)

        return controls

    def _queue_controls_apply(self) -> None:
        """Schedule camera controls to be applied on the camera thread."""
        controls = self._build_libcamera_controls()
        with self._pending_controls_lock:
            self._pending_controls = controls

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

            # Camera / ISP
            controls_changed = False
            if "rotate_deg" in p:
                self._rotate_deg = int(p["rotate_deg"])
            if "hfov_deg" in p:
                self._hfov_deg = float(p["hfov_deg"])
            if "af_mode" in p:
                self._af_mode = int(p["af_mode"])
                controls_changed = True
            if "lens_position" in p:
                self._lens_position = float(p["lens_position"])
                controls_changed = True
            if "ae_enable" in p:
                self._ae_enable = int(p["ae_enable"])
                controls_changed = True
            if "exposure_time_us" in p:
                self._exposure_time_us = int(p["exposure_time_us"])
                controls_changed = True
            if "analogue_gain" in p:
                self._analogue_gain = float(p["analogue_gain"])
                controls_changed = True
            if "awb_enable" in p:
                self._awb_enable = int(p["awb_enable"])
                controls_changed = True
            if "colour_gain_r" in p:
                self._colour_gain_r = float(p["colour_gain_r"])
                controls_changed = True
            if "colour_gain_b" in p:
                self._colour_gain_b = float(p["colour_gain_b"])
                controls_changed = True
            if "brightness" in p:
                self._brightness = float(p["brightness"])
                controls_changed = True
            if "contrast" in p:
                self._contrast = float(p["contrast"])
                controls_changed = True
            if "saturation" in p:
                self._saturation = float(p["saturation"])
                controls_changed = True
            if "sharpness" in p:
                self._sharpness = float(p["sharpness"])
                controls_changed = True
            if "jpeg_quality" in p:
                self._jpeg_quality = int(p["jpeg_quality"])

            if controls_changed:
                self._queue_controls_apply()
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
            try:
                cam.configure(
                    cam.create_video_configuration(
                        main={"size": self._capture_size, "format": "BGR888"},
                    )
                )
                self._camera_main_format = "BGR888"
            except Exception:
                cam.configure(
                    cam.create_video_configuration(
                        main={"size": self._capture_size, "format": "RGB888"},
                    )
                )
                self._camera_main_format = "RGB888"
            cam.start()
            self._camera_ok = True
            log.info("camera opened (format=%s)", self._camera_main_format)
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
        cam_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="vision-cam"
        )

        try:

            def _capture_with_metadata() -> tuple[Any, int]:
                """Blocking capture that returns (frame_array, t_cam_ns)."""
                with self._pending_controls_lock:
                    controls = self._pending_controls
                    self._pending_controls = {}
                if controls:
                    try:
                        cam.set_controls(controls)
                    except Exception as e:
                        self._last_error = f"set_controls: {e}"
                request = cam.capture_request()
                try:
                    arr = request.make_array("main")
                    metadata = request.get_metadata()
                    t_cam_ns = metadata.get("SensorTimestamp", 0)
                    return arr, int(t_cam_ns)
                finally:
                    request.release()

            # Apply default controls once and warm up the pipeline
            self._queue_controls_apply()
            try:
                await loop.run_in_executor(cam_executor, _capture_with_metadata)
            except Exception:
                pass

            while self.running:
                # Capture in executor to avoid blocking the event loop
                try:
                    frame, t_cam_ns = await loop.run_in_executor(
                        cam_executor, _capture_with_metadata
                    )
                except Exception as e:
                    self._last_error = str(e)
                    self._camera_ok = False
                    log.error("capture error: %s", e)
                    await asyncio.sleep(0.1)
                    continue

                # Process
                if self._camera_main_format == "RGB888":
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                if self._rotate_deg == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif self._rotate_deg == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif self._rotate_deg == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                small = cv2.resize(frame, self._process_size)

                clear_conf = detect_clear_path(
                    small, self._floor_hsv_low, self._floor_hsv_high
                )
                ball_result = detect_ball(
                    small,
                    self._ball_hsv_low,
                    self._ball_hsv_high,
                    self._min_ball_radius,
                    hfov_deg=self._hfov_deg,
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
                    quality = max(10, min(95, int(self._jpeg_quality)))
                    _, jpeg = cv2.imencode(
                        ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, quality]
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
            cam_executor.shutdown(wait=False, cancel_futures=True)
            if cam:
                try:
                    cam.stop()
                except Exception:
                    pass


if __name__ == "__main__":
    worker_main(VisionWorker)
