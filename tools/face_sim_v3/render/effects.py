"""Effects rendering — sparkles, fire, afterglow, color utilities.

Extracted from face_render_v2.py for clean separation.
"""

from __future__ import annotations

from tools.face_sim_v3.state.constants import (
    BG_COLOR,
    SCREEN_H,
    SCREEN_W,
)


# ── Color utilities ──────────────────────────────────────────────────


def clamp_color(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(c[0]))),
        max(0, min(255, int(c[1]))),
        max(0, min(255, int(c[2]))),
    )


def mix_color(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def set_px_blend(
    buf: list, idx: int, color: tuple[int, int, int], alpha: float
) -> None:
    """Blend a color onto a pixel buffer at index with alpha."""
    if alpha <= 0.0 or idx < 0 or idx >= len(buf):
        return
    color = clamp_color(color)
    if alpha >= 1.0:
        buf[idx] = color
    else:
        buf[idx] = mix_color(buf[idx], color, alpha)


def set_px_xy(
    buf: list, x: int, y: int, color: tuple[int, int, int], alpha: float
) -> None:
    """Blend a color at (x, y) with bounds checking."""
    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
        set_px_blend(buf, y * SCREEN_W + x, color, alpha)


# ── Sparkle rendering ────────────────────────────────────────────────


def render_sparkles(buf: list, fs: object) -> None:
    """Render sparkle pixels as white dots with fade."""
    for sx, sy, life in fs.fx.sparkle_pixels:  # type: ignore[attr-defined]
        if 0 <= sx < SCREEN_W and 0 <= sy < SCREEN_H:
            idx = sy * SCREEN_W + sx
            set_px_blend(buf, idx, (255, 255, 255), min(1.0, life / 5.0))


# ── Fire rendering ───────────────────────────────────────────────────


def render_fire(buf: list, fs: object) -> None:
    """Draw fire particles as 3x3 heat blobs during RAGE gesture."""
    for fx, fy, life, heat in fs.fx.fire_pixels:  # type: ignore[attr-defined]
        ix, iy = int(fx), int(fy)
        if heat > 0.85:
            r, g, b = 255, 220, 120
        elif heat > 0.65:
            r, g, b = 255, 140, 20
        elif heat > 0.4:
            r, g, b = 220, 50, 0
        else:
            r, g, b = 130, 20, 0
        fade = min(1.0, life / 5.0)
        color = (int(r * fade), int(g * fade), int(b * fade))
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                px, py = ix + dx, iy + dy
                if 0 <= px < SCREEN_W and 0 <= py < SCREEN_H:
                    idx = py * SCREEN_W + px
                    old = buf[idx]
                    buf[idx] = (
                        max(old[0], color[0]),
                        max(old[1], color[1]),
                        max(old[2], color[2]),
                    )


# ── Afterglow rendering ─────────────────────────────────────────────


def apply_afterglow(buf: list, fs: object) -> None:
    """Blend previous frame for soft fade-out on blink (2/5 intensity)."""
    afterglow_buf = fs.fx.afterglow_buf  # type: ignore[attr-defined]
    if afterglow_buf is None:
        return
    from tools.face_sim_v3.state.constants import AFTERGLOW_DECAY

    for i in range(SCREEN_W * SCREEN_H):
        cr, cg, cb = buf[i]
        pr, pg, pb = afterglow_buf[i]
        if cr <= BG_COLOR[0] and cg <= BG_COLOR[1] and cb <= BG_COLOR[2]:
            if pr > BG_COLOR[0] or pg > BG_COLOR[1] or pb > BG_COLOR[2]:
                buf[i] = (
                    max(BG_COLOR[0], int(pr * AFTERGLOW_DECAY)),
                    max(BG_COLOR[1], int(pg * AFTERGLOW_DECAY)),
                    max(BG_COLOR[2], int(pb * AFTERGLOW_DECAY)),
                )


# ── Snow rendering (Christmas) ─────────────────────────────────────


def render_snow(buf: list, fs: object) -> None:
    """Render falling snow particles as white/blue dots."""
    for sx, sy, life, _phase in fs.fx.snow_pixels:  # type: ignore[attr-defined]
        ix, iy = int(sx), int(sy)
        if 0 <= ix < SCREEN_W and 0 <= iy < SCREEN_H:
            fade = min(1.0, life / 10.0)
            # Alternate white and light blue
            color = (220, 230, 255) if ix % 2 == 0 else (255, 255, 255)
            set_px_xy(buf, ix, iy, color, fade)


# ── Confetti rendering (New Year's) ────────────────────────────────


def render_confetti(buf: list, fs: object) -> None:
    """Render falling confetti as multicolored 2x2 blocks."""
    from tools.face_sim_v3.state.constants import HOLIDAY_CONFETTI_COLORS

    for cx, cy, life, ci in fs.fx.confetti_pixels:  # type: ignore[attr-defined]
        ix, iy = int(cx), int(cy)
        color = HOLIDAY_CONFETTI_COLORS[ci % len(HOLIDAY_CONFETTI_COLORS)]
        fade = min(1.0, life / 8.0)
        for dx in range(2):
            for dy in range(2):
                set_px_xy(buf, ix + dx, iy + dy, color, fade)


# ── Rosy cheeks rendering (Christmas) ──────────────────────────────


def render_rosy_cheeks(buf: list) -> None:
    """Render two subtle pink circles below the eyes."""
    from tools.face_sim_v3.render.sdf import sd_circle, sdf_alpha
    from tools.face_sim_v3.state.constants import (
        LEFT_EYE_CX,
        LEFT_EYE_CY,
        RIGHT_EYE_CX,
        ROSY_CHEEK_ALPHA,
        ROSY_CHEEK_COLOR,
        ROSY_CHEEK_R,
        ROSY_CHEEK_X_OFFSET,
        ROSY_CHEEK_Y_OFFSET,
    )

    cheeks = [
        (LEFT_EYE_CX + ROSY_CHEEK_X_OFFSET, LEFT_EYE_CY + ROSY_CHEEK_Y_OFFSET),
        (RIGHT_EYE_CX - ROSY_CHEEK_X_OFFSET, LEFT_EYE_CY + ROSY_CHEEK_Y_OFFSET),
    ]
    for ccx, ccy in cheeks:
        # Only render in the bounding box around the cheek
        x0 = max(0, int(ccx - ROSY_CHEEK_R - 2))
        x1 = min(SCREEN_W, int(ccx + ROSY_CHEEK_R + 2))
        y0 = max(0, int(ccy - ROSY_CHEEK_R - 2))
        y1 = min(SCREEN_H, int(ccy + ROSY_CHEEK_R + 2))
        for py in range(y0, y1):
            for px in range(x0, x1):
                d = sd_circle(float(px), float(py), ccx, ccy, ROSY_CHEEK_R)
                a = sdf_alpha(d, 2.0) * ROSY_CHEEK_ALPHA
                if a > 0.01:
                    set_px_xy(buf, px, py, ROSY_CHEEK_COLOR, a)
