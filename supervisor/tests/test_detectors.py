"""Tests for vision detection functions using synthetic images."""

import cv2
import numpy as np

from supervisor.inputs.detectors import detect_ball, detect_clear_path


def _make_frame(w: int = 320, h: int = 240, color_bgr=(128, 128, 128)) -> np.ndarray:
    """Create a solid-color BGR frame."""
    frame = np.full((h, w, 3), color_bgr, dtype=np.uint8)
    return frame


class TestDetectClearPath:
    def test_all_floor_high_confidence(self):
        # Gray floor — default HSV range should match
        frame = _make_frame(color_bgr=(140, 140, 140))
        conf = detect_clear_path(frame)
        assert conf > 0.7

    def test_bright_obstacle_low_confidence(self):
        # Floor is gray, but paint bottom third bright red (not floor-like)
        frame = _make_frame(color_bgr=(140, 140, 140))
        h = frame.shape[0]
        frame[h * 2 // 3 :, :] = (0, 0, 255)  # bright red
        conf = detect_clear_path(frame)
        assert conf < 0.3

    def test_half_blocked(self):
        # Left half is floor, right half is bright obstacle
        frame = _make_frame(color_bgr=(140, 140, 140))
        h, w = frame.shape[:2]
        frame[h * 2 // 3 :, w // 2 :] = (0, 0, 255)
        conf = detect_clear_path(frame)
        assert 0.15 < conf < 0.7

    def test_center_blocked_penalized(self):
        # Floor everywhere except center column blocked
        frame = _make_frame(color_bgr=(140, 140, 140))
        h, w = frame.shape[:2]
        frame[h * 2 // 3 :, w // 3 : w * 2 // 3] = (0, 0, 255)
        conf = detect_clear_path(frame)
        # Center weighting should penalize this more than edge blocking
        assert conf < 0.5

    def test_custom_floor_color(self):
        # Brown floor with custom HSV
        brown_bgr = (42, 82, 139)  # brownish
        frame = _make_frame(color_bgr=brown_bgr)
        # Convert to find the right HSV range
        hsv_pixel = cv2.cvtColor(
            np.array([[brown_bgr]], dtype=np.uint8), cv2.COLOR_BGR2HSV
        )[0][0]
        h_val = int(hsv_pixel[0])
        low = (max(0, h_val - 10), 50, 50)
        high = (min(180, h_val + 10), 255, 255)
        conf = detect_clear_path(frame, floor_hsv_low=low, floor_hsv_high=high)
        assert conf > 0.7


class TestDetectBall:
    def _draw_ball(self, frame, center, radius, color_bgr):
        """Draw a filled circle on the frame."""
        cv2.circle(frame, center, radius, color_bgr, -1)

    def test_detect_orange_ball_center(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        # Orange ball in center
        self._draw_ball(frame, (160, 120), 30, (0, 120, 255))  # BGR orange
        result = detect_ball(frame, hsv_low=(5, 100, 100), hsv_high=(25, 255, 255))
        assert result is not None
        conf, bearing = result
        assert conf > 0.05
        assert abs(bearing) < 5.0  # near center

    def test_detect_ball_left(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        # Ball on left side
        self._draw_ball(frame, (40, 120), 25, (0, 120, 255))
        result = detect_ball(frame, hsv_low=(5, 100, 100), hsv_high=(25, 255, 255))
        assert result is not None
        _, bearing = result
        assert bearing < -10.0  # should be negative (left)

    def test_detect_ball_right(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        # Ball on right side
        self._draw_ball(frame, (280, 120), 25, (0, 120, 255))
        result = detect_ball(frame, hsv_low=(5, 100, 100), hsv_high=(25, 255, 255))
        assert result is not None
        _, bearing = result
        assert bearing > 10.0  # should be positive (right)

    def test_no_ball_returns_none(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        result = detect_ball(frame, hsv_low=(5, 100, 100), hsv_high=(25, 255, 255))
        assert result is None

    def test_too_small_ball_rejected(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        # Tiny ball below min_radius
        self._draw_ball(frame, (160, 120), 5, (0, 120, 255))
        result = detect_ball(
            frame, hsv_low=(5, 100, 100), hsv_high=(25, 255, 255), min_radius_px=10
        )
        assert result is None

    def test_red_hue_wraparound(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        # Pure red ball (H near 0/180)
        self._draw_ball(frame, (160, 120), 30, (0, 0, 220))
        result = detect_ball(frame, hsv_low=(170, 100, 100), hsv_high=(10, 255, 255))
        assert result is not None

    def test_wrong_color_not_detected(self):
        frame = _make_frame(color_bgr=(140, 140, 140))
        # Blue ball with orange HSV filter
        self._draw_ball(frame, (160, 120), 30, (255, 0, 0))
        result = detect_ball(frame, hsv_low=(5, 100, 100), hsv_high=(25, 255, 255))
        assert result is None
