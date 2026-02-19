"""Vision worker — runs in a child process via multiprocessing.

Captures frames from picamera2, runs detection, publishes results via queues.
Imports picamera2 only inside this process to keep the main process clean.
"""

from __future__ import annotations

import logging
import multiprocessing
import time
from queue import Empty, Full

import cv2

from supervisor.inputs.camera_vision import VisionSnapshot
from supervisor.inputs.detectors import detect_ball, detect_clear_path

log = logging.getLogger(__name__)


def drain_and_put(q: multiprocessing.Queue, item) -> None:
    """Put an item on a queue, discarding any stale value first."""
    try:
        q.get_nowait()
    except Empty:
        pass
    try:
        q.put_nowait(item)
    except Full:
        pass


def vision_main(
    result_q: multiprocessing.Queue,
    frame_q: multiprocessing.Queue,
    config_q: multiprocessing.Queue,
    camera_id: int = 0,
    capture_size: tuple[int, int] = (640, 480),
    process_size: tuple[int, int] = (320, 240),
) -> None:
    """Entry point for the vision child process."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Try to import and open camera
    try:
        from picamera2 import Picamera2

        cam = Picamera2(camera_id)
        cam.configure(
            cam.create_video_configuration(
                # main={"size": capture_size, "format": "RGB888"},
                main={"size": capture_size, "format": "BGRA2BGR"},
            )
        )
        cam.start()
        log.info("vision_worker: camera started (%dx%d)", *capture_size)
    except Exception as e:
        log.warning("vision_worker: camera unavailable (%s), exiting", e)
        # Signal "no camera" and exit
        drain_and_put(result_q, None)
        return

    # Tunable config (updated via config_q)
    mjpeg_enabled = False
    floor_hsv_low = (0, 0, 50)
    floor_hsv_high = (180, 80, 220)
    ball_hsv_low = (0, 120, 70)
    ball_hsv_high = (15, 255, 255)
    min_ball_radius = 10

    frame_count = 0
    fps_t0 = time.monotonic()

    try:
        while True:
            # Check for config updates (non-blocking)
            try:
                cfg = config_q.get_nowait()
                if isinstance(cfg, dict):
                    mjpeg_enabled = cfg.get("mjpeg", mjpeg_enabled)
                    if "floor_hsv_low" in cfg:
                        floor_hsv_low = tuple(cfg["floor_hsv_low"])
                    if "floor_hsv_high" in cfg:
                        floor_hsv_high = tuple(cfg["floor_hsv_high"])
                    if "ball_hsv_low" in cfg:
                        ball_hsv_low = tuple(cfg["ball_hsv_low"])
                    if "ball_hsv_high" in cfg:
                        ball_hsv_high = tuple(cfg["ball_hsv_high"])
                    if "min_ball_radius" in cfg:
                        min_ball_radius = cfg["min_ball_radius"]
                    log.info("vision_worker: config updated")
            except Empty:
                pass

            # Capture
            rgb = cam.capture_array()
            # bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_BGRA2BGR)
            bgr = cv2.rotate(bgr, cv2.ROTATE_180)
            small = cv2.resize(bgr, process_size)

            # Detect
            clear_conf = detect_clear_path(small, floor_hsv_low, floor_hsv_high)
            ball_result = detect_ball(
                small, ball_hsv_low, ball_hsv_high, min_ball_radius
            )

            # FPS tracking
            frame_count += 1
            elapsed = time.monotonic() - fps_t0
            fps = frame_count / elapsed if elapsed > 0 else 0.0
            if elapsed > 5.0:
                frame_count = 0
                fps_t0 = time.monotonic()

            snap = VisionSnapshot(
                clear_confidence=clear_conf,
                ball_confidence=ball_result[0] if ball_result else 0.0,
                ball_bearing_deg=ball_result[1] if ball_result else 0.0,
                timestamp_mono_ms=time.monotonic() * 1000.0,
                fps=fps,
            )
            drain_and_put(result_q, snap)

            # Optional MJPEG frame
            if mjpeg_enabled:
                _, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 50])
                drain_and_put(frame_q, jpeg.tobytes())

    except KeyboardInterrupt:
        pass
    finally:
        try:
            cam.stop()
        except Exception:
            pass
        log.info("vision_worker: stopped")
