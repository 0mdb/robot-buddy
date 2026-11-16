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


def _hsv_fill(h: int, w: int, hsv: tuple[int, int, int]) -> np.ndarray:
    px = np.full((h, w, 3), hsv, dtype=np.uint8)
    return cv2.cvtColor(px, cv2.COLOR_HSV2BGR)


def test_a_warm_wall_is_not_a_ball() -> None:
    # 2026-11-16: a beige wall the camera saw as hue 12, saturation 172 filled the right
    # side of the frame and scored 0.50; Buddy kept saying "I found a ball!".
    h, w = 240, 320
    frame = np.full((h, w, 3), 30, dtype=np.uint8)  # dark curtain
    frame[:, 176:] = _hsv_fill(h, w - 176, (12, 172, 122))
    assert detect_ball(frame) is None


def test_a_ball_in_front_of_that_wall_is_still_found() -> None:
    h, w = 240, 320
    frame = np.full((h, w, 3), 30, dtype=np.uint8)
    frame[:, 176:] = _hsv_fill(h, w - 176, (12, 172, 122))
    # A red ball over the dark part (its blob is separate from the wall's).
    cv2.circle(frame, (90, 150), 28, (0, 0, 220), -1)
    found = detect_ball(frame)
    assert found is not None and found[0] > 0.2 and found[1] < 0  # left of centre


def test_a_flat_patch_of_wall_colour_is_not_a_ball_either() -> None:
    # Shape gates alone passed a 60x60 square of the wall's colour (0.74); the default
    # hue range now stops at 8, below the wall's 12.
    frame = np.full((240, 320, 3), 30, dtype=np.uint8)
    frame[90:150, 130:190] = _hsv_fill(60, 60, (12, 172, 122))
    assert detect_ball(frame) is None


def test_fingers_holding_the_ball_do_not_hide_it() -> None:
    # Fingertips read hue ~175, saturation ~143 next to the ball (sat ~207); with the old
    # saturation floor (80) they merged with it into one ragged blob that was rejected.
    h, w = 240, 320
    frame = np.full((h, w, 3), 30, dtype=np.uint8)
    for x in (110, 140, 170, 200):  # four fingers coming down onto the ball
        frame[0:60, x - 8 : x + 8] = _hsv_fill(60, 16, (175, 143, 170))
    ball = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(ball, (155, 85), 34, 255, -1)
    frame[ball > 0] = cv2.cvtColor(
        np.full((1, 1, 3), (171, 207, 145), dtype=np.uint8), cv2.COLOR_HSV2BGR
    )[0, 0]
    found = detect_ball(frame)
    assert found is not None and found[0] > 0.5
