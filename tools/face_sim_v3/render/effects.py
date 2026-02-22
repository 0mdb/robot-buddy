"""Effects rendering — sparkles, fire, afterglow, color utilities.

Extracted from face_render_v2.py for clean separation.
"""

from __future__ import annotations

from tools.face_sim_v3.state.constants import BG_COLOR, SCREEN_H, SCREEN_W


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
