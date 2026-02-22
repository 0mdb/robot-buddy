"""Face renderer — eye, mouth, system overlays.

Renders into a list[tuple[int,int,int]] pixel buffer (320x240).
Port from face_render_v2.py with all constants from constants.py.
"""

from __future__ import annotations

import math
import random
import time

from tools.face_sim_v3.render.effects import (
    apply_afterglow,
    clamp_color,
    render_fire,
    render_sparkles,
    set_px_blend,
)
from tools.face_sim_v3.render.sdf import (
    sd_circle,
    sd_cross,
    sd_heart,
    sd_rounded_box,
    sd_equilateral_triangle,
    smoothstep,
)
from tools.face_sim_v3.state.constants import (
    BG_COLOR,
    EDGE_GLOW_FALLOFF,
    EYE_CORNER_R,
    EYE_HEIGHT,
    EYE_WIDTH,
    GAZE_EYE_SHIFT,
    GAZE_PUPIL_SHIFT,
    LEFT_EYE_CX,
    LEFT_EYE_CY,
    MOUTH_CX,
    MOUTH_CY,
    MOUTH_HALF_W,
    MOUTH_THICKNESS,
    PUPIL_COLOR,
    PUPIL_R,
    RIGHT_EYE_CX,
    RIGHT_EYE_CY,
    SCREEN_H,
    SCREEN_W,
    SystemMode,
)
from tools.face_sim_v3.state.face_state import (
    FaceState,
    face_get_breath_scale,
    face_get_emotion_color,
)


# ── Color/math helpers ───────────────────────────────────────────────


def _clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


# ── System overlay screens ───────────────────────────────────────────


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
            vignette = 1.0 - smoothstep(max_dist * 0.5, max_dist, dist)
            old = buf[row + x]
            buf[row + x] = (
                int(old[0] * vignette),
                int(old[1] * vignette),
                int(old[2] * vignette),
            )


def _render_booting(buf: list, fs: FaceState) -> None:
    elapsed = time.monotonic() - fs.system.timer
    cx, cy = SCREEN_W / 2, SCREEN_H / 2
    grid_col = (0, 50, 100)
    for y in range(SCREEN_H):
        row = y * SCREEN_W
        for x in range(SCREEN_W):
            if x % 40 == 0 or y % 40 == 0:
                set_px_blend(buf, row + x, grid_col, 0.2)
    angle = (elapsed * 3.0) % 6.28
    radar_r = 90.0
    for y in range(int(cy - radar_r), int(cy + radar_r)):
        row = y * SCREEN_W
        for x in range(int(cx - radar_r), int(cx + radar_r)):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            ring_sdf = abs(dist - radar_r)
            alpha_ring = 1.0 - smoothstep(1.0, 3.0, ring_sdf)
            if alpha_ring > 0:
                set_px_blend(buf, row + x, (0, 200, 255), alpha_ring)
            if dist < radar_r:
                pixel_angle = math.atan2(dy, dx)
                diff = (pixel_angle - angle + 3.14159) % 6.28 - 3.14159
                if diff < 0:
                    diff += 6.28
                if 0 < diff < 1.0:
                    intensity = (1.0 - diff) * 0.6
                    if (x * y) % 43 == 0 and random.random() < 0.1:
                        intensity = 1.0
                    set_px_blend(
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
    bg_c = (int(40 * pulse), 0, 0)
    tri_r = 70.0
    for y in range(SCREEN_H):
        row = y * SCREEN_W
        off_x = random.randint(-10, 10) if random.random() < 0.05 else 0
        for x in range(SCREEN_W):
            buf[row + x] = bg_c
            sx = x + off_x
            d_tri = sd_equilateral_triangle(sx, y, cx, cy, tri_r)
            d_in = sd_equilateral_triangle(sx, y, cx, cy + 5, tri_r - 15)
            d_mark = min(
                sd_rounded_box(sx, y, cx, cy - 10, 6, 20, 2),
                sd_circle(sx, y, cx, cy + 25, 6),
            )
            a_tri = 1.0 - smoothstep(0.0, 2.0, min(d_tri, -d_in))
            a_mark = 1.0 - smoothstep(0.0, 2.0, d_mark)

            # Chromatic aberration (split R/G/B channels)
            sx_r = x + off_x - 4
            d_tri_r = sd_equilateral_triangle(sx_r, y, cx, cy, tri_r)
            d_in_r = sd_equilateral_triangle(sx_r, y, cx, cy + 5, tri_r - 15)
            d_mark_r = min(
                sd_rounded_box(sx_r, y, cx, cy - 10, 6, 20, 2),
                sd_circle(sx_r, y, cx, cy + 25, 6),
            )
            ay_r = 1.0 - smoothstep(0.0, 2.0, min(d_tri_r, -d_in_r))
            am_r = 1.0 - smoothstep(0.0, 2.0, d_mark_r)

            sx_b = x + off_x + 4
            d_tri_b = sd_equilateral_triangle(sx_b, y, cx, cy, tri_r)
            d_in_b = sd_equilateral_triangle(sx_b, y, cx, cy + 5, tri_r - 15)
            d_mark_b = min(
                sd_rounded_box(sx_b, y, cx, cy - 10, 6, 20, 2),
                sd_circle(sx_b, y, cx, cy + 25, 6),
            )
            ay_b = 1.0 - smoothstep(0.0, 2.0, min(d_tri_b, -d_in_b))
            am_b = 1.0 - smoothstep(0.0, 2.0, d_mark_b)

            r = 255 if ay_r > 0 else bg_c[0]
            if am_r > 0:
                r = 10
            g = 200 if a_tri > 0 else bg_c[1]
            if a_mark > 0:
                g = 0
            b = 0 if ay_b > 0 else bg_c[2]
            if am_b > 0:
                b = 0
            buf[row + x] = clamp_color((r, g, b))


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
            d_out = sd_rounded_box(px, py, cx, cy, bw, bh, 6)
            d_in = sd_rounded_box(px, py, cx, cy, bw - 4, bh - 4, 4)
            d_tip = sd_rounded_box(px, py, cx + bw + 8, cy, 6, 15, 2)
            d_shell = min(max(d_out, -d_in), d_tip)
            alpha_shell = 1.0 - smoothstep(-1.0, 1.0, d_shell)
            if alpha_shell > 0:
                set_px_blend(buf, row + x, (200, 200, 210), alpha_shell)
            fill_max = (cx - bw + 4) + (2 * (bw - 4) * lvl)
            if d_in < 0:
                wave = math.sin(x * 0.1 + el * 5.0) * 3.0
                if px < fill_max + wave:
                    gloss = (py - (cy - bh)) / (2 * bh)
                    r, g, b = (
                        int(col[0] * (0.8 + 0.4 * gloss)),
                        int(col[1] * (0.8 + 0.4 * gloss)),
                        int(col[2] * (0.8 + 0.4 * gloss)),
                    )
                    if (
                        int(x / 20) * int(y / 20) + int(el * 2)
                    ) % 13 == 0 and random.random() < 0.2:
                        r, g, b = 255, 255, 255
                    set_px_blend(buf, row + x, (r, g, b), 1.0)
            if lvl < 0.2 and (int(el * 4) % 2 == 0):
                if (
                    abs(px - cx) < 10
                    and abs(py - cy) < 20
                    and abs((px - cx) + (py - cy) * 0.4) < 4
                ):
                    set_px_blend(buf, row + x, (255, 255, 255), 1.0)


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
                set_px_blend(buf, row + x, (0, 255, 100), 1.0)
            a2 = (angle - el * 5.0) % 1.5
            if abs(dist - 35.0) < 4.0 and a2 < 1.0:
                set_px_blend(buf, row + x, (0, 200, 255), 1.0)
            alpha_dot = 1.0 - smoothstep(
                -1.0,
                1.0,
                sd_circle(x + 0.5, y + 0.5, cx, cy, 8.0 + math.sin(el * 10) * 2),
            )
            if alpha_dot > 0:
                set_px_blend(buf, row + x, (255, 255, 255), alpha_dot)


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
    bw = max(1, bw)
    bh = max(1, bh)
    col = (int(255 * min(1.0, br)), int(255 * min(1.0, br)), 255)
    for y in range(max(0, int(cy - bh / 2)), min(SCREEN_H, int(cy + bh / 2))):
        row = y * SCREEN_W
        for x in range(max(0, int(cx - bw / 2)), min(SCREEN_W, int(cx + bw / 2))):
            buf[row + x] = col


# ── Eye rendering ────────────────────────────────────────────────────


def _render_eye(buf: list, fs: FaceState, is_left: bool) -> None:
    eye = fs.eye_l if is_left else fs.eye_r
    cx_base = LEFT_EYE_CX if is_left else RIGHT_EYE_CX
    cy_base = LEFT_EYE_CY if is_left else RIGHT_EYE_CY
    breath = face_get_breath_scale(fs)
    w = (EYE_WIDTH / 2.0) * eye.width_scale * breath
    h = (EYE_HEIGHT / 2.0) * eye.height_scale * breath

    # Clamp pupil offset so it stays inside the eye
    max_offset_x = w - PUPIL_R - 5.0
    max_offset_y = h - PUPIL_R - 5.0
    shift_x = _clamp(eye.gaze_x * GAZE_PUPIL_SHIFT, -max_offset_x, max_offset_x)
    shift_y = _clamp(eye.gaze_y * GAZE_PUPIL_SHIFT, -max_offset_y, max_offset_y)

    cx = cx_base + eye.gaze_x * GAZE_EYE_SHIFT
    cy = cy_base + eye.gaze_y * GAZE_EYE_SHIFT
    pupil_cx = cx_base + shift_x
    pupil_cy = cy_base + shift_y

    lid_top = fs.eyelids.top_l if is_left else fs.eyelids.top_r
    lid_bot = fs.eyelids.bottom_l if is_left else fs.eyelids.bottom_r
    lid_slope = fs.eyelids.slope

    base_color = face_get_emotion_color(fs)

    x0 = max(0, int(cx - w - 10))
    x1 = min(SCREEN_W, int(cx + w + 10))
    y0 = max(0, int(cy - h - 10))
    y1 = min(SCREEN_H, int(cy + h + 10))

    # Solid-mode heart override
    if fs.solid_eye and fs.anim.heart:
        heart_size = min(w, h) * 0.7
        for y in range(y0, y1):
            row_idx = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5, y + 0.5
                val = sd_heart(px, py, cx_base, cy_base, heart_size)
                alpha = 1.0 - smoothstep(-0.5, 0.5, val)
                if alpha > 0.01:
                    br = fs.brightness
                    set_px_blend(
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

    # Solid-mode X-eyes override
    if fs.solid_eye and fs.anim.x_eyes:
        x_size = min(w, h) * 0.8
        for y in range(y0, y1):
            row_idx = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5, y + 0.5
                dist_x = sd_cross(px, py, cx_base, cy_base, x_size, 6.0)
                alpha = 1.0 - smoothstep(-0.5, 0.5, dist_x)
                if alpha > 0.01:
                    br = fs.brightness
                    set_px_blend(
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

    # Normal eye rendering
    for y in range(y0, y1):
        row_idx = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5

            dist_box = sd_rounded_box(px, py, cx, cy, w, h, EYE_CORNER_R)
            alpha_shape = 1.0 - smoothstep(-0.5, 0.5, dist_box)
            if alpha_shape <= 0.01:
                continue

            norm_x = (px - cx) / w
            if not is_left:
                norm_x = -norm_x

            slope_off = lid_slope * 20.0 * norm_x
            lid_limit_t = (cy - h) + (h * 2.0 * lid_top) + slope_off
            lid_limit_b = (cy + h) - (h * 2.0 * lid_bot)

            alpha_lid = smoothstep(-1.0, 1.0, py - lid_limit_t)
            alpha_lid_b = smoothstep(-1.0, 1.0, lid_limit_b - py)

            final_alpha = alpha_shape * alpha_lid * alpha_lid_b
            if final_alpha <= 0.01:
                continue

            if fs.fx.edge_glow:
                dist_center = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
                grad = _clamp(
                    1.0 - EDGE_GLOW_FALLOFF * (dist_center / (max(w, h) * 1.5)),
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

            # Fade pupil & gloss as eyelids close (gone by 50% closure)
            lid_vis = 1.0 - smoothstep(0.25, 0.55, lid_top)

            if not fs.solid_eye and lid_vis > 0.01:
                if fs.anim.heart:
                    val = sd_heart(px, py, pupil_cx, pupil_cy, PUPIL_R * 1.5)
                    alpha_pupil = 1.0 - smoothstep(-0.5, 0.5, val)
                elif fs.anim.x_eyes:
                    dist_x = sd_cross(px, py, pupil_cx, pupil_cy, PUPIL_R, 6.0)
                    alpha_pupil = 1.0 - smoothstep(-0.5, 0.5, dist_x)
                else:
                    dist_pupil = sd_circle(px, py, pupil_cx, pupil_cy, PUPIL_R)
                    alpha_pupil = 1.0 - smoothstep(-0.5, 0.5, dist_pupil)

                alpha_pupil *= final_alpha * lid_vis
                if alpha_pupil > 0:
                    r = int(r * (1.0 - alpha_pupil) + PUPIL_COLOR[0] * alpha_pupil)
                    g = int(g * (1.0 - alpha_pupil) + PUPIL_COLOR[1] * alpha_pupil)
                    b = int(b * (1.0 - alpha_pupil) + PUPIL_COLOR[2] * alpha_pupil)

            br = fs.brightness
            set_px_blend(
                buf, row_idx + x, (int(r * br), int(g * br), int(b * br)), final_alpha
            )


# ── Mouth rendering ──────────────────────────────────────────────────


def _render_mouth(buf: list, fs: FaceState) -> None:
    if not fs.show_mouth:
        return
    cx, cy = MOUTH_CX + fs.mouth_offset_x * 10.0, MOUTH_CY
    w, thick = MOUTH_HALF_W * fs.mouth_width, MOUTH_THICKNESS
    curve, openness = fs.mouth_curve * 40.0, fs.mouth_open * 40.0
    col = face_get_emotion_color(fs)
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
            curve_y = curve * shape
            upper_y = cy + curve_y - openness * shape
            lower_y = cy + curve_y + openness * shape
            dist = (
                0.0
                if (openness > 1.0 and upper_y < py < lower_y)
                else min(abs(py - upper_y), abs(py - lower_y))
            )
            alpha = 1.0 - smoothstep(thick / 2.0 - 1.0, thick / 2.0 + 1.0, dist)
            if alpha > 0:
                set_px_blend(buf, row_idx + x, draw_col, alpha)


# ── Main render entry point ──────────────────────────────────────────


def render_face(
    fs: FaceState,
    border_renderer: object | None = None,
) -> list[tuple[int, int, int]]:
    """Render a complete frame into a pixel buffer.

    border_renderer: optional BorderRenderer for conversation border.
    """
    buf: list[tuple[int, int, int]] = [BG_COLOR] * (SCREEN_W * SCREEN_H)

    # System overlay check
    mode = fs.system.mode
    if mode != SystemMode.NONE:
        if mode == SystemMode.BOOTING:
            _render_booting(buf, fs)
        elif mode == SystemMode.ERROR_DISPLAY:
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

    # Border background layer (behind eyes)
    if border_renderer is not None and hasattr(border_renderer, "render"):
        border_renderer.render(buf)  # type: ignore[attr-defined]

    # Eyes + mouth
    _render_eye(buf, fs, True)
    _render_eye(buf, fs, False)
    _render_mouth(buf, fs)

    # Post-processing effects
    if fs.fx.afterglow:
        apply_afterglow(buf, fs)
    if fs.anim.rage:
        render_fire(buf, fs)
    render_sparkles(buf, fs)

    # Buttons foreground layer (on top of everything)
    if border_renderer is not None and hasattr(border_renderer, "render_buttons"):
        border_renderer.render_buttons(buf)  # type: ignore[attr-defined]

    # Store frame for afterglow
    if fs.fx.afterglow:
        fs.fx.afterglow_buf = buf[:]

    return buf
