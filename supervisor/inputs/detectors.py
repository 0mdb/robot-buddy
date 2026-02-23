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
    hsv_low: Tuple[int, int, int] = (170, 80, 40),  # more forgiving S/V
    hsv_high: Tuple[int, int, int] = (15, 255, 255),
    min_radius_px: int = 8,
    good_radius_px: int = 35,
    blur_ksize: int = 5,
) -> tuple[float, float] | None:
    """
    Forgiving red ball detector for variable lighting.

    - Uses wrap-around hue by default
    - Softer S/V floors
    - Scores candidates by size + circularity + fill + purity (no hard gates)
    """
    if frame is None or frame.size == 0:
        return None

    # Mild blur helps in low light (reduces speckle)
    if blur_ksize >= 3 and blur_ksize % 2 == 1:
        work = cv2.GaussianBlur(frame, (blur_ksize, blur_ksize), 0)
    else:
        work = frame

    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)

    # Hue wrap-around
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

    # Morph: open to remove specks, close + dilate to connect fragments
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best_score = -1.0
    best_cx = 0.0
    best_conf = 0.0

    frame_w = frame.shape[1]

    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area <= 20.0:
            continue

        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        if r < float(min_radius_px):
            continue

        perim = float(cv2.arcLength(cnt, True))
        circularity = (4.0 * np.pi * area) / (perim * perim + 1e-6)  # 0..1

        circle_area = float(np.pi * r * r)
        fill = area / (circle_area + 1e-6)  # 0..1

        circle_mask = np.zeros_like(mask)
        cv2.circle(circle_mask, (int(cx), int(cy)), int(r), 255, -1)
        inside = cv2.bitwise_and(mask, circle_mask)
        purity = float(np.count_nonzero(inside)) / (
            float(np.count_nonzero(circle_mask)) + 1e-6
        )

        # Size term saturates at good_radius_px
        good_r = max(float(good_radius_px), float(min_radius_px) + 1.0)
        size_term = float(
            np.clip(
                (r - float(min_radius_px)) / (good_r - float(min_radius_px)), 0.0, 1.0
            )
        )

        # Soft score (no hard reject): weighted sum
        shape_term = float(
            np.clip(0.45 * circularity + 0.35 * fill + 0.20 * purity, 0.0, 1.0)
        )
        conf = float(np.clip(size_term * shape_term, 0.0, 1.0))

        # Prefer larger + rounder things; add tiny bias toward center to avoid edges/noise
        center_bias = 1.0 - min(1.0, abs((cx - frame_w / 2.0) / (frame_w / 2.0)))
        score = conf + 0.05 * center_bias

        if score > best_score:
            best_score = score
            best_cx = cx
            best_conf = conf

    if best_score < 0.0:
        return None

    normalized_x = (best_cx - frame_w / 2.0) / (frame_w / 2.0)
    bearing_deg = float(normalized_x * (HFOV_DEG / 2.0))

    return (best_conf, bearing_deg)
