"""Conversation border renderer.

Visual state (alpha, color, orbit) separated from state machine (conv_state.py).
Port from conv_border.py with constants from constants.py.
"""

from __future__ import annotations

import math

from tools.face_sim_v3.render.sdf import sd_cross, sd_rounded_box, sdf_alpha
from tools.face_sim_v3.state.constants import (
    ATTENTION_DEPTH,
    BORDER_BLEND_RATE,
    BORDER_CORNER_R,
    BORDER_FRAME_W,
    BORDER_GLOW_W,
    BTN_CORNER_INNER_R,
    BTN_ICON_SIZE,
    BTN_LEFT_ICON_CX,
    BTN_LEFT_ICON_CY,
    BTN_LEFT_ZONE_X1,
    BTN_RIGHT_ICON_CX,
    BTN_RIGHT_ICON_CY,
    BTN_RIGHT_ZONE_X0,
    BTN_ZONE_Y_TOP,
    ButtonIcon,
    ButtonState,
    CONV_COLORS,
    DONE_FADE_SPEED,
    ERROR_DECAY_RATE,
    ERROR_FLASH_DURATION,
    LED_SCALE,
    LISTENING_ALPHA_BASE,
    LISTENING_ALPHA_MOD,
    LISTENING_BREATH_FREQ,
    PTT_ALPHA_BASE,
    PTT_ALPHA_MOD,
    PTT_PULSE_FREQ,
    SCREEN_H,
    SCREEN_W,
    SPEAKING_ALPHA_BASE,
    SPEAKING_ALPHA_MOD,
    THINKING_BORDER_ALPHA,
    THINKING_ORBIT_DOT_R,
    THINKING_ORBIT_DOTS,
    THINKING_ORBIT_SPACING,
    THINKING_ORBIT_SPEED,
    ConvState,
)

# ── Helpers ──────────────────────────────────────────────────────────

BTN_IDLE_BG = (40, 44, 52)
BTN_IDLE_BORDER = (80, 90, 100)
BTN_IDLE_ALPHA = 0.35
BTN_ICON_COLOR = (200, 210, 220)
BTN_CANCEL_ACTIVE = (255, 120, 80)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _lerp_color(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = _clamp(t, 0.0, 1.0)
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _scale_color(c: tuple[int, int, int], s: float) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(c[0] * s))),
        max(0, min(255, int(c[1] * s))),
        max(0, min(255, int(c[2] * s))),
    )


def _blend(buf: list, idx: int, color: tuple[int, int, int], alpha: float) -> None:
    if alpha <= 0.0 or idx < 0 or idx >= len(buf):
        return
    o = buf[idx]
    if alpha >= 1.0:
        buf[idx] = (min(255, color[0]), min(255, color[1]), min(255, color[2]))
    else:
        buf[idx] = (
            min(255, int(o[0] + (color[0] - o[0]) * alpha)),
            min(255, int(o[1] + (color[1] - o[1]) * alpha)),
            min(255, int(o[2] + (color[2] - o[2]) * alpha)),
        )


# ── Inner SDF ────────────────────────────────────────────────────────

_INNER_HW = SCREEN_W / 2.0 - BORDER_FRAME_W
_INNER_HH = SCREEN_H / 2.0 - BORDER_FRAME_W
_CX = SCREEN_W / 2.0
_CY = SCREEN_H / 2.0


def _inner_sdf(px: float, py: float) -> float:
    r = BORDER_CORNER_R
    dx = abs(px - _CX) - _INNER_HW + r
    dy = abs(py - _CY) - _INNER_HH + r
    return min(max(dx, dy), 0.0) + math.sqrt(max(dx, 0) ** 2 + max(dy, 0) ** 2) - r


def _perimeter_xy(t: float) -> tuple[float, float]:
    """Map normalized position [0, 1) to (x, y) on the inner frame centre-line."""
    inset = BORDER_FRAME_W / 2.0
    w = SCREEN_W - 2 * inset
    h = SCREEN_H - 2 * inset
    perim = 2.0 * (w + h)
    d = (t % 1.0) * perim
    if d < w:
        return inset + d, inset
    d -= w
    if d < h:
        return inset + w, inset + d
    d -= h
    if d < w:
        return inset + w - d, inset + h
    d -= w
    return inset, inset + h - d


# ══════════════════════════════════════════════════════════════════════
#  BorderRenderer
# ══════════════════════════════════════════════════════════════════════


class BorderRenderer:
    """Conversation border visual state + rendering.

    Reads state from a ConvStateMachine; manages visual interpolation.
    """

    def __init__(self) -> None:
        self.alpha: float = 0.0
        self.color: tuple[int, int, int] = (0, 0, 0)
        self.orbit_pos: float = 0.0
        self.led_color: tuple[int, int, int] = (0, 0, 0)
        self.energy: float = 0.0

        # Corner button state
        self.btn_left_icon: int = ButtonIcon.MIC
        self.btn_left_state: int = ButtonState.IDLE
        self.btn_left_color: tuple[int, int, int] = (0, 0, 0)
        self.btn_right_icon: int = ButtonIcon.X_MARK
        self.btn_right_state: int = ButtonState.IDLE
        self.btn_right_color: tuple[int, int, int] = (0, 0, 0)
        self._btn_left_flash: float = 0.0
        self._btn_right_flash: float = 0.0

    def set_energy(self, energy: float) -> None:
        self.energy = _clamp(energy, 0.0, 1.0)

    def set_button_left(
        self,
        icon: int,
        state: int,
        color: tuple[int, int, int] | None = None,
    ) -> None:
        self.btn_left_icon = icon
        self.btn_left_state = state
        if color is not None:
            self.btn_left_color = color
        if state == ButtonState.PRESSED:
            self._btn_left_flash = 0.15

    def set_button_right(
        self,
        icon: int,
        state: int,
        color: tuple[int, int, int] | None = None,
    ) -> None:
        self.btn_right_icon = icon
        self.btn_right_state = state
        if color is not None:
            self.btn_right_color = color
        if state == ButtonState.PRESSED:
            self._btn_right_flash = 0.15

    # Backward-compat properties
    @property
    def ptt_active(self) -> bool:
        return self.btn_left_state != ButtonState.IDLE

    @ptt_active.setter
    def ptt_active(self, val: bool) -> None:
        if val:
            col = self.color if self.alpha > 0.1 else CONV_COLORS[ConvState.LISTENING]
            self.set_button_left(ButtonIcon.MIC, ButtonState.ACTIVE, col)
        else:
            self.set_button_left(ButtonIcon.MIC, ButtonState.IDLE)

    @property
    def cancel_pressed(self) -> bool:
        return self.btn_right_state == ButtonState.PRESSED

    @cancel_pressed.setter
    def cancel_pressed(self, val: bool) -> None:
        if val:
            self.set_button_right(
                ButtonIcon.X_MARK, ButtonState.PRESSED, BTN_CANCEL_ACTIVE
            )
        else:
            self.set_button_right(ButtonIcon.X_MARK, ButtonState.IDLE)

    def update(self, state: ConvState, timer: float, dt: float) -> None:
        """Update visual state based on conversation state."""
        s = state

        if s == ConvState.IDLE:
            self.alpha = _clamp(self.alpha - dt * BORDER_BLEND_RATE, 0.0, 1.0)

        elif s == ConvState.ATTENTION:
            if timer < 0.4:
                self.alpha = 1.0
                self.color = CONV_COLORS[ConvState.ATTENTION]

        elif s == ConvState.LISTENING:
            target = LISTENING_ALPHA_BASE + LISTENING_ALPHA_MOD * math.sin(
                timer * 2.0 * math.pi * LISTENING_BREATH_FREQ
            )
            self.alpha += (target - self.alpha) * min(1.0, dt * BORDER_BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.LISTENING],
                min(1.0, dt * BORDER_BLEND_RATE),
            )

        elif s == ConvState.PTT:
            target = PTT_ALPHA_BASE + PTT_ALPHA_MOD * math.sin(
                timer * 2.0 * math.pi * PTT_PULSE_FREQ
            )
            self.alpha += (target - self.alpha) * min(1.0, dt * BORDER_BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.PTT],
                min(1.0, dt * BORDER_BLEND_RATE),
            )

        elif s == ConvState.THINKING:
            target = THINKING_BORDER_ALPHA
            self.alpha += (target - self.alpha) * min(1.0, dt * BORDER_BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.THINKING],
                min(1.0, dt * BORDER_BLEND_RATE),
            )
            self.orbit_pos = (self.orbit_pos + THINKING_ORBIT_SPEED * dt) % 1.0

        elif s == ConvState.SPEAKING:
            target = SPEAKING_ALPHA_BASE + SPEAKING_ALPHA_MOD * self.energy
            self.alpha += (target - self.alpha) * min(1.0, dt * BORDER_BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.SPEAKING],
                min(1.0, dt * BORDER_BLEND_RATE),
            )

        elif s == ConvState.ERROR:
            if timer < ERROR_FLASH_DURATION:
                self.alpha = 1.0
                self.color = CONV_COLORS[ConvState.ERROR]
            else:
                self.alpha = math.exp(
                    -(timer - ERROR_FLASH_DURATION) * ERROR_DECAY_RATE
                )

        elif s == ConvState.DONE:
            self.alpha = _clamp(self.alpha - dt * DONE_FADE_SPEED, 0.0, 1.0)

        # LED mirrors border color at reduced brightness
        if self.alpha > 0.01:
            led_s = self.alpha * LED_SCALE
            self.led_color = _scale_color(self.color, led_s)
        else:
            self.led_color = (0, 0, 0)

        # Button flash decay
        if self._btn_left_flash > 0:
            self._btn_left_flash = max(0.0, self._btn_left_flash - dt)
            if self._btn_left_flash <= 0 and self.btn_left_state == ButtonState.PRESSED:
                self.btn_left_state = ButtonState.ACTIVE
        if self._btn_right_flash > 0:
            self._btn_right_flash = max(0.0, self._btn_right_flash - dt)
            if (
                self._btn_right_flash <= 0
                and self.btn_right_state == ButtonState.PRESSED
            ):
                self.btn_right_state = ButtonState.ACTIVE

    # ── Frame rendering ──────────────────────────────────────────────

    def render(self, buf: list) -> None:
        """Draw the border frame onto the pixel buffer (call before eyes)."""
        if self.alpha < 0.01 and self._current_state != ConvState.ATTENTION:
            return

        if self._current_state == ConvState.ATTENTION and self._current_timer < 0.4:
            self._render_attention(buf)
            return

        depth = BORDER_FRAME_W + BORDER_GLOW_W
        W, H = SCREEN_W, SCREEN_H
        for y in range(H):
            dv = min(y, H - 1 - y)
            row = y * W
            if dv >= depth:
                for x in range(depth):
                    self._frame_px(buf, row + x, x, y)
                for x in range(W - depth, W):
                    self._frame_px(buf, row + x, x, y)
            else:
                for x in range(W):
                    dh = min(x, W - 1 - x)
                    if dh >= depth and dv >= depth:
                        continue
                    self._frame_px(buf, row + x, x, y)

        if self._current_state == ConvState.THINKING and self.alpha > 0.01:
            self._render_dots(buf)

    def update_state_ref(self, state: ConvState, timer: float) -> None:
        """Store state reference for render pass."""
        self._current_state = state
        self._current_timer = timer

    _current_state: ConvState = ConvState.IDLE
    _current_timer: float = 0.0

    def _frame_px(self, buf: list, idx: int, x: int, y: int) -> None:
        d = _inner_sdf(x + 0.5, y + 0.5)
        if d > 0:
            a = self.alpha
        elif d > -BORDER_GLOW_W:
            t = (d + BORDER_GLOW_W) / BORDER_GLOW_W
            a = self.alpha * t * t
        else:
            return
        if a > 0.01:
            _blend(buf, idx, self.color, a)

    def _render_attention(self, buf: list) -> None:
        progress = self._current_timer / 0.4
        sweep = ATTENTION_DEPTH * progress
        col = CONV_COLORS[ConvState.ATTENTION]
        fade_global = 1.0 - progress * 0.5
        limit = int(sweep) + 1
        W, H = SCREEN_W, SCREEN_H
        for y in range(H):
            dv = min(y, H - 1 - y)
            row = y * W
            if dv > limit:
                for x in range(min(limit, W)):
                    self._attn_px(buf, row + x, x, sweep, col, fade_global)
                for x in range(max(0, W - limit), W):
                    self._attn_px(
                        buf, row + x, min(x, W - 1 - x), sweep, col, fade_global
                    )
            else:
                for x in range(W):
                    d = min(x, dv, W - 1 - x)
                    self._attn_px(buf, row + x, d, sweep, col, fade_global)

    @staticmethod
    def _attn_px(
        buf: list,
        idx: int,
        dist: int,
        sweep: float,
        col: tuple[int, int, int],
        fade: float,
    ) -> None:
        if dist >= sweep:
            return
        f = (1.0 - dist / max(1.0, sweep)) * fade
        a = f * f
        if a > 0.01:
            _blend(buf, idx, col, a)

    def _render_dots(self, buf: list) -> None:
        brightnesses = (1.0, 0.7, 0.4)
        dot_col = CONV_COLORS[ConvState.THINKING]
        for i in range(THINKING_ORBIT_DOTS):
            pos = (self.orbit_pos - i * THINKING_ORBIT_SPACING) % 1.0
            dx, dy = _perimeter_xy(pos)
            bri = brightnesses[i] if i < len(brightnesses) else 0.3
            c = _scale_color(dot_col, bri)
            r = THINKING_ORBIT_DOT_R
            x0 = max(0, int(dx - r - 1))
            x1 = min(SCREEN_W, int(dx + r + 2))
            y0 = max(0, int(dy - r - 1))
            y1 = min(SCREEN_H, int(dy + r + 2))
            for y in range(y0, y1):
                row = y * SCREEN_W
                for x in range(x0, x1):
                    d = math.sqrt((x + 0.5 - dx) ** 2 + (y + 0.5 - dy) ** 2)
                    if d < r:
                        a = min(1.0, (1.0 - (d / r) ** 2) * 2.5)
                        if a > 0.01:
                            _blend(buf, row + x, c, a)

    # ── Corner button rendering ────────────────────────────────────────

    def render_buttons(self, buf: list) -> None:
        """Draw left and right corner-zone buttons (call after eyes/mouth)."""
        if self.btn_left_icon != ButtonIcon.NONE:
            self._draw_button_zone(buf, is_left=True)
        if self.btn_right_icon != ButtonIcon.NONE:
            self._draw_button_zone(buf, is_left=False)

    def _draw_button_zone(self, buf: list, *, is_left: bool) -> None:
        icon = self.btn_left_icon if is_left else self.btn_right_icon
        state = self.btn_left_state if is_left else self.btn_right_state
        active_color = self.btn_left_color if is_left else self.btn_right_color
        flash = self._btn_left_flash if is_left else self._btn_right_flash

        if state == ButtonState.PRESSED or flash > 0:
            bg_col = _scale_color(active_color, 1.3)
            bg_alpha = 0.75
            border_col = (255, 255, 255)
            icon_col = (255, 255, 255)
        elif state == ButtonState.ACTIVE:
            bg_col = active_color
            bg_alpha = 0.55
            border_col = _scale_color(active_color, 1.2)
            icon_col = (255, 255, 255)
        else:
            bg_col = BTN_IDLE_BG
            bg_alpha = BTN_IDLE_ALPHA
            border_col = BTN_IDLE_BORDER
            icon_col = BTN_ICON_COLOR

        _draw_corner_zone(buf, is_left, bg_col, bg_alpha, border_col)

        if is_left:
            icx, icy = float(BTN_LEFT_ICON_CX), float(BTN_LEFT_ICON_CY)
        else:
            icx, icy = float(BTN_RIGHT_ICON_CX), float(BTN_RIGHT_ICON_CY)

        active = state != ButtonState.IDLE
        _draw_icon(
            buf, icx, icy, icon, icon_col, BTN_ICON_SIZE, self._current_timer, active
        )


# ── Corner zone background ──────────────────────────────────────────


def _draw_corner_zone(
    buf: list,
    is_left: bool,
    bg_col: tuple[int, int, int],
    bg_alpha: float,
    border_col: tuple[int, int, int],
) -> None:
    """Draw a rounded-inner-corner rectangle in a bottom corner."""
    R = BTN_CORNER_INNER_R
    if is_left:
        x0, x1 = 0, BTN_LEFT_ZONE_X1
        # Rounded corner center: top-right of zone
        rcx = BTN_LEFT_ZONE_X1 - R
        rcy = BTN_ZONE_Y_TOP + R
    else:
        x0, x1 = BTN_RIGHT_ZONE_X0, SCREEN_W
        # Rounded corner center: top-left of zone
        rcx = BTN_RIGHT_ZONE_X0 + R
        rcy = BTN_ZONE_Y_TOP + R

    for y in range(BTN_ZONE_Y_TOP, SCREEN_H):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5

            # Check inner rounded corner cutout
            if is_left:
                in_corner_quad = px > rcx and py < rcy
            else:
                in_corner_quad = px < rcx and py < rcy

            if in_corner_quad:
                dx = px - rcx
                dy = py - rcy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > R + 0.5:
                    continue
                if dist > R - 0.5:
                    # AA on the curved edge
                    a = bg_alpha * _clamp(R + 0.5 - dist, 0.0, 1.0)
                    if a > 0.01:
                        _blend(buf, row + x, bg_col, a)
                    # Border on the curve
                    ba = _clamp(1.0 - abs(dist - R), 0.0, 1.0) * 0.6
                    if ba > 0.01:
                        _blend(buf, row + x, border_col, ba)
                    continue

            _blend(buf, row + x, bg_col, bg_alpha)

            # Thin border on inner edges (not screen edges)
            on_top = y == BTN_ZONE_Y_TOP and not in_corner_quad
            on_inner_side = (is_left and x == x1 - 1) or (not is_left and x == x0)
            if on_inner_side and py >= rcy:
                _blend(buf, row + x, border_col, 0.6)
            elif on_top:
                if is_left:
                    on_top_valid = px <= rcx
                else:
                    on_top_valid = px >= rcx
                if on_top_valid:
                    _blend(buf, row + x, border_col, 0.6)


# ── Icon dispatch ───────────────────────────────────────────────────


def _sd_line_seg(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Unsigned distance from point to line segment."""
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-10:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = _clamp(((px - ax) * dx + (py - ay) * dy) / len_sq, 0.0, 1.0)
    cx, cy = ax + t * dx, ay + t * dy
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2)


def _draw_icon(
    buf: list,
    cx: float,
    cy: float,
    icon: int,
    color: tuple[int, int, int],
    size: float,
    timer: float,
    active: bool,
) -> None:
    if icon == ButtonIcon.NONE:
        return
    elif icon == ButtonIcon.MIC:
        _icon_mic(buf, cx, cy, color, size, timer, active)
    elif icon == ButtonIcon.X_MARK:
        _icon_x_mark(buf, cx, cy, color, size)
    elif icon == ButtonIcon.CHECK:
        _icon_check(buf, cx, cy, color, size)
    elif icon == ButtonIcon.REPEAT:
        _icon_repeat(buf, cx, cy, color, size)
    elif icon == ButtonIcon.STAR:
        _icon_star(buf, cx, cy, color, size)
    elif icon == ButtonIcon.SPEAKER:
        _icon_speaker(buf, cx, cy, color, size, timer, active)


# ── Icon renderers ──────────────────────────────────────────────────


def _icon_mic(
    buf: list,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    size: float,
    timer: float,
    active: bool,
) -> None:
    """Microphone body + sound wave arcs."""
    mic_cx = cx - size * 0.22
    body_hw = size * 0.19
    body_hh = size * 0.39
    body_r = body_hw  # Capsule
    base_y = cy + size * 0.5
    base_hw = size * 0.22
    base_hh = size * 0.06
    arc_radii = (size * 0.44, size * 0.67, size * 0.89)
    arc_thick = size * 0.072
    arc_min = -70.0 * math.pi / 180.0
    arc_max = 70.0 * math.pi / 180.0

    x0 = max(0, int(cx - size - 1))
    x1 = min(SCREEN_W, int(cx + size + 1))
    y0 = max(0, int(cy - size - 1))
    y1 = min(SCREEN_H, int(cy + size + 1))

    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5

            # Mic body (capsule)
            d_body = sd_rounded_box(px, py, mic_cx, cy, body_hw, body_hh, body_r)
            a_body = sdf_alpha(d_body)
            if a_body > 0.01:
                _blend(buf, row + x, color, a_body * 0.9)
                continue

            # Base bar
            d_base = sd_rounded_box(px, py, mic_cx, base_y, base_hw, base_hh, 0.5)
            a_base = sdf_alpha(d_base)
            if a_base > 0.01:
                _blend(buf, row + x, color, a_base * 0.7)
                continue

            # Sound wave arcs (right side)
            dx_a, dy_a = px - mic_cx, py - cy
            dist = math.sqrt(dx_a * dx_a + dy_a * dy_a)
            angle = math.atan2(dy_a, dx_a)
            if arc_min <= angle <= arc_max:
                for ar in arc_radii:
                    ad = abs(dist - ar)
                    if ad < arc_thick:
                        a = 1.0 - ad / arc_thick
                        if active:
                            phase = (timer * 3.0 - ar / (size * 0.78)) % 1.0
                            a *= 0.5 + 0.5 * max(0.0, math.sin(phase * math.pi))
                        _blend(buf, row + x, color, a * 0.9)
                        break


def _icon_x_mark(
    buf: list,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    size: float,
) -> None:
    """X / cross mark using sd_cross."""
    arm = size * 0.5
    thick = size * 0.14
    x0 = max(0, int(cx - arm - 2))
    x1 = min(SCREEN_W, int(cx + arm + 2))
    y0 = max(0, int(cy - arm - 2))
    y1 = min(SCREEN_H, int(cy + arm + 2))
    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            d = sd_cross(x + 0.5, y + 0.5, cx, cy, arm, thick)
            a = sdf_alpha(d)
            if a > 0.01:
                _blend(buf, row + x, color, a * 0.9)


def _icon_check(
    buf: list,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    size: float,
) -> None:
    """Checkmark — two line segments forming a tick."""
    thick = size * 0.14
    # Vertex (bottom of check)
    vx = cx - size * 0.1
    vy = cy + size * 0.15
    # Short arm (down-left)
    a1x = vx - size * 0.25
    a1y = vy - size * 0.2
    # Long arm (up-right)
    a2x = vx + size * 0.45
    a2y = vy - size * 0.45

    x0 = max(0, int(cx - size - 1))
    x1 = min(SCREEN_W, int(cx + size + 1))
    y0 = max(0, int(cy - size - 1))
    y1 = min(SCREEN_H, int(cy + size + 1))

    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5
            d1 = _sd_line_seg(px, py, a1x, a1y, vx, vy) - thick
            d2 = _sd_line_seg(px, py, vx, vy, a2x, a2y) - thick
            d = min(d1, d2)
            a = sdf_alpha(d)
            if a > 0.01:
                _blend(buf, row + x, color, a * 0.9)


def _icon_repeat(
    buf: list,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    size: float,
) -> None:
    """Circular arrow — nearly complete ring + arrowhead."""
    ring_r = size * 0.45
    ring_thick = size * 0.08
    # Gap at the top (from -30 to +30 degrees measured from top = -pi/2)
    gap_half = 30.0 * math.pi / 180.0
    gap_center = -math.pi / 2.0
    gap_max = gap_center + gap_half

    # Arrowhead at the gap end (clockwise, so at gap_max)
    arrow_angle = gap_max
    tip_x = cx + ring_r * math.cos(arrow_angle)
    tip_y = cy + ring_r * math.sin(arrow_angle)
    # Arrow points tangentially (clockwise = downward at this angle)
    tang_angle = arrow_angle + math.pi / 2.0
    arr_len = size * 0.25
    arr_hw = size * 0.15
    base_x = tip_x - arr_len * math.cos(tang_angle)
    base_y = tip_y - arr_len * math.sin(tang_angle)
    perp_x = -math.sin(tang_angle)
    perp_y = math.cos(tang_angle)
    tri_a = (tip_x, tip_y)
    tri_b = (base_x + perp_x * arr_hw, base_y + perp_y * arr_hw)
    tri_c = (base_x - perp_x * arr_hw, base_y - perp_y * arr_hw)

    x0 = max(0, int(cx - size - 1))
    x1 = min(SCREEN_W, int(cx + size + 1))
    y0 = max(0, int(cy - size - 1))
    y1 = min(SCREEN_H, int(cy + size + 1))

    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5
            best_a = 0.0

            # Ring arc
            dx_r, dy_r = px - cx, py - cy
            dist = math.sqrt(dx_r * dx_r + dy_r * dy_r)
            angle = math.atan2(dy_r, dx_r)
            # Normalize angle difference from gap_center
            da = angle - gap_center
            da = (da + math.pi) % (2.0 * math.pi) - math.pi
            if abs(da) > gap_half:
                d_ring = abs(dist - ring_r) - ring_thick
                a_ring = sdf_alpha(d_ring)
                if a_ring > best_a:
                    best_a = a_ring

            # Arrowhead (point-in-triangle via barycentric)
            a_tri = _tri_alpha(px, py, tri_a, tri_b, tri_c)
            if a_tri > best_a:
                best_a = a_tri

            if best_a > 0.01:
                _blend(buf, row + x, color, best_a * 0.9)


def _tri_alpha(
    px: float,
    py: float,
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    """Soft alpha for point inside triangle (1.0 inside, AA at edges)."""
    # Signed area method
    d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1])
    d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (py - c[1])
    d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (py - a[1])
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    if has_neg and has_pos:
        return 0.0
    return 1.0


def _icon_star(
    buf: list,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    size: float,
) -> None:
    """Five-pointed star."""
    r_outer = size * 0.5
    r_inner = size * 0.22
    x0 = max(0, int(cx - size))
    x1 = min(SCREEN_W, int(cx + size))
    y0 = max(0, int(cy - size))
    y1 = min(SCREEN_H, int(cy + size))
    two_pi_5 = 2.0 * math.pi / 5.0
    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            dx_s, dy_s = x + 0.5 - cx, y + 0.5 - cy
            dist = math.sqrt(dx_s * dx_s + dy_s * dy_s)
            # Rotate so top point faces up
            angle = math.atan2(dy_s, dx_s) + math.pi / 2.0
            # Fold into one segment
            seg = angle % two_pi_5
            t = abs(seg / two_pi_5 - 0.5) * 2.0  # 0 at midpoint, 1 at tips
            edge_r = r_inner + (r_outer - r_inner) * t
            d = dist - edge_r
            a = sdf_alpha(d)
            if a > 0.01:
                _blend(buf, row + x, color, a * 0.9)


def _icon_speaker(
    buf: list,
    cx: float,
    cy: float,
    color: tuple[int, int, int],
    size: float,
    timer: float,
    active: bool,
) -> None:
    """Speaker cone + sound arcs."""
    # Cone: small rect on left + larger rect on right (wedge approximation)
    cone_cx = cx - size * 0.2
    small_hw = size * 0.1
    small_hh = size * 0.12
    big_hw = size * 0.1
    big_hh = size * 0.28
    big_cx = cone_cx - size * 0.15

    arc_cx = cone_cx + size * 0.05
    arc_radii = (size * 0.4, size * 0.6)
    arc_thick = size * 0.072
    arc_min = -60.0 * math.pi / 180.0
    arc_max = 60.0 * math.pi / 180.0

    x0 = max(0, int(cx - size - 1))
    x1 = min(SCREEN_W, int(cx + size + 1))
    y0 = max(0, int(cy - size - 1))
    y1 = min(SCREEN_H, int(cy + size + 1))

    for y in range(y0, y1):
        row = y * SCREEN_W
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5

            # Speaker body (two overlapping rects)
            d1 = sd_rounded_box(px, py, cone_cx, cy, small_hw, small_hh, 1.0)
            d2 = sd_rounded_box(px, py, big_cx, cy, big_hw, big_hh, 1.0)
            d_cone = min(d1, d2)
            a_cone = sdf_alpha(d_cone)
            if a_cone > 0.01:
                _blend(buf, row + x, color, a_cone * 0.9)
                continue

            # Sound arcs
            dx_a, dy_a = px - arc_cx, py - cy
            dist = math.sqrt(dx_a * dx_a + dy_a * dy_a)
            angle = math.atan2(dy_a, dx_a)
            if arc_min <= angle <= arc_max:
                for ar in arc_radii:
                    ad = abs(dist - ar)
                    if ad < arc_thick:
                        a = 1.0 - ad / arc_thick
                        if active:
                            phase = (timer * 3.0 - ar / (size * 0.6)) % 1.0
                            a *= 0.5 + 0.5 * max(0.0, math.sin(phase * math.pi))
                        _blend(buf, row + x, color, a * 0.9)
                        break
