"""Conversation border renderer.

Visual state (alpha, color, orbit) separated from state machine (conv_state.py).
Port from conv_border.py with constants from constants.py.
"""

from __future__ import annotations

import math

from tools.face_sim_v3.state.constants import (
    ATTENTION_DEPTH,
    BORDER_BLEND_RATE,
    BORDER_CORNER_R,
    BORDER_FRAME_W,
    BORDER_GLOW_W,
    BTN_RADIUS,
    CANCEL_CX,
    CANCEL_CY,
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
    PTT_CX,
    PTT_CY,
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
        self.ptt_active: bool = False
        self.cancel_pressed: bool = False

    def set_energy(self, energy: float) -> None:
        self.energy = _clamp(energy, 0.0, 1.0)

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

    # ── Button rendering ─────────────────────────────────────────────

    def render_buttons(self, buf: list) -> None:
        """Draw PTT and Cancel buttons (call after eyes/mouth)."""
        self._draw_button_ptt(buf)
        self._draw_button_cancel(buf)

    def _draw_button_ptt(self, buf: list) -> None:
        cx, cy, r = PTT_CX, PTT_CY, BTN_RADIUS
        if self.ptt_active:
            active_col = (
                self.color if self.alpha > 0.1 else CONV_COLORS[ConvState.LISTENING]
            )
            bg_col = active_col
            bg_alpha = 0.55
            border_col = _scale_color(active_col, 1.2)
            icon_col = (255, 255, 255)
        else:
            bg_col = BTN_IDLE_BG
            bg_alpha = BTN_IDLE_ALPHA
            border_col = BTN_IDLE_BORDER
            icon_col = BTN_ICON_COLOR

        x0 = max(0, cx - r - 2)
        x1 = min(SCREEN_W, cx + r + 2)
        y0 = max(0, cy - r - 2)
        y1 = min(SCREEN_H, cy + r + 2)

        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                d = math.sqrt((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2)
                if d < r - 1:
                    _blend(buf, row + x, bg_col, bg_alpha)
                elif d < r + 0.5:
                    ba = max(0.0, 1.0 - abs(d - r + 0.5))
                    _blend(buf, row + x, border_col, ba * 0.8)

        # Sound wave icon
        dot_r = 2.5
        arc_radii = (6.0, 10.0, 14.0)
        arc_thick = 1.3
        arc_min = -70.0 * math.pi / 180.0
        arc_max = 70.0 * math.pi / 180.0

        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5 - cx, y + 0.5 - cy
                dist = math.sqrt(px * px + py * py)
                if dist < dot_r:
                    a = 1.0 - max(0, (dist - dot_r + 1.0))
                    _blend(buf, row + x, icon_col, min(1.0, a))
                    continue
                angle = math.atan2(py, px)
                if arc_min <= angle <= arc_max:
                    for ar in arc_radii:
                        ad = abs(dist - ar)
                        if ad < arc_thick:
                            a = 1.0 - ad / arc_thick
                            if self.ptt_active:
                                phase = (self._current_timer * 3.0 - ar / 14.0) % 1.0
                                a *= 0.5 + 0.5 * max(0, math.sin(phase * math.pi))
                            _blend(buf, row + x, icon_col, a * 0.9)
                            break

    def _draw_button_cancel(self, buf: list) -> None:
        cx, cy, r = CANCEL_CX, CANCEL_CY, BTN_RADIUS
        if self.cancel_pressed:
            bg_col = BTN_CANCEL_ACTIVE
            bg_alpha = 0.55
            border_col = _scale_color(BTN_CANCEL_ACTIVE, 0.8)
            icon_col = (255, 255, 255)
        else:
            bg_col = BTN_IDLE_BG
            bg_alpha = BTN_IDLE_ALPHA
            border_col = BTN_IDLE_BORDER
            icon_col = BTN_ICON_COLOR

        x0 = max(0, cx - r - 2)
        x1 = min(SCREEN_W, cx + r + 2)
        y0 = max(0, cy - r - 2)
        y1 = min(SCREEN_H, cy + r + 2)

        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                d = math.sqrt((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2)
                if d < r - 1:
                    _blend(buf, row + x, bg_col, bg_alpha)
                elif d < r + 0.5:
                    ba = max(0.0, 1.0 - abs(d - r + 0.5))
                    _blend(buf, row + x, border_col, ba * 0.8)

        # X mark icon
        arm = r * 0.45
        thick = 2.0
        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5 - cx, y + 0.5 - cy
                d1 = abs(px - py) / 1.414
                d2 = abs(px + py) / 1.414
                if abs(px) >= arm or abs(py) >= arm:
                    continue
                d = min(d1, d2)
                if d < thick:
                    a = 1.0 - d / thick
                    _blend(buf, row + x, icon_col, a * 0.9)
