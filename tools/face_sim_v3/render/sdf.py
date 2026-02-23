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
    """Exact heart shape SDF (Inigo Quilez construction).

    Proper signed distance field — smooth everywhere, no cusp singularities.
    Returns negative inside, positive outside.
    size = half-extent; the heart fills roughly ±size pixels from center.

    The IQ heart has tip at origin and lobes at y≈1.1.  We shift by +0.5
    so the heart is vertically centered on (cx, cy), and rescale x by 1/0.6
    so the width fills the size box.
    """
    # Map pixel coords to IQ heart coords (y-flipped, centered, scaled)
    # IQ heart: tip at (0,0), lobes at y≈1.1, width ±0.6
    # Shift +0.5 centers the heart vertically on (cx, cy)
    x = abs(px - cx) / size
    y = (cy - py) / size + 0.5

    # Two regions split by the line x + y = 1
    if y + x > 1.0:
        # Upper/outer region: distance to circle lobe center (0.25, 0.75)
        dx = x - 0.25
        dy = y - 0.75
        d = math.sqrt(dx * dx + dy * dy) - 0.35355339  # sqrt(2)/4
    else:
        # Lower/inner region: min of distance to tip and distance to edge line
        # Distance to bottom tip (0, 1)
        dy1 = y - 1.0
        d1 = x * x + dy1 * dy1

        # Distance to diagonal edge (projection onto x+y=0 half-plane)
        t = max(x + y, 0.0) * 0.5
        dx2 = x - t
        dy2 = y - t
        d2 = dx2 * dx2 + dy2 * dy2

        d = math.sqrt(min(d1, d2))
        # Sign: inside when x < y (left of the diagonal)
        if x < y:
            d = -d

    # Scale back to pixel space
    return d * size


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
