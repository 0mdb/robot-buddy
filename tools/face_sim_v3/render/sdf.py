"""SDF (Signed Distance Field) primitive library.

All functions return float: negative = inside shape, positive = outside.
Used for antialiased rendering of eyes, mouth, border, and effects.
"""

from __future__ import annotations

import math


def sd_rounded_box(
    px: float, py: float, cx: float, cy: float, hw: float, hh: float, r: float
) -> float:
    """Rounded rectangle SDF. hw/hh = half-width/half-height, r = corner radius."""
    dx = abs(px - cx) - hw + r
    dy = abs(py - cy) - hh + r
    return min(max(dx, dy), 0.0) + math.sqrt(max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2) - r


def sd_circle(px: float, py: float, cx: float, cy: float, r: float) -> float:
    """Circle SDF."""
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2) - r


def sd_equilateral_triangle(
    px: float, py: float, cx: float, cy: float, r: float
) -> float:
    """Equilateral triangle SDF (point up)."""
    px -= cx
    py -= cy
    k = math.sqrt(3.0)
    px = abs(px) - r
    py = py + r / k
    if px + k * py > 0.0:
        px, py = (px - k * py) / 2.0, (-k * px - py) / 2.0
    px -= max(-2.0 * r, min(0.0, px))
    return -math.sqrt(px * px + py * py) * (1.0 if py < 0.0 else -1.0)


def sd_heart(px: float, py: float, cx: float, cy: float, size: float) -> float:
    """Heart shape SDF. size = scale factor. Negative = inside."""
    x = (px - cx) / size
    y = (cy - py) / size
    ax = abs(x)
    # Circle lobes
    d_circ = math.sqrt((ax - 0.42) ** 2 + (y - 0.32) ** 2) - 0.55
    # V-taper: perpendicular distance to line from (0.97, 0.32) to (0, -0.85)
    if y < 0.32:
        d_taper = 0.769 * ax - 0.638 * (y + 0.85)  # pre-normalized normal
        if y < -0.85:
            d_taper = max(d_taper, -0.85 - y)
    else:
        d_taper = 100.0
    return min(d_circ, d_taper)


def sd_cross(
    px: float, py: float, cx: float, cy: float, size: float, thick: float
) -> float:
    """X/cross shape SDF (rotated 45 degrees). For X-eyes gesture."""
    # Rotate coords 45 deg
    rx = (px - cx) * 0.707 - (py - cy) * 0.707
    ry = (px - cx) * 0.707 + (py - cy) * 0.707
    d1 = sd_rounded_box(rx, ry, 0, 0, thick, size, 1.0)
    d2 = sd_rounded_box(rx, ry, 0, 0, size, thick, 1.0)
    return min(d1, d2)


# ── Utilities ────────────────────────────────────────────────────────


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite interpolation between edge0 and edge1."""
    if edge1 == edge0:
        return 0.0 if x < edge0 else 1.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def sdf_alpha(dist: float, aa_width: float = 1.0) -> float:
    """Convert SDF distance to alpha using smoothstep antialiasing.

    aa_width controls the smoothing band (default 1.0 pixel).
    """
    return 1.0 - smoothstep(-aa_width / 2, aa_width / 2, dist)
