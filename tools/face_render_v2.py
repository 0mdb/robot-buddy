"""Face renderer v2 (Final).

Updates:
- Fixed pupil clipping (pupil now stays inside eye).
- Fixed mouth curvature (Happy = Smile).
- Added Heart and X SDF shapes for gestures.
- Fixed System Screen crash (color clamping).
"""

from __future__ import annotations
import math
import random
import time
from face_state_v2 import (
    FaceState,
    SystemMode,
    SCREEN_W,
    SCREEN_H,
    EYE_WIDTH,
    EYE_HEIGHT,
    EYE_CORNER_R,
    PUPIL_R,
    LEFT_EYE_CX,
    LEFT_EYE_CY,
    RIGHT_EYE_CX,
    RIGHT_EYE_CY,
    GAZE_EYE_SHIFT,
    GAZE_PUPIL_SHIFT,
    MOUTH_CX,
    MOUTH_CY,
    MOUTH_HALF_W,
    MOUTH_THICKNESS,
    get_breath_scale,
    get_emotion_color,
)

BG_COLOR = (10, 10, 14)


def _clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


def _clamp_color(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(c[0]))),
        max(0, min(255, int(c[1]))),
        max(0, min(255, int(c[2]))),
    )


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    x = _clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _mix_color(c1: tuple, c2: tuple, t: float) -> tuple[int, int, int]:
    t = _clamp(t, 0.0, 1.0)
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _set_px_blend(buf: list, idx: int, color: tuple, alpha: float) -> None:
    if alpha <= 0.0:
        return
    color = _clamp_color(color)
    bg = buf[idx]
    if alpha >= 1.0:
        buf[idx] = color
    else:
        buf[idx] = _mix_color(bg, color, alpha)


# ── SDF Shapes ───────────────────────────────────────────────────────


def _sd_rounded_box(
    px: float, py: float, cx: float, cy: float, hw: float, hh: float, r: float
) -> float:
    dx = abs(px - cx) - hw + r
    dy = abs(py - cy) - hh + r
    return min(max(dx, dy), 0.0) + math.sqrt(max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2) - r


def _sd_circle(px: float, py: float, cx: float, cy: float, r: float) -> float:
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2) - r


def _sd_equilateral_triangle(
    px: float, py: float, cx: float, cy: float, r: float
) -> float:
    px -= cx
    py -= cy
    k = math.sqrt(3.0)
    px = abs(px) - r
    py = py + r / k
    if px + k * py > 0.0:
        px, py = (px - k * py) / 2.0, (-k * px - py) / 2.0
    px -= _clamp(px, -2.0 * r, 0.0)
    return -math.sqrt(px * px + py * py) * (1.0 if py < 0.0 else -1.0)


def _sd_heart(px: float, py: float, cx: float, cy: float, size: float) -> float:
    """Heart SDF: two circle lobes + V-taper to point. Negative = inside."""
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


def _sd_cross(
    px: float, py: float, cx: float, cy: float, size: float, thick: float
) -> float:
    # Union of two rotated boxes
    # Rotate 45 deg roughly: union of two rects:
    # Rect 1: /  Rect 2: \
    # Rotate coords
    rx = (px - cx) * 0.707 - (py - cy) * 0.707
    ry = (px - cx) * 0.707 + (py - cy) * 0.707

    d1 = _sd_rounded_box(rx, ry, 0, 0, thick, size, 1.0)
    d2 = _sd_rounded_box(rx, ry, 0, 0, size, thick, 1.0)
    return min(d1, d2)


# ── System FX ────────────────────────────────────────────────────────


def _apply_scanlines(buf: list) -> None:
    for y in range(0, SCREEN_H, 2):
        row = y * SCREEN_W
        for x in range(SCREEN_W):
            c = buf[row + x]
            buf[row + x] = (int(c[0] * 0.8), int(c[1] * 0.8), int(c[2] * 0.8))


def _draw_vignette(buf: list) -> None:
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    max_dist = math.sqrt(cx * cx + cy * cy)
    for y in range(SCREEN_H):
        row = y * SCREEN_W
        for x in range(SCREEN_W):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            vignette = 1.0 - _smoothstep(max_dist * 0.5, max_dist, dist)
            old = buf[row + x]
            buf[row + x] = (
                int(old[0] * vignette),
                int(old[1] * vignette),
                int(old[2] * vignette),
            )


# ── Renderers ────────────────────────────────────────────────────────


def _render_booting(buf: list, fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    grid_col = (0, 50, 100)
    for y in range(SCREEN_H):
        row = y * SCREEN_W
        for x in range(SCREEN_W):
            if x % 40 == 0 or y % 40 == 0:
                _set_px_blend(buf, row + x, grid_col, 0.2)
    angle = (elapsed * 3.0) % 6.28
    radar_r = 90.0
    for y in range(int(cy - radar_r), int(cy + radar_r)):
        row = y * SCREEN_W
        for x in range(int(cx - radar_r), int(cx + radar_r)):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            ring_sdf = abs(dist - radar_r)
            alpha_ring = 1.0 - _smoothstep(1.0, 3.0, ring_sdf)
            if alpha_ring > 0:
                _set_px_blend(buf, row + x, (0, 200, 255), alpha_ring)
            if dist < radar_r:
                pixel_angle = math.atan2(dy, dx)
                diff = (pixel_angle - angle + 3.14159) % 6.28 - 3.14159
                if diff < 0:
                    diff += 6.28
                if 0 < diff < 1.0:
                    intensity = (1.0 - diff) * 0.6
                    if (x * y) % 43 == 0 and random.random() < 0.1:
                        intensity = 1.0
                    _set_px_blend(
                        buf,
                        row + x,
                        (0, int(255 * intensity), int(200 * intensity)),
                        intensity,
                    )
    bar_w, bar_h, bar_y = 200, 10, cy + 60
    prog = min(1.0, elapsed / 3.0)
    for y in range(int(bar_y), int(bar_y + bar_h)):
        row = y * SCREEN_W
        for x in range(int(cx - bar_w / 2), int(cx + bar_w / 2)):
            if (
                x == int(cx - bar_w / 2)
                or x == int(cx + bar_w / 2 - 1)
                or y == int(bar_y)
                or y == int(bar_y + bar_h - 1)
            ):
                buf[row + x] = (0, 150, 255)
            elif x < (cx - bar_w / 2) + (bar_w * prog):
                buf[row + x] = (0, 200, 255)


def _render_error(buf: list, fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    pulse = (math.sin(elapsed * 8.0) + 1.0) * 0.5
    bg_color = (int(40 * pulse), 0, 0)
    tri_r = 70.0
    for y in range(SCREEN_H):
        row = y * SCREEN_W
        off_x = random.randint(-10, 10) if random.random() < 0.05 else 0
        for x in range(SCREEN_W):
            buf[row + x] = bg_color

            def get_alpha(sx, sy):
                d_tri = _sd_equilateral_triangle(sx, sy, cx, cy, tri_r)
                d_in = _sd_equilateral_triangle(sx, sy, cx, cy + 5, tri_r - 15)
                d_mark = min(
                    _sd_rounded_box(sx, sy, cx, cy - 10, 6, 20, 2),
                    _sd_circle(sx, sy, cx, cy + 25, 6),
                )
                return 1.0 - _smoothstep(
                    0.0, 2.0, min(d_tri, -d_in)
                ), 1.0 - _smoothstep(0.0, 2.0, d_mark)

            ay_r, am_r = get_alpha(x + off_x - 4, y)
            ay_c, am_c = get_alpha(x + off_x, y)
            ay_b, am_b = get_alpha(x + off_x + 4, y)
            r = 255 if ay_r > 0 else bg_color[0]
            if am_r > 0:
                r = 10
            g = 200 if ay_c > 0 else bg_color[1]
            if am_c > 0:
                g = 0
            b = 0 if ay_b > 0 else bg_color[2]
            if am_b > 0:
                b = 0
            buf[row + x] = _clamp_color((r, g, b))


def _render_battery(buf: list, fs: FaceState) -> None:
    lvl = fs.system.param
    el = time.monotonic() - fs.system.timer
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    col = (0, 220, 100) if lvl > 0.5 else (220, 180, 0) if lvl > 0.2 else (220, 40, 40)
    bw, bh = 80, 40
    for y in range(int(cy - 60), int(cy + 60)):
        row = y * SCREEN_W
        for x in range(int(cx - 100), int(cx + 100)):
            px, py = x + 0.5, y + 0.5
            d_out = _sd_rounded_box(px, py, cx, cy, bw, bh, 6)
            d_in = _sd_rounded_box(px, py, cx, cy, bw - 4, bh - 4, 4)
            d_tip = _sd_rounded_box(px, py, cx + bw + 8, cy, 6, 15, 2)
            d_shell = min(max(d_out, -d_in), d_tip)
            alpha_shell = 1.0 - _smoothstep(-1.0, 1.0, d_shell)
            if alpha_shell > 0:
                _set_px_blend(buf, row + x, (200, 200, 210), alpha_shell)
            fill_max = (cx - bw + 4) + (2 * (bw - 4) * lvl)
            if d_in < 0:
                wave = math.sin(x * 0.1 + el * 5.0) * 3.0
                if px < fill_max + wave:
                    gloss = (py - (cy - bh)) / (2 * bh)
                    r, g, b = col
                    r, g, b = (
                        int(r * (0.8 + 0.4 * gloss)),
                        int(g * (0.8 + 0.4 * gloss)),
                        int(b * (0.8 + 0.4 * gloss)),
                    )
                    if (
                        int(x / 20) * int(y / 20) + int(el * 2)
                    ) % 13 == 0 and random.random() < 0.2:
                        r, g, b = 255, 255, 255
                    _set_px_blend(buf, row + x, (r, g, b), 1.0)
            if lvl < 0.2 and (int(el * 4) % 2 == 0):
                if (
                    abs(px - cx) < 10
                    and abs(py - cy) < 20
                    and abs((px - cx) + (py - cy) * 0.4) < 4
                ):
                    _set_px_blend(buf, row + x, (255, 255, 255), 1.0)


def _render_updating(buf: list, fs: FaceState) -> None:
    el = time.monotonic() - fs.system.timer
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    for y in range(int(cy - 60), int(cy + 60)):
        row = y * SCREEN_W
        for x in range(int(cx - 60), int(cx + 60)):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            angle = math.atan2(dy, dx)
            a1 = (angle + el * 2.0) % 6.28
            if abs(dist - 50.0) < 3.0 and 0 < a1 < 4.0:
                _set_px_blend(buf, row + x, (0, 255, 100), 1.0)
            a2 = (angle - el * 5.0) % 1.5
            if abs(dist - 35.0) < 4.0 and a2 < 1.0:
                _set_px_blend(buf, row + x, (0, 200, 255), 1.0)
            alpha_dot = 1.0 - _smoothstep(
                -1.0,
                1.0,
                _sd_circle(x + 0.5, y + 0.5, cx, cy, 8.0 + math.sin(el * 10) * 2),
            )
            if alpha_dot > 0:
                _set_px_blend(buf, row + x, (255, 255, 255), alpha_dot)


def _render_shutdown(buf: list, fs: FaceState) -> None:
    el = time.monotonic() - fs.system.timer
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    if el < 0.4:
        vs, hs, br = 1.0 - (el / 0.4), 1.0, 1.0 + el
    elif el < 0.6:
        vs, hs, br = 0.005, 1.0 - ((el - 0.4) / 0.2), 2.0
    elif el < 0.8:
        vs, hs, br = 0.002, 0.002, 1.0 - ((el - 0.6) / 0.2)
    else:
        return
    bw, bh = int(SCREEN_W * hs), int(SCREEN_H * vs)
    if bw < 1:
        bw = 1
    if bh < 1:
        bh = 1
    col = (int(255 * min(1.0, br)), int(255 * min(1.0, br)), 255)
    for y in range(max(0, int(cy - bh / 2)), min(SCREEN_H, int(cy + bh / 2))):
        row = y * SCREEN_W
        for x in range(max(0, int(cx - bw / 2)), min(SCREEN_W, int(cx + bw / 2))):
            buf[row + x] = col


def _render_eye(buf: list, fs: FaceState, is_left: bool) -> None:
    eye = fs.eye_l if is_left else fs.eye_r
    cx_base = LEFT_EYE_CX if is_left else RIGHT_EYE_CX
    cy_base = LEFT_EYE_CY if is_left else RIGHT_EYE_CY
    breath = get_breath_scale(fs)
    w = (EYE_WIDTH / 2.0) * eye.width_scale * breath
    h = (EYE_HEIGHT / 2.0) * eye.height_scale * breath

    # CLAMP: Ensure the pupil cannot physically leave the eye
    # Max shift allowed = (Width of eye) - (Radius of pupil) - (Padding)
    max_offset_x = w - PUPIL_R - 5.0
    max_offset_y = h - PUPIL_R - 5.0

    # Calculate clamped offsets
    shift_x = _clamp(eye.gaze_x * GAZE_PUPIL_SHIFT, -max_offset_x, max_offset_x)
    shift_y = _clamp(eye.gaze_y * GAZE_PUPIL_SHIFT, -max_offset_y, max_offset_y)

    cx = cx_base + eye.gaze_x * GAZE_EYE_SHIFT
    cy = cy_base + eye.gaze_y * GAZE_EYE_SHIFT

    pupil_cx = cx_base + shift_x
    pupil_cy = cy_base + shift_y

    lid_top = fs.eyelids.top_l if is_left else fs.eyelids.top_r
    lid_bot = fs.eyelids.bottom_l if is_left else fs.eyelids.bottom_r
    lid_slope = fs.eyelids.slope

    base_color = get_emotion_color(fs)
    pupil_color = (10, 15, 30)

    x0 = max(0, int(cx - w - 10))
    x1 = min(SCREEN_W, int(cx + w + 10))
    y0 = max(0, int(cy - h - 10))
    y1 = min(SCREEN_H, int(cy + h + 10))

    # Solid-mode heart override: replace entire eye with heart shape
    if fs.solid_eye and fs.anim.heart:
        heart_size = min(w, h) * 0.7
        for y in range(y0, y1):
            row_idx = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5, y + 0.5
                val = _sd_heart(px, py, cx_base, cy_base, heart_size)
                alpha = 1.0 - _smoothstep(-0.5, 0.5, val)
                if alpha > 0.01:
                    br = fs.brightness
                    _set_px_blend(
                        buf,
                        row_idx + x,
                        (
                            int(base_color[0] * br),
                            int(base_color[1] * br),
                            int(base_color[2] * br),
                        ),
                        alpha,
                    )
        return

    # Solid-mode X-eyes override: replace entire eye with X shape
    if fs.solid_eye and fs.anim.x_eyes:
        x_size = min(w, h) * 0.8
        for y in range(y0, y1):
            row_idx = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5, y + 0.5
                dist_x = _sd_cross(px, py, cx_base, cy_base, x_size, 6.0)
                alpha = 1.0 - _smoothstep(-0.5, 0.5, dist_x)
                if alpha > 0.01:
                    br = fs.brightness
                    _set_px_blend(
                        buf,
                        row_idx + x,
                        (
                            int(base_color[0] * br),
                            int(base_color[1] * br),
                            int(base_color[2] * br),
                        ),
                        alpha,
                    )
        return

    for y in range(y0, y1):
        row_idx = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5

            dist_box = _sd_rounded_box(px, py, cx, cy, w, h, EYE_CORNER_R)
            alpha_shape = 1.0 - _smoothstep(-0.5, 0.5, dist_box)
            if alpha_shape <= 0.01:
                continue

            norm_x = (px - cx) / w
            if not is_left:
                norm_x = -norm_x

            slope_off = lid_slope * 20.0 * norm_x
            lid_limit_t = (cy - h) + (h * 2.0 * lid_top) + slope_off
            lid_limit_b = (cy + h) - (h * 2.0 * lid_bot)

            alpha_lid = _smoothstep(-1.0, 1.0, py - lid_limit_t)
            alpha_lid_b = _smoothstep(-1.0, 1.0, lid_limit_b - py)

            final_alpha = alpha_shape * alpha_lid * alpha_lid_b
            if final_alpha <= 0.01:
                continue

            if fs.fx.edge_glow:
                dist_center = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
                grad = _clamp(
                    1.0 - fs.fx.edge_glow_falloff * (dist_center / (max(w, h) * 1.5)),
                    0.4,
                    1.0,
                )
            else:
                grad = 1.0

            r, g, b = (
                int(base_color[0] * grad),
                int(base_color[1] * grad),
                int(base_color[2] * grad),
            )

            # Fade pupil & gloss out as eyelids close (gone by 50% closure)
            lid_vis = 1.0 - _smoothstep(0.25, 0.55, lid_top)

            if not fs.solid_eye and lid_vis > 0.01:
                # Select SDF Shape based on Anim
                if fs.anim.heart:
                    # Heart SDF (implicit)
                    val = _sd_heart(px, py, pupil_cx, pupil_cy, PUPIL_R * 1.5)
                    alpha_pupil = 1.0 - _smoothstep(-0.5, 0.5, val)
                elif fs.anim.x_eyes:
                    # Cross SDF
                    dist_x = _sd_cross(px, py, pupil_cx, pupil_cy, PUPIL_R, 6.0)
                    alpha_pupil = 1.0 - _smoothstep(-0.5, 0.5, dist_x)
                else:
                    # Standard Circle
                    dist_pupil = _sd_circle(px, py, pupil_cx, pupil_cy, PUPIL_R)
                    alpha_pupil = 1.0 - _smoothstep(-0.5, 0.5, dist_pupil)

                alpha_pupil *= final_alpha * lid_vis
                if alpha_pupil > 0:
                    r = int(r * (1.0 - alpha_pupil) + pupil_color[0] * alpha_pupil)
                    g = int(g * (1.0 - alpha_pupil) + pupil_color[1] * alpha_pupil)
                    b = int(b * (1.0 - alpha_pupil) + pupil_color[2] * alpha_pupil)

            br = fs.brightness
            _set_px_blend(
                buf, row_idx + x, (int(r * br), int(g * br), int(b * br)), final_alpha
            )


def _render_mouth(buf: list, fs: FaceState) -> None:
    if not fs.show_mouth:
        return
    cx, cy = MOUTH_CX + fs.mouth_offset_x * 10.0, MOUTH_CY
    w, thick = MOUTH_HALF_W * fs.mouth_width, MOUTH_THICKNESS
    curve, openness = fs.mouth_curve * 40.0, fs.mouth_open * 40.0
    col = get_emotion_color(fs)
    br = fs.brightness
    draw_col = (int(col[0] * br), int(col[1] * br), int(col[2] * br))

    x0, x1 = int(cx - w - thick), int(cx + w + thick)
    y0, y1 = (
        int(cy - abs(curve) - openness - thick),
        int(cy + abs(curve) + openness + thick),
    )

    for y in range(max(0, y0), min(SCREEN_H, y1)):
        row_idx = y * SCREEN_W
        for x in range(max(0, x0), min(SCREEN_W, x1)):
            px, py = x + 0.5, y + 0.5
            nx = (px - cx) / w
            if abs(nx) > 1.0:
                continue
            shape = 1.0 - nx * nx
            # FIXED: Positive curve = smile (U shape), so Ends must be higher (lower Y) than Center.
            # shape=1 at center. curve_y must increase Y at center.
            curve_y = curve * shape
            upper_y = cy + curve_y - openness * shape
            lower_y = cy + curve_y + openness * shape
            dist = (
                0.0
                if (openness > 1.0 and upper_y < py < lower_y)
                else min(abs(py - upper_y), abs(py - lower_y))
            )
            alpha = 1.0 - _smoothstep(thick / 2.0 - 1.0, thick / 2.0 + 1.0, dist)
            if alpha > 0:
                _set_px_blend(buf, row_idx + x, draw_col, alpha)


def _apply_fire(buf: list, fs: FaceState) -> None:
    """Draw fire particles as 3x3 blobs during rage."""
    for fx, fy, life, heat in fs.fx.fire_pixels:
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


def _apply_afterglow(buf: list, fs: FaceState) -> None:
    """Blend previous frame through for a soft fade-out on blink."""
    if fs.fx.afterglow_buf is None:
        return
    prev = fs.fx.afterglow_buf
    decay = 0.4
    for i in range(SCREEN_W * SCREEN_H):
        cr, cg, cb = buf[i]
        pr, pg, pb = prev[i]
        if cr <= BG_COLOR[0] and cg <= BG_COLOR[1] and cb <= BG_COLOR[2]:
            if pr > BG_COLOR[0] or pg > BG_COLOR[1] or pb > BG_COLOR[2]:
                buf[i] = (
                    max(BG_COLOR[0], int(pr * decay)),
                    max(BG_COLOR[1], int(pg * decay)),
                    max(BG_COLOR[2], int(pb * decay)),
                )


def render_face(fs: FaceState) -> list[tuple[int, int, int]]:
    buf = [BG_COLOR] * (SCREEN_W * SCREEN_H)
    mode = fs.system.mode
    if mode != SystemMode.NONE:
        if mode == SystemMode.BOOTING:
            _render_booting(buf, fs)
        elif mode == SystemMode.ERROR:
            _render_error(buf, fs)
        elif mode == SystemMode.LOW_BATTERY:
            _render_battery(buf, fs)
        elif mode == SystemMode.UPDATING:
            _render_updating(buf, fs)
        elif mode == SystemMode.SHUTTING_DOWN:
            _render_shutdown(buf, fs)
        _apply_scanlines(buf)
        _draw_vignette(buf)
        return buf

    _render_eye(buf, fs, True)
    _render_eye(buf, fs, False)
    _render_mouth(buf, fs)

    # Post-processing effects
    if fs.fx.afterglow:
        _apply_afterglow(buf, fs)
    if fs.anim.rage:
        _apply_fire(buf, fs)
    for sx, sy, life in fs.fx.sparkle_pixels:
        if 0 <= sx < SCREEN_W and 0 <= sy < SCREEN_H:
            idx = sy * SCREEN_W + sx
            _set_px_blend(buf, idx, (255, 255, 255), min(1.0, life / 5.0))

    # Store frame for afterglow
    if fs.fx.afterglow:
        fs.fx.afterglow_buf = buf[:]

    return buf
