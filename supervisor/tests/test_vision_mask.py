"""Vision include-mask behavior for detectors (mask editor support)."""

from __future__ import annotations

import cv2
import numpy as np

from supervisor.inputs.detectors import detect_ball, detect_clear_path


def test_detect_clear_path_include_mask_excludes_center_obstacle() -> None:
    h, w = 240, 320

    # "Floor" in default HSV range (low saturation gray)
    frame = np.full((h, w, 3), 100, dtype=np.uint8)

    # Place a non-floor obstacle in the ROI center strip (bottom third).
    frame[h * 2 // 3 :, w // 3 : w * 2 // 3] = (0, 0, 255)  # BGR red, high S

    base = detect_clear_path(frame)
    assert 0.0 <= base < 0.4

    # Exclude the obstacle region → confidence should rise (it's no longer counted).
    include = np.full((h, w), 255, dtype=np.uint8)
    include[h * 2 // 3 :, w // 3 : w * 2 // 3] = 0
    masked = detect_clear_path(frame, include_mask=include)
    assert masked > 0.95

    # Include only the obstacle region → confidence should be ~0.
    include_center = np.zeros((h, w), dtype=np.uint8)
    include_center[h * 2 // 3 :, w // 3 : w * 2 // 3] = 255
    center_only = detect_clear_path(frame, include_mask=include_center)
    assert center_only < 0.01


def test_detect_ball_include_mask_suppresses_detection() -> None:
    h, w = 240, 320
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(frame, (w // 2, h // 2), 30, (0, 0, 255), -1)  # red ball

    found = detect_ball(frame)
    assert found is not None
    conf, _bearing = found
    assert conf > 0.2

    include = np.full((h, w), 255, dtype=np.uint8)
    cv2.circle(include, (w // 2, h // 2), 45, 0, -1)

    blocked = detect_ball(frame, include_mask=include)
    assert blocked is None
