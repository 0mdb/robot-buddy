"""Pure OpenCV detection functions — no camera dependency.

All functions take a BGR numpy array and config parameters, return results.
Stateless and easy to unit test with synthetic images.
"""

from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np

# RPi Camera Module 1.3 (OV5647) horizontal FOV ~ 54 degrees
HFOV_DEG = 54.0


def detect_clear_path(
    frame: np.ndarray,
    floor_hsv_low: Tuple[int, int, int] = (0, 0, 50),
    floor_hsv_high: Tuple[int, int, int] = (180, 80, 220),
) -> float:
    """Estimate how clear the path ahead is based on floor color.

    Looks at the bottom third of the frame. Pixels matching the floor HSV range
    are considered "clear." Returns 0.0..1.0 confidence.

    Args:
        frame: BGR image (e.g. 320x240)
        floor_hsv_low: Lower HSV bound for floor color
        floor_hsv_high: Upper HSV bound for floor color

    Returns:
        Confidence 0.0 (blocked) to 1.0 (fully clear)
    """
    h, w = frame.shape[:2]
    # Bottom third — the region most relevant for immediate obstacles
    roi = frame[h * 2 // 3 :, :]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(floor_hsv_low), np.array(floor_hsv_high))

    total = mask.size
    if total == 0:
        return 0.0

    floor_pixels = int(np.count_nonzero(mask))
    confidence = floor_pixels / total

    # Penalize if the center column is blocked (most dangerous)
    center_strip = mask[:, w // 3 : w * 2 // 3]
    center_total = center_strip.size
    if center_total > 0:
        center_clear = int(np.count_nonzero(center_strip)) / center_total
        # Weight center more heavily
        confidence = 0.4 * confidence + 0.6 * center_clear

    return float(np.clip(confidence, 0.0, 1.0))


# def detect_ball(
#     frame: np.ndarray,
#     # hsv_low: Tuple[int, int, int] = (0, 120, 70),
#     # hsv_high: Tuple[int, int, int] = (15, 255, 255),
#     hsv_low: Tuple[int, int, int] = (170, 120, 70),
#     hsv_high: Tuple[int, int, int] = (10, 255, 255),
#     min_radius_px: int = 10,
#     max_area_px: int = 50000,
# ) -> tuple[float, float] | None:
#     """Detect a colored ball and return its confidence and bearing.

#     Args:
#         frame: BGR image (e.g. 320x240)
#         hsv_low: Lower HSV bound for ball color
#         hsv_high: Upper HSV bound for ball color
#         min_radius_px: Minimum enclosing circle radius to accept
#         max_area_px: Area used to normalize confidence (1.0 = ball fills this many px)

#     Returns:
#         (confidence, bearing_deg) or None if no ball found.
#         bearing_deg: negative = left, positive = right
#     """
#     hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

#     # Handle hue wrap-around for red (H near 0 and near 180)
#     if hsv_low[0] <= hsv_high[0]:
#         mask = cv2.inRange(hsv, np.array(hsv_low), np.array(hsv_high))
#     else:
#         # Wrap-around: e.g. low=(170,S,V) high=(10,S,V)
#         mask1 = cv2.inRange(
#             hsv, np.array(hsv_low), np.array((180, hsv_high[1], hsv_high[2]))
#         )
#         mask2 = cv2.inRange(
#             hsv, np.array((0, hsv_low[1], hsv_low[2])), np.array(hsv_high)
#         )
#         mask = cv2.bitwise_or(mask1, mask2)

#     # Morphological cleanup
#     kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
#     mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
#     mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

#     contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#     if not contours:
#         return None

#     # Find largest contour
#     best = max(contours, key=cv2.contourArea)
#     area = cv2.contourArea(best)

#     (cx, cy), radius = cv2.minEnclosingCircle(best)

#     if radius < min_radius_px:
#         return None

#     # Confidence based on area relative to max expected
#     confidence = float(np.clip(area / max_area_px, 0.0, 1.0))

#     # Bearing: center of frame = 0, left = negative, right = positive
#     frame_w = frame.shape[1]
#     normalized_x = (cx - frame_w / 2) / (frame_w / 2)  # -1..1
#     bearing_deg = normalized_x * (HFOV_DEG / 2)

#     return (confidence, bearing_deg)
def detect_ball(
    frame: np.ndarray,
    # Robust default for red (wrap-around)
    hsv_low: Tuple[int, int, int] = (170, 120, 70),
    hsv_high: Tuple[int, int, int] = (10, 255, 255),
    min_radius_px: int = 10,
    # “Good enough” size where we stop rewarding size (prevents confidence being “always tiny”)
    good_radius_px: int = 35,
    # Morph kernel for 320x240-ish frames; tune if you change process_size a lot
    morph_kernel: Tuple[int, int] = (5, 5),
    # Optional hard gates (set to 0.0 to disable)
    min_circularity: float = 0.55,
    min_fill: float = 0.45,
    min_purity: float = 0.55,
    # Pre-blur helps with speckle/noise
    blur_ksize: int = 5,
) -> tuple[float, float] | None:
    """Detect a colored ball and return (confidence, bearing_deg), or None.

    Inputs:
      - frame: BGR uint8 image (e.g. 320x240)
      - hsv_low/high: HSV bounds; supports wrap-around when low.H > high.H
      - min_radius_px: minimum radius for a valid detection
      - good_radius_px: radius where size_term saturates (confidence stops caring about "bigger")
      - min_circularity/min_fill/min_purity: gates to reduce false positives

    Confidence meaning:
      0..1 likelihood this blob is a ball-like red object, based on size + shape + mask purity.
      Not based on “fills half the frame”.
    """
    if frame is None or frame.size == 0:
        return None

    # Optional blur for stability
    if blur_ksize and blur_ksize >= 3 and blur_ksize % 2 == 1:
        work = cv2.GaussianBlur(frame, (blur_ksize, blur_ksize), 0)
    else:
        work = frame

    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)

    # Handle hue wrap-around for red (H near 0 and near 180)
    if hsv_low[0] <= hsv_high[0]:
        mask = cv2.inRange(hsv, np.array(hsv_low), np.array(hsv_high))
    else:
        mask1 = cv2.inRange(
            hsv, np.array(hsv_low), np.array((180, hsv_high[1], hsv_high[2]))
        )
        mask2 = cv2.inRange(
            hsv, np.array((0, hsv_low[1], hsv_low[2])), np.array(hsv_high)
        )
        mask = cv2.bitwise_or(mask1, mask2)

    # Morphological cleanup
    kx, ky = morph_kernel
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kx, ky))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(best))
    if area <= 1.0:
        return None

    (cx, cy), radius = cv2.minEnclosingCircle(best)
    if radius < float(min_radius_px):
        return None

    # Shape metrics
    perim = float(cv2.arcLength(best, True))
    circularity = (4.0 * np.pi * area) / (perim * perim + 1e-6)  # 0..1

    circle_area = float(np.pi * radius * radius)
    fill = area / (circle_area + 1e-6)  # 0..1

    # Purity: how much of the enclosing circle is actually “red mask”
    circle_mask = np.zeros_like(mask)
    cv2.circle(circle_mask, (int(cx), int(cy)), int(radius), 255, -1)
    inside = cv2.bitwise_and(mask, circle_mask)
    purity = float(np.count_nonzero(inside)) / (float(np.count_nonzero(circle_mask)) + 1e-6)

    # Hard gates (reduce false positives)
    if min_circularity > 0.0 and circularity < min_circularity:
        return None
    if min_fill > 0.0 and fill < min_fill:
        return None
    if min_purity > 0.0 and purity < min_purity:
        return None

    # Size term saturates at "good radius" (so confidence isn’t always tiny)
    good_r = max(float(good_radius_px), float(min_radius_px) + 1.0)
    size_term = float(np.clip((radius - float(min_radius_px)) / (good_r - float(min_radius_px)), 0.0, 1.0))

    # Weighted confidence from shape + purity + size
    shape_term = float(np.clip(0.45 * circularity + 0.35 * fill + 0.20 * purity, 0.0, 1.0))
    confidence = float(np.clip(size_term * shape_term, 0.0, 1.0))

    # Bearing: center of frame = 0, left = negative, right = positive
    frame_w = frame.shape[1]
    normalized_x = (cx - frame_w / 2.0) / (frame_w / 2.0)  # -1..1
    bearing_deg = float(normalized_x * (HFOV_DEG / 2.0))

    return (confidence, bearing_deg)
