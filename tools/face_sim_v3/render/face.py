"""Face renderer — eye, mouth, system overlays.

Renders into a list[tuple[int,int,int]] pixel buffer (320x240).
Port from face_render_v2.py with all constants from constants.py.
"""

from __future__ import annotations

import math
import time

from tools.face_sim_v3.render.effects import (
    apply_afterglow,
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
    HEART_PUPIL_SCALE,
    HEART_SOLID_SCALE,
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


# ── System animation face drivers ────────────────────────────────────
# These modify FaceState so the normal renderer draws Buddy's face in
# system-appropriate poses.  Small SDF icons overlay afterward.


def _sys_booting(fs: FaceState) -> None:
    """'Waking up' — eyes open from sleepy slits, yawn, settle to neutral."""
    elapsed = time.monotonic() - fs.system.timer
    BOOT_DUR = 3.0  # total duration
    t = _clamp(elapsed / BOOT_DUR, 0.0, 1.0)

    # Phase 1 (0-40%): sleepy slits slowly opening
    # Phase 2 (40-65%): yawn (mouth opens wide, slight eye squeeze)
    # Phase 3 (65-85%): eyes open fully, blink
    # Phase 4 (85-100%): settle to neutral with happy bounce

    if t < 0.4:
        # Sleepy slits opening
        p = t / 0.4  # 0→1
        droop = 0.6 * (1.0 - p)
        fs.eyelids.top_l = droop
        fs.eyelids.top_r = droop
        fs.eye_l.height_scale = 0.7 + 0.15 * p
        fs.eye_r.height_scale = 0.7 + 0.15 * p
        fs.eyelids.slope = -0.2 * (1.0 - p)
        # Color: navy → transitioning
        frac = p
        fs.mood_color_override = (
            int(70 + (50 - 70) * frac),
            int(90 + (150 - 90) * frac),
            int(140 + (255 - 140) * frac),
        )
    elif t < 0.65:
        # Yawn: mouth opens wide, eyes squeeze slightly
        p = (t - 0.4) / 0.25
        yawn = math.sin(p * 3.14159)  # peaks at p=0.5
        fs.mouth_open = 0.6 * yawn
        fs.mouth_width = 1.0 + 0.2 * yawn
        fs.mouth_curve = -0.1 * yawn
        fs.eyelids.top_l = 0.15 * yawn
        fs.eyelids.top_r = 0.15 * yawn
        fs.eye_l.height_scale = 0.85 - 0.1 * yawn
        fs.eye_r.height_scale = 0.85 - 0.1 * yawn
        fs.mood_color_override = (50, 150, 255)
    elif t < 0.85:
        # Eyes open fully, quick blink at 75%
        p = (t - 0.65) / 0.2
        blink_p = abs(p - 0.5) * 2.0  # V-shape: 1→0→1
        fs.eyelids.top_l = 0.7 * (1.0 - blink_p) if p > 0.4 and p < 0.6 else 0.0
        fs.eyelids.top_r = fs.eyelids.top_l
        fs.eye_l.height_scale = 1.0
        fs.eye_r.height_scale = 1.0
        fs.mood_color_override = (50, 150, 255)
    else:
        # Happy bounce settle
        p = (t - 0.85) / 0.15
        bounce = math.sin(p * 3.14159) * 0.05
        fs.eye_l.height_scale = 1.0 + bounce
        fs.eye_r.height_scale = 1.0 + bounce
        fs.mouth_curve = 0.3 * math.sin(p * 3.14159)
        fs.mood_color_override = (
            int(50 + (0 - 50) * p),
            int(150 + (255 - 150) * p),
            int(255 + (200 - 255) * p),
        )
    # Breathing ramps in over last 30%
    fs.fx.breathing = t > 0.7


def _sys_shutdown(fs: FaceState) -> None:
    """'Going to sleep' — yawn, droop, close eyes, fade to black."""
    elapsed = time.monotonic() - fs.system.timer
    SHUT_DUR = 2.5
    t = _clamp(elapsed / SHUT_DUR, 0.0, 1.0)

    # Phase 1 (0-30%): yawn
    # Phase 2 (30-60%): eyes droop, gaze sways
    # Phase 3 (60-85%): eyes close with small smile
    # Phase 4 (85-100%): fade to black

    if t < 0.3:
        p = t / 0.3
        yawn = math.sin(p * 3.14159)
        fs.mouth_open = 0.5 * yawn
        fs.mouth_width = 1.0 + 0.15 * yawn
        fs.eyelids.top_l = 0.1 * yawn
        fs.eyelids.top_r = 0.1 * yawn
        fs.eye_l.height_scale = 1.0 - 0.1 * yawn
        fs.eye_r.height_scale = 1.0 - 0.1 * yawn
    elif t < 0.6:
        p = (t - 0.3) / 0.3
        droop = 0.15 + 0.35 * p
        fs.eyelids.top_l = droop
        fs.eyelids.top_r = droop
        fs.eye_l.height_scale = 0.9 - 0.15 * p
        fs.eye_r.height_scale = 0.9 - 0.15 * p
        fs.eyelids.slope = -0.2 * p
        # Gentle side-to-side sway, slowing down
        sway_amp = 3.0 * (1.0 - p)
        sway = math.sin(elapsed * 2.0) * sway_amp
        fs.eye_l.gaze_x = sway
        fs.eye_r.gaze_x = sway
    elif t < 0.85:
        p = (t - 0.6) / 0.25
        fs.eyelids.top_l = 0.5 + 0.5 * p
        fs.eyelids.top_r = 0.5 + 0.5 * p
        fs.eye_l.height_scale = 0.75 - 0.35 * p
        fs.eye_r.height_scale = 0.75 - 0.35 * p
        fs.eyelids.slope = -0.2
        # Small content smile as eyes close
        fs.mouth_curve = 0.3 * p
    else:
        # Fully closed, fade brightness
        p = (t - 0.85) / 0.15
        fs.eyelids.top_l = 1.0
        fs.eyelids.top_r = 1.0
        fs.eye_l.height_scale = 0.4
        fs.eye_r.height_scale = 0.4
        fs.mouth_curve = 0.3
        fs.brightness = 1.0 - p

    # Color fades from cyan to navy to black
    if t < 0.6:
        frac = t / 0.6
        fs.mood_color_override = (
            int(50 * (1.0 - frac) + 70 * frac),
            int(150 * (1.0 - frac) + 90 * frac),
            int(255 * (1.0 - frac) + 140 * frac),
        )
    else:
        frac = (t - 0.6) / 0.4
        fs.mood_color_override = (
            int(70 * (1.0 - frac)),
            int(90 * (1.0 - frac)),
            int(140 * (1.0 - frac)),
        )
    fs.fx.breathing = t < 0.5


def _sys_error(fs: FaceState) -> None:
    """'Confused Buddy' — worried expression + slow headshake."""
    elapsed = time.monotonic() - fs.system.timer

    # CONFUSED expression: asymmetric mouth, inner brow furrow
    fs.eyelids.slope = 0.2  # inner furrow
    fs.eyelids.top_l = 0.1
    fs.eyelids.top_r = 0.1
    fs.mouth_curve = -0.2
    fs.mouth_offset_x = 2.0 * math.sin(elapsed * 3.0)  # slight wobble

    # Slow headshake
    shake = math.sin(elapsed * 4.0) * 3.0
    fs.eye_l.gaze_x = shake
    fs.eye_r.gaze_x = shake

    # Warm orange/amber color
    fs.mood_color_override = (220, 160, 60)
    fs.expression_intensity = 0.7


def _sys_error_icon(buf: list) -> None:
    """Draw tiny warning icon in lower-right corner (20px triangle + !)."""
    # Icon position: lower-right corner with margin
    icon_cx = SCREEN_W - 22
    icon_cy = SCREEN_H - 22
    icon_r = 10.0
    icon_col = (255, 180, 50)

    x0 = max(0, icon_cx - 14)
    x1 = min(SCREEN_W, icon_cx + 14)
    y0 = max(0, icon_cy - 14)
    y1 = min(SCREEN_H, icon_cy + 14)

    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5
            d_tri = sd_equilateral_triangle(px, py, icon_cx, icon_cy, icon_r)
            alpha = 1.0 - smoothstep(0.0, 1.5, d_tri)
            if alpha > 0.01:
                set_px_blend(buf, row + x, icon_col, alpha)
            # Exclamation mark: small bar + dot
            d_bar = sd_rounded_box(px, py, icon_cx, icon_cy - 2, 1.5, 4.0, 0.5)
            d_dot = sd_circle(px, py, icon_cx, icon_cy + 4.5, 1.5)
            d_mark = min(d_bar, d_dot)
            alpha_m = 1.0 - smoothstep(0.0, 1.0, d_mark)
            if alpha_m > 0.01:
                set_px_blend(buf, row + x, (0, 0, 0), alpha_m)


def _sys_battery(fs: FaceState) -> None:
    """'Sleepy Buddy' — heavy eyelids, slow blinks, drowsy."""
    elapsed = time.monotonic() - fs.system.timer
    lvl = _clamp(fs.system.param, 0.0, 1.0)

    # Sleepy expression
    droop = 0.4 + 0.2 * (1.0 - lvl)  # more droop at lower battery
    fs.eyelids.top_l = droop
    fs.eyelids.top_r = droop
    fs.eyelids.slope = -0.2
    fs.eye_l.height_scale = 0.75
    fs.eye_r.height_scale = 0.75

    # Periodic yawns at low battery
    if lvl < 0.2:
        yawn_cycle = elapsed % 6.0  # yawn every 6 seconds
        if yawn_cycle < 1.5:
            yawn = math.sin(yawn_cycle / 1.5 * 3.14159)
            fs.mouth_open = 0.5 * yawn
            fs.mouth_width = 1.0 + 0.1 * yawn
            fs.eyelids.top_l = min(0.8, droop + 0.2 * yawn)
            fs.eyelids.top_r = min(0.8, droop + 0.2 * yawn)

    # Slow breathing
    fs.fx.breathing = True

    # Navy/deep blue color, dimmer at lower battery
    dim = 0.6 + 0.4 * lvl
    fs.mood_color_override = (int(70 * dim), int(90 * dim), int(140 * dim))
    fs.brightness = 0.7 + 0.3 * lvl


def _sys_battery_icon(buf: list, lvl: float) -> None:
    """Draw tiny battery icon in lower-right corner."""
    bx = SCREEN_W - 24
    by = SCREEN_H - 18
    bw, bh = 16, 10  # half-dims for SDF
    col = (0, 220, 100) if lvl > 0.5 else (220, 180, 0) if lvl > 0.2 else (220, 40, 40)

    x0 = max(0, bx - 12)
    x1 = min(SCREEN_W, bx + 18)
    y0 = max(0, by - 8)
    y1 = min(SCREEN_H, by + 8)

    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5
            # Battery shell (outline)
            d_out = sd_rounded_box(px, py, bx, by, bw / 2, bh / 2, 1.5)
            d_in = sd_rounded_box(px, py, bx, by, bw / 2 - 1.5, bh / 2 - 1.5, 0.5)
            d_tip = sd_rounded_box(px, py, bx + bw / 2 + 2, by, 1.5, 3.0, 0.5)
            d_shell = min(max(d_out, -d_in), d_tip)
            alpha_s = 1.0 - smoothstep(0.0, 1.0, d_shell)
            if alpha_s > 0.01:
                set_px_blend(buf, row + x, (180, 180, 190), alpha_s)
            # Fill level
            fill_right = (bx - bw / 2 + 1.5) + (bw - 3) * lvl
            if d_in < 0 and px < fill_right:
                set_px_blend(buf, row + x, col, 0.9)


def _sys_updating(fs: FaceState) -> None:
    """'Thinking hard' — gaze drifts up-right, brow furrow, sparkle boost."""
    elapsed = time.monotonic() - fs.system.timer

    # THINKING expression
    fs.eyelids.slope = 0.4
    fs.eyelids.top_l = 0.2
    fs.eyelids.top_r = 0.2
    fs.mouth_curve = -0.1
    fs.mouth_offset_x = 1.5

    # Gaze drifts up-right with slow wander
    base_gx = 6.0
    base_gy = -4.0
    drift_x = math.sin(elapsed * 0.8) * 2.0
    drift_y = math.cos(elapsed * 0.6) * 1.5
    fs.eye_l.gaze_x = base_gx + drift_x
    fs.eye_r.gaze_x = base_gx + drift_x
    fs.eye_l.gaze_y = base_gy + drift_y
    fs.eye_r.gaze_y = base_gy + drift_y

    # Blue-violet color
    fs.mood_color_override = (80, 135, 220)
    fs.expression_intensity = 0.6


def _sys_updating_bar(buf: list, progress: float) -> None:
    """Thin progress bar at bottom of screen."""
    bar_y = SCREEN_H - 4
    bar_h = 2
    bar_x0 = 20
    bar_x1 = SCREEN_W - 20
    fill_x = bar_x0 + int((bar_x1 - bar_x0) * _clamp(progress, 0.0, 1.0))
    col_fill = (80, 135, 220)
    col_bg = (30, 40, 60)

    for y in range(bar_y, min(SCREEN_H, bar_y + bar_h)):
        row = y * SCREEN_W
        for x in range(bar_x0, bar_x1):
            c = col_fill if x < fill_x else col_bg
            set_px_blend(buf, row + x, c, 0.8)


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
        heart_size = min(w, h) * HEART_SOLID_SCALE
        br = fs.brightness
        br_color = (
            int(base_color[0] * br),
            int(base_color[1] * br),
            int(base_color[2] * br),
        )
        for y in range(y0, y1):
            row_idx = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5, y + 0.5
                val = sd_heart(px, py, cx_base, cy_base, heart_size)
                alpha = 1.0 - smoothstep(-0.5, 0.5, val)
                if alpha > 0.01:
                    set_px_blend(buf, row_idx + x, br_color, alpha)
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
                    val = sd_heart(
                        px, py, pupil_cx, pupil_cy, PUPIL_R * HEART_PUPIL_SCALE
                    )
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

    # System mode: drive face state (system animations use Buddy's face,
    # not custom full-screen SDF scenes)
    mode = fs.system.mode
    fs.mood_color_override = None  # reset each frame
    if mode != SystemMode.NONE:
        if mode == SystemMode.BOOTING:
            _sys_booting(fs)
        elif mode == SystemMode.ERROR_DISPLAY:
            _sys_error(fs)
        elif mode == SystemMode.LOW_BATTERY:
            _sys_battery(fs)
        elif mode == SystemMode.UPDATING:
            _sys_updating(fs)
        elif mode == SystemMode.SHUTTING_DOWN:
            _sys_shutdown(fs)

    # Border background layer (behind eyes) — suppress during system overlays (spec §4.4)
    show_border = mode == SystemMode.NONE
    if (
        show_border
        and border_renderer is not None
        and hasattr(border_renderer, "render")
    ):
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

    # Holiday rendering overlays
    from tools.face_sim_v3.state.constants import HolidayMode

    if fs.holiday_mode == HolidayMode.CHRISTMAS:
        from tools.face_sim_v3.render.effects import render_rosy_cheeks, render_snow

        render_snow(buf, fs)
        render_rosy_cheeks(buf)
    elif fs.holiday_mode == HolidayMode.NEW_YEAR:
        from tools.face_sim_v3.render.effects import render_confetti

        render_confetti(buf, fs)

    # System mode icon overlays (drawn on top of face)
    if mode == SystemMode.ERROR_DISPLAY:
        _sys_error_icon(buf)
    elif mode == SystemMode.LOW_BATTERY:
        _sys_battery_icon(buf, _clamp(fs.system.param, 0.0, 1.0))
    elif mode == SystemMode.UPDATING:
        _sys_updating_bar(buf, _clamp(fs.system.param, 0.0, 1.0))

    # Corner buttons + border ring — suppress during system overlays (spec §4.4)
    if (
        show_border
        and border_renderer is not None
        and hasattr(border_renderer, "render_buttons")
    ):
        border_renderer.render_buttons(buf)  # type: ignore[attr-defined]

    # Border ring re-pass over corner buttons for clean overlap
    if (
        show_border
        and border_renderer is not None
        and hasattr(border_renderer, "render")
    ):
        border_renderer.render(buf)  # type: ignore[attr-defined]

    # Store frame for afterglow
    if fs.fx.afterglow:
        fs.fx.afterglow_buf = buf[:]

    return buf
