"""Long-press ring around the touch point (spec §9.5 local feedback).

Fills clockwise from 12 o'clock as the hold approaches TOUCH_LONG_PRESS_MS,
then flashes for TOUCH_RING_FLASH_MS when the long-press fires.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tools.face_sim_v3.render.sdf import sdf_alpha
from tools.face_sim_v3.state.constants import (
    SCREEN_H,
    SCREEN_W,
    TOUCH_RING_RADIUS,
    TOUCH_RING_THICKNESS,
)

_TRACK_ALPHA = 0.25  # unfilled part of the ring
_TWO_PI = 2.0 * math.pi


def _blend(
    buf: list[tuple[int, int, int]],
    idx: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    o = buf[idx]
    buf[idx] = (
        int(o[0] + (color[0] - o[0]) * alpha),
        int(o[1] + (color[1] - o[1]) * alpha),
        int(o[2] + (color[2] - o[2]) * alpha),
    )


@dataclass
class TouchRing:
    """What to draw this frame.

    progress: fill fraction [0, 1], clockwise from 12 o'clock.
    flash:    remaining flash fraction (1 -> 0) after firing; draws a full,
              brightened ring and overrides progress.
    """

    cx: int
    cy: int
    progress: float
    color: tuple[int, int, int]
    flash: float | None = None


def render_touch_ring(buf: list[tuple[int, int, int]], ring: TouchRing) -> None:
    """Draw the long-press ring centred on (ring.cx, ring.cy)."""
    cx, cy = ring.cx, ring.cy
    progress, color, flash = ring.progress, ring.color, ring.flash
    r_mid = TOUCH_RING_RADIUS - TOUCH_RING_THICKNESS / 2.0
    half_t = TOUCH_RING_THICKNESS / 2.0
    if flash is not None:
        progress = 1.0
        # Flash: lerp toward white and back as it decays
        w = flash
        color = (
            int(color[0] + (255 - color[0]) * w),
            int(color[1] + (255 - color[1]) * w),
            int(color[2] + (255 - color[2]) * w),
        )
    sweep = progress * _TWO_PI

    reach = TOUCH_RING_RADIUS + 1
    y0, y1 = max(0, cy - reach), min(SCREEN_H, cy + reach + 1)
    x0, x1 = max(0, cx - reach), min(SCREEN_W, cx + reach + 1)
    for y in range(y0, y1):
        py = y + 0.5 - cy
        row = y * SCREEN_W
        for x in range(x0, x1):
            px = x + 0.5 - cx
            d = math.sqrt(px * px + py * py)
            a = sdf_alpha(abs(d - r_mid) - half_t)
            if a <= 0.01:
                continue
            # Angle clockwise from 12 o'clock (screen y points down)
            ang = math.atan2(px, -py) % _TWO_PI
            if ang <= sweep:
                _blend(buf, row + x, color, a)
            else:
                _blend(buf, row + x, color, a * _TRACK_ALPHA)
