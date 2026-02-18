"""Face renderer v2: converts FaceState into a 320x240 RGB pixel buffer.

Targets the 320x240 TFT in landscape orientation. Rendering approach matches
the ESP32 firmware (face_ui.cpp) with additional visual effects ported from
the old 16x16 LED renderer for design iteration.

Output is a flat list of (R, G, B) tuples, row-major, 320*240 entries.
"""

from __future__ import annotations

import math
import time
from face_state_v2 import (
    FaceState, SystemMode,
    SCREEN_W, SCREEN_H,
    EYE_WIDTH, EYE_HEIGHT, EYE_CORNER_R, PUPIL_R,
    LEFT_EYE_CX, LEFT_EYE_CY, RIGHT_EYE_CX, RIGHT_EYE_CY,
    GAZE_EYE_SHIFT, GAZE_PUPIL_SHIFT,
    MOUTH_CX, MOUTH_CY, MOUTH_HALF_W, MOUTH_THICKNESS,
    get_breath_scale, get_emotion_color,
)

BG_COLOR = (0, 0, 0)

# ── Pixel buffer helpers ─────────────────────────────────────────────

def _idx(x: int, y: int) -> int:
    return y * SCREEN_W + x


def _set_px(buf: list[tuple[int, int, int]], x: int, y: int,
            color: tuple[int, int, int]) -> None:
    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
        buf[_idx(x, y)] = color


def _get_px(buf: list[tuple[int, int, int]], x: int, y: int
            ) -> tuple[int, int, int]:
    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
        return buf[_idx(x, y)]
    return BG_COLOR


def _blend_max(buf: list[tuple[int, int, int]], x: int, y: int,
               color: tuple[int, int, int]) -> None:
    """Additive-max blend: take the brighter channel per pixel."""
    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
        old = buf[_idx(x, y)]
        buf[_idx(x, y)] = (
            max(old[0], color[0]),
            max(old[1], color[1]),
            max(old[2], color[2]),
        )


# ── Geometry helpers ─────────────────────────────────────────────────

def _in_rounded_rect(px: float, py: float,
                     cx: float, cy: float,
                     hw: float, hh: float,
                     r: float) -> bool:
    if hw <= 0 or hh <= 0:
        return False
    r = min(r, hw, hh)
    dx = abs(px - cx)
    dy = abs(py - cy)
    if dx > hw or dy > hh:
        return False
    if dx <= hw - r or dy <= hh - r:
        return True
    corner_dx = dx - (hw - r)
    corner_dy = dy - (hh - r)
    return (corner_dx * corner_dx + corner_dy * corner_dy) <= r * r


def _in_circle(px: float, py: float, cx: float, cy: float, r: float) -> bool:
    dx = px - cx
    dy = py - cy
    return (dx * dx + dy * dy) <= r * r


def _dist_to_edge(px: float, py: float,
                  cx: float, cy: float,
                  hw: float, hh: float) -> float:
    dx = hw - abs(px - cx)
    dy = hh - abs(py - cy)
    return max(0.0, min(dx, dy))


def _in_heart(px: float, py: float, cx: float, cy: float, size: float) -> bool:
    x = (px - cx) / size
    y = (cy - py) / size + 0.3
    x2 = x * x
    y2 = y * y
    return (x2 + y2 - 1.0) ** 3 - x2 * (y ** 3) <= 0


def _in_x_shape(px: float, py: float, cx: float, cy: float,
                size: float, thickness: float = 5.0) -> bool:
    dx = abs(px - cx)
    dy = abs(py - cy)
    if dx > size or dy > size:
        return False
    return abs(dx - dy) < thickness


# ── Eyelid masks ─────────────────────────────────────────────────────

def _tired_mask(px: float, py: float, cx: float, top_y: float,
                hw: float, amount: float) -> bool:
    if amount < 0.01:
        return False
    max_droop = hw * 0.7 * amount
    dist_from_center = abs(px - cx)
    droop_at_x = max_droop * (dist_from_center / max(hw, 0.01))
    return py < top_y + droop_at_x


def _angry_mask(px: float, py: float, cx: float, top_y: float,
                hw: float, amount: float, is_left: bool) -> bool:
    if amount < 0.01:
        return False
    max_droop = hw * 0.6 * amount
    t = (px - (cx - hw)) / max(2 * hw, 0.01)
    if is_left:
        droop_at_x = max_droop * t  # deeper on inner (right) side
    else:
        droop_at_x = max_droop * (1.0 - t)  # deeper on inner (left) side
    return py < top_y + droop_at_x


def _happy_mask(py: float, bottom_y: float, amount: float) -> bool:
    if amount < 0.01:
        return False
    cutoff = bottom_y - (bottom_y - SCREEN_H * 0.1) * 0.35 * amount
    return py > cutoff


# ── Eye renderer ─────────────────────────────────────────────────────

def _render_eye(buf: list[tuple[int, int, int]], fs: FaceState,
                is_left: bool) -> None:
    eye = fs.eye_l if is_left else fs.eye_r
    base_cx = LEFT_EYE_CX if is_left else RIGHT_EYE_CX
    base_cy = LEFT_EYE_CY if is_left else RIGHT_EYE_CY

    solid_color = get_emotion_color(fs)
    breath = get_breath_scale(fs)
    open_frac = max(0.0, min(1.0, eye.openness))

    w_scale = eye.width_scale * breath
    h_scale = eye.height_scale * breath

    half_w = (EYE_WIDTH / 2.0) * w_scale
    half_h = (EYE_HEIGHT / 2.0) * open_frac * h_scale
    corner_r = EYE_CORNER_R * min(1.0, open_frac * 2)

    cx = base_cx + eye.gaze_x * GAZE_EYE_SHIFT
    cy = base_cy + eye.gaze_y * GAZE_EYE_SHIFT
    pupil_cx = base_cx + eye.gaze_x * GAZE_PUPIL_SHIFT
    pupil_cy = base_cy + eye.gaze_y * GAZE_PUPIL_SHIFT

    top_y = cy - half_h
    bottom_y = cy + half_h
    br = max(0.0, min(1.0, fs.brightness))

    edge_glow = fs.fx.edge_glow
    edge_falloff = fs.fx.edge_glow_falloff

    # Bounding box for iteration (avoid scanning all 320x240)
    x0 = max(0, int(cx - half_w - 5))
    x1 = min(SCREEN_W, int(cx + half_w + 5))
    y0 = max(0, int(cy - half_h - 5))
    y1 = min(SCREEN_H, int(cy + half_h + 5))

    # Heart eyes override
    if fs.anim.heart:
        heart_size = 22.0 * breath
        for y in range(max(0, int(base_cy - 40)), min(SCREEN_H, int(base_cy + 40))):
            for x in range(max(0, int(base_cx - 40)), min(SCREEN_W, int(base_cx + 40))):
                px = x + 0.5
                py = y + 0.5
                if _in_heart(px, py, base_cx, base_cy, heart_size):
                    r, g, b = solid_color
                    _set_px(buf, x, y, (int(r * br), int(g * br), int(b * br)))
        return

    # X eyes override
    if fs.anim.x_eyes:
        x_size = 28.0
        for y in range(max(0, int(base_cy - 35)), min(SCREEN_H, int(base_cy + 35))):
            for x in range(max(0, int(base_cx - 35)), min(SCREEN_W, int(base_cx + 35))):
                px = x + 0.5
                py = y + 0.5
                if _in_x_shape(px, py, base_cx, base_cy, x_size):
                    r, g, b = solid_color
                    _set_px(buf, x, y, (int(r * br), int(g * br), int(b * br)))
        return

    for y in range(y0, y1):
        for x in range(x0, x1):
            px = x + 0.5
            py = y + 0.5

            if not _in_rounded_rect(px, py, cx, cy, half_w, half_h, corner_r):
                continue

            # Eyelid masks
            if _angry_mask(px, py, cx, top_y, half_w, fs.eyelids.angry, is_left):
                continue
            if _tired_mask(px, py, cx, top_y, half_w, fs.eyelids.tired):
                continue
            if _happy_mask(py, bottom_y, fs.eyelids.happy):
                continue

            if fs.solid_eye:
                r, g, b = solid_color
            elif _in_circle(px, py, pupil_cx, pupil_cy, PUPIL_R * open_frac):
                r, g, b = (10, 20, 50)
            else:
                r, g, b = (255, 255, 255)

            # Edge glow dimming
            if edge_glow:
                dist = _dist_to_edge(px, py, cx, cy, half_w, half_h)
                max_dist = min(half_w, half_h)
                if max_dist > 0:
                    glow = 1.0 - edge_falloff * (1.0 - min(dist / max_dist, 1.0))
                    r = int(r * glow)
                    g = int(g * glow)
                    b = int(b * glow)

            _set_px(buf, x, y, (int(r * br), int(g * br), int(b * br)))


# ── Mouth renderer ───────────────────────────────────────────────────

def _render_mouth(buf: list[tuple[int, int, int]], fs: FaceState) -> None:
    if not fs.show_mouth:
        return

    curve = fs.mouth_curve
    openness = fs.mouth_open
    wave = fs.mouth_wave
    offset_x = fs.mouth_offset_x
    width_scale = fs.mouth_width
    br = max(0.0, min(1.0, fs.brightness))
    color = get_emotion_color(fs)

    cx = MOUTH_CX + offset_x * 8.0
    hw = MOUTH_HALF_W * width_scale
    bend = -curve * 30.0

    thick = MOUTH_THICKNESS

    num_points = int(hw * 2)
    if num_points < 2:
        return

    now = time.monotonic()

    for i in range(num_points):
        t = i / (num_points - 1)
        x_off = -hw + 2.0 * hw * t

        parabola = 1.0 - 4.0 * (t - 0.5) * (t - 0.5)
        y_off = bend * parabola

        if wave > 0.01:
            y_off += wave * 5.0 * math.sin(t * 12.0 + now * 8.0)

        px = int(cx + x_off)
        py = int(MOUTH_CY + y_off)

        # Draw thick dot at each curve point
        th = int(thick)
        for dy in range(-th // 2, th // 2 + 1):
            for dx in range(-th // 2, th // 2 + 1):
                r = int(color[0] * br)
                g = int(color[1] * br)
                b = int(color[2] * br)
                _set_px(buf, px + dx, py + dy, (r, g, b))

        # Open mouth fill (below curve)
        if openness > 0.05:
            fill_depth = int(openness * 20.0 * parabola)
            for fy in range(1, max(1, fill_depth)):
                fade = 1.0 - fy / max(fill_depth, 1)
                r = int(color[0] * 0.3 * br * fade)
                g = int(color[1] * 0.3 * br * fade)
                b = int(color[2] * 0.3 * br * fade)
                for dx in range(-th // 2, th // 2 + 1):
                    _set_px(buf, px + dx, py + fy, (r, g, b))


# ── Sparkle overlay ─────────────────────────────────────────────────

def _apply_sparkle(buf: list[tuple[int, int, int]], fs: FaceState) -> None:
    if not fs.fx.sparkle:
        return
    for sx, sy, life in fs.fx.sparkle_pixels:
        if 0 <= sx < SCREEN_W and 0 <= sy < SCREEN_H:
            existing = buf[_idx(sx, sy)]
            if existing != BG_COLOR:
                intensity = min(1.0, life / 6.0)
                r = min(255, int(existing[0] + 80 * intensity))
                g = min(255, int(existing[1] + 80 * intensity))
                b = min(255, int(existing[2] + 80 * intensity))
                buf[_idx(sx, sy)] = (r, g, b)


# ── Fire particles ──────────────────────────────────────────────────

def _apply_fire(buf: list[tuple[int, int, int]], fs: FaceState) -> None:
    if not fs.anim.rage:
        return
    for fx, fy, life, heat in fs.fx.fire_pixels:
        ix = int(fx)
        iy = int(fy)
        if 0 <= ix < SCREEN_W and 0 <= iy < SCREEN_H:
            if heat > 0.85:
                r, g, b = 255, 220, 120
            elif heat > 0.65:
                r, g, b = 255, 140, 20
            elif heat > 0.4:
                r, g, b = 220, 50, 0
            else:
                r, g, b = 130, 20, 0
            fade = min(1.0, life / 5.0)
            # Draw a 3x3 blob for visibility at this resolution
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    _blend_max(buf, ix + dx, iy + dy, (
                        int(r * fade),
                        int(g * fade),
                        int(b * fade),
                    ))


# ── Afterglow ────────────────────────────────────────────────────────

def _apply_afterglow(buf: list[tuple[int, int, int]], fs: FaceState) -> None:
    if not fs.fx.afterglow or fs.fx.afterglow_buf is None:
        return
    prev = fs.fx.afterglow_buf
    decay = 0.4
    for i in range(SCREEN_W * SCREEN_H):
        cr, cg, cb = buf[i]
        pr, pg, pb = prev[i]
        if cr == 0 and cg == 0 and cb == 0 and (pr > 0 or pg > 0 or pb > 0):
            buf[i] = (int(pr * decay), int(pg * decay), int(pb * decay))


# ── System mode renderers ───────────────────────────────────────────

_CX = SCREEN_W / 2.0
_CY = SCREEN_H / 2.0


def _render_system_booting(buf: list[tuple[int, int, int]],
                           fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    for wave in range(3):
        wave_start = wave * 0.4
        wave_elapsed = elapsed - wave_start
        if wave_elapsed < 0 or wave_elapsed > 1.5:
            continue
        radius = (wave_elapsed / 1.5) * max(SCREEN_W, SCREEN_H) * 0.5
        thickness = 8.0
        alpha = max(0.0, 1.0 - wave_elapsed / 1.5)

        for y in range(SCREEN_H):
            for x in range(SCREEN_W):
                dx = (x + 0.5) - _CX
                dy = (y + 0.5) - _CY
                dist = math.sqrt(dx * dx + dy * dy)
                if abs(dist - radius) < thickness:
                    intensity = alpha * (1.0 - abs(dist - radius) / thickness)
                    r = int(30 * intensity * br)
                    g = int(140 * intensity * br)
                    b = int(255 * intensity * br)
                    old = buf[_idx(x, y)]
                    buf[_idx(x, y)] = (
                        min(255, old[0] + r),
                        min(255, old[1] + g),
                        min(255, old[2] + b),
                    )

    if elapsed > 2.4:
        flash_t = min(1.0, (elapsed - 2.4) / 0.3)
        flash_alpha = 1.0 - flash_t
        r = int(30 * flash_alpha * br)
        g = int(120 * flash_alpha * br)
        b = int(255 * flash_alpha * br)
        for i in range(SCREEN_W * SCREEN_H):
            old = buf[i]
            buf[i] = (min(255, old[0] + r), min(255, old[1] + g), min(255, old[2] + b))


def _render_system_error(buf: list[tuple[int, int, int]],
                         fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    flash = math.sin(elapsed * 4.0 * math.pi) > -0.3
    if not flash:
        return

    # Triangle centered on screen
    ax, ay = _CX, _CY - 60
    bx, by = _CX - 55, _CY + 50
    cx, cy = _CX + 55, _CY + 50

    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            px = x + 0.5
            py = y + 0.5
            denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(denom) < 0.001:
                continue
            u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
            v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
            w = 1.0 - u - v
            if u >= 0 and v >= 0 and w >= 0:
                r, g, b = 255, 180, 0
                # Exclamation mark
                if abs(px - _CX) < 5:
                    if _CY - 30 <= py <= _CY + 10 or _CY + 20 <= py <= _CY + 30:
                        r, g, b = 40, 10, 0
                buf[_idx(x, y)] = (int(r * br), int(g * br), int(b * br))


def _render_system_updating(buf: list[tuple[int, int, int]],
                            fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    radius = 40.0
    thickness = 8.0
    arc_len = math.pi * 0.7
    angle_offset = elapsed * 4.0 * math.pi

    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            dx = (x + 0.5) - _CX
            dy = (y + 0.5) - _CY
            dist = math.sqrt(dx * dx + dy * dy)
            if abs(dist - radius) > thickness:
                continue
            angle = (math.atan2(dy, dx) - angle_offset) % (2.0 * math.pi)
            if angle < arc_len:
                t = angle / arc_len
                intensity = 1.0 - t * 0.6
                buf[_idx(x, y)] = (
                    int(60 * intensity * br),
                    int(160 * intensity * br),
                    int(255 * intensity * br),
                )


def _render_system_shutdown(buf: list[tuple[int, int, int]],
                            fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    if elapsed > 2.0:
        return

    if elapsed < 1.5:
        t = elapsed / 1.5
        radius = 80.0 * (1.0 - t * t)
        alpha = 1.0
    else:
        t = (elapsed - 1.5) / 0.5
        radius = 5.0
        alpha = 1.0 - t

    color = (30, 120, 255)
    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            dx = (x + 0.5) - _CX
            dy = (y + 0.5) - _CY
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= radius:
                edge = max(0.0, 1.0 - max(0.0, dist - radius + 3.0) / 3.0)
                buf[_idx(x, y)] = (
                    int(color[0] * alpha * edge * br),
                    int(color[1] * alpha * edge * br),
                    int(color[2] * alpha * edge * br),
                )


def _render_system_low_battery(buf: list[tuple[int, int, int]],
                               fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))
    level = max(0.0, min(1.0, fs.system.param))

    # Battery body scaled to landscape
    body_l, body_r = 80, 230
    body_t, body_b = 80, 160
    tip_l, tip_r = 230, 245
    tip_t, tip_b = 100, 140

    if level > 0.4:
        fill_color = (40, 200, 40)
    elif level > 0.15:
        fill_color = (255, 180, 0)
    else:
        fill_color = (180, 0, 0)

    outline_color = (120, 120, 130)
    fill_right = body_l + 5 + int(level * (body_r - body_l - 10))

    critical = level <= 0.15
    bang_visible = critical and ((elapsed * 2.0) % 1.0 < 0.6)
    bang_color = (255, 40, 20)

    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            if tip_t <= y <= tip_b and tip_l <= x <= tip_r:
                _set_px(buf, x, y, tuple(int(c * br) for c in outline_color))
                continue

            if body_l <= x <= body_r and body_t <= y <= body_b:
                is_outline = (x == body_l or x == body_r or
                              y == body_t or y == body_b)
                if is_outline:
                    _set_px(buf, x, y, tuple(int(c * br) for c in outline_color))
                elif body_l < x < body_r and body_t < y < body_b:
                    if bang_visible and abs(x - _CX) < 5:
                        if 90 <= y <= 130 or 140 <= y <= 150:
                            _set_px(buf, x, y, tuple(int(c * br) for c in bang_color))
                            continue
                    if x < fill_right:
                        _set_px(buf, x, y, tuple(int(c * br) for c in fill_color))


def _render_system_mode(buf: list[tuple[int, int, int]],
                        fs: FaceState) -> bool:
    mode = fs.system.mode
    if mode == SystemMode.NONE:
        return False
    elif mode == SystemMode.BOOTING:
        _render_system_booting(buf, fs)
    elif mode == SystemMode.ERROR:
        _render_system_error(buf, fs)
    elif mode == SystemMode.LOW_BATTERY:
        _render_system_low_battery(buf, fs)
    elif mode == SystemMode.UPDATING:
        _render_system_updating(buf, fs)
    elif mode == SystemMode.SHUTTING_DOWN:
        _render_system_shutdown(buf, fs)
    return True


# ── Main render function ─────────────────────────────────────────────

def render_face(fs: FaceState) -> list[tuple[int, int, int]]:
    """Render face onto a flat 320x240 pixel buffer. Returns row-major list."""
    buf: list[tuple[int, int, int]] = [BG_COLOR] * (SCREEN_W * SCREEN_H)

    if _render_system_mode(buf, fs):
        return buf

    _render_eye(buf, fs, is_left=True)
    _render_eye(buf, fs, is_left=False)
    _render_mouth(buf, fs)

    _apply_afterglow(buf, fs)
    _apply_sparkle(buf, fs)
    _apply_fire(buf, fs)

    if fs.fx.afterglow:
        fs.fx.afterglow_buf = buf[:]

    return buf
