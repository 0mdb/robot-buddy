"""Conversation border animation system.

Renders a rectangular frame around the 320x240 display to communicate
conversation state.  Syncs with a single LED color output.

States:
  IDLE      - No border
  ATTENTION - Inward sweep pulse (~400ms), auto-advances to LISTENING
  LISTENING - Breathing teal glow (~1.5 Hz)
  PTT       - Steady warm amber glow
  THINKING  - Blue-violet with orbiting comet dots (~2 s revolution)
  SPEAKING  - White-teal, energy-reactive brightness
  ERROR     - Amber flash + exponential decay (~800ms), auto-returns to IDLE
  DONE      - Outward fade (~500ms), auto-returns to IDLE
"""

from __future__ import annotations

import math
from enum import IntEnum

from face_state_v2 import SCREEN_W, SCREEN_H


class ConvState(IntEnum):
    IDLE = 0
    ATTENTION = 1
    LISTENING = 2
    PTT = 3
    THINKING = 4
    SPEAKING = 5
    ERROR = 6
    DONE = 7


# ── Color palette (independent of mood system) ─────────────────────

CONV_COLORS: dict[int, tuple[int, int, int]] = {
    ConvState.IDLE: (0, 0, 0),
    ConvState.ATTENTION: (180, 240, 255),
    ConvState.LISTENING: (0, 200, 220),
    ConvState.PTT: (255, 200, 80),
    ConvState.THINKING: (120, 100, 255),
    ConvState.SPEAKING: (200, 240, 255),
    ConvState.ERROR: (255, 160, 60),
    ConvState.DONE: (0, 0, 0),
}

CONV_NAMES = {s: s.name for s in ConvState}

# ── Geometry ────────────────────────────────────────────────────────

FRAME_W = 4
GLOW_W = 3
CORNER_R = 3.0
ATTENTION_DEPTH = 20
BLEND_RATE = 8.0  # per-second color/alpha interpolation speed

# Orbit (thinking dots)
ORBIT_DOTS = 3
ORBIT_SPACING = 0.12  # fraction of perimeter between trailing dots
ORBIT_SPEED = 0.5  # revolutions per second
ORBIT_DOT_R = 4.0

# ── Buttons ─────────────────────────────────────────────────────────

BTN_VISIBLE = 36
BTN_HITBOX = 48
BTN_MARGIN = 6
BTN_RADIUS = BTN_VISIBLE // 2  # 18

# PTT: bottom-left
PTT_CX = BTN_MARGIN + BTN_HITBOX // 2
PTT_CY = SCREEN_H - BTN_MARGIN - BTN_HITBOX // 2

# Cancel: bottom-right
CANCEL_CX = SCREEN_W - BTN_MARGIN - BTN_HITBOX // 2
CANCEL_CY = SCREEN_H - BTN_MARGIN - BTN_HITBOX // 2

BTN_IDLE_BG = (40, 44, 52)
BTN_IDLE_BORDER = (80, 90, 100)
BTN_IDLE_ALPHA = 0.35
BTN_ICON_COLOR = (200, 210, 220)
BTN_CANCEL_ACTIVE = (255, 120, 80)


# ── Helpers ─────────────────────────────────────────────────────────


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _lerp_color(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
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
    if alpha <= 0.0:
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


def _perimeter_xy(t: float) -> tuple[float, float]:
    """Map normalized position [0, 1) → (x, y) on the inner frame centre-line."""
    inset = FRAME_W / 2.0
    W = SCREEN_W - 2 * inset
    H = SCREEN_H - 2 * inset
    perim = 2.0 * (W + H)
    d = (t % 1.0) * perim
    if d < W:
        return inset + d, inset
    d -= W
    if d < H:
        return inset + W, inset + d
    d -= H
    if d < W:
        return inset + W - d, inset + H
    d -= W
    return inset, inset + H - d


# ── Inner SDF (used by frame + glow) ───────────────────────────────

_INNER_HW = SCREEN_W / 2.0 - FRAME_W
_INNER_HH = SCREEN_H / 2.0 - FRAME_W
_CX = SCREEN_W / 2.0
_CY = SCREEN_H / 2.0


def _inner_sdf(px: float, py: float) -> float:
    r = CORNER_R
    dx = abs(px - _CX) - _INNER_HW + r
    dy = abs(py - _CY) - _INNER_HH + r
    return min(max(dx, dy), 0.0) + math.sqrt(max(dx, 0) ** 2 + max(dy, 0) ** 2) - r


# ═══════════════════════════════════════════════════════════════════
#  ConvBorder – state machine + renderer
# ═══════════════════════════════════════════════════════════════════


class ConvBorder:
    """Conversation-state border animation controller."""

    def __init__(self) -> None:
        self.state: ConvState = ConvState.IDLE
        self.prev_state: ConvState = ConvState.IDLE
        self.timer: float = 0.0  # seconds since entering current state
        self.alpha: float = 0.0  # current frame alpha (0..1)
        self.color: tuple[int, int, int] = (0, 0, 0)
        self.orbit_pos: float = 0.0  # normalised [0, 1) for thinking dots
        self.energy: float = 0.0  # speaking energy [0, 1]
        self.led_color: tuple[int, int, int] = (0, 0, 0)
        self.ptt_active: bool = False
        self.cancel_pressed: bool = False

    # ── State transitions ───────────────────────────────────────────

    def set_state(self, state: ConvState) -> None:
        if state == self.state:
            return
        self.prev_state = self.state
        self.state = state
        self.timer = 0.0

    def set_energy(self, energy: float) -> None:
        self.energy = _clamp(energy, 0.0, 1.0)

    # ── Per-frame tick ──────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self.timer += dt
        s = self.state
        t = self.timer

        if s == ConvState.IDLE:
            self.alpha = _clamp(self.alpha - dt * BLEND_RATE, 0.0, 1.0)

        elif s == ConvState.ATTENTION:
            if t < 0.4:
                self.alpha = 1.0
                self.color = CONV_COLORS[ConvState.ATTENTION]
            else:
                # auto-advance to listening
                self.set_state(ConvState.LISTENING)

        elif s == ConvState.LISTENING:
            target = 0.6 + 0.3 * math.sin(t * 2.0 * math.pi * 1.5)
            self.alpha += (target - self.alpha) * min(1.0, dt * BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.LISTENING],
                min(1.0, dt * BLEND_RATE),
            )

        elif s == ConvState.PTT:
            target = 0.8 + 0.1 * math.sin(t * 2.0 * math.pi * 0.8)
            self.alpha += (target - self.alpha) * min(1.0, dt * BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.PTT],
                min(1.0, dt * BLEND_RATE),
            )

        elif s == ConvState.THINKING:
            target = 0.3
            self.alpha += (target - self.alpha) * min(1.0, dt * BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.THINKING],
                min(1.0, dt * BLEND_RATE),
            )
            self.orbit_pos = (self.orbit_pos + ORBIT_SPEED * dt) % 1.0

        elif s == ConvState.SPEAKING:
            target = 0.3 + 0.7 * self.energy
            self.alpha += (target - self.alpha) * min(1.0, dt * BLEND_RATE)
            self.color = _lerp_color(
                self.color,
                CONV_COLORS[ConvState.SPEAKING],
                min(1.0, dt * BLEND_RATE),
            )

        elif s == ConvState.ERROR:
            if t < 0.1:
                self.alpha = 1.0
                self.color = CONV_COLORS[ConvState.ERROR]
            elif t < 0.8:
                self.alpha = math.exp(-(t - 0.1) * 5.0)
            else:
                self.set_state(ConvState.IDLE)

        elif s == ConvState.DONE:
            self.alpha = _clamp(self.alpha - dt * 2.0, 0.0, 1.0)
            if self.alpha < 0.01:
                self.set_state(ConvState.IDLE)

        # LED mirrors border colour at reduced brightness
        if self.alpha > 0.01:
            led_scale = self.alpha * 0.16
            self.led_color = _scale_color(self.color, led_scale)
        else:
            self.led_color = (0, 0, 0)

    # ── Render into pixel buffer ────────────────────────────────────

    def render(self, buf: list[tuple[int, int, int]]) -> None:
        """Draw the border frame onto the 320×240 buffer (call before eyes)."""
        if self.alpha < 0.01 and self.state != ConvState.ATTENTION:
            return

        W, H = SCREEN_W, SCREEN_H

        # Attention: special inward-sweep animation
        if self.state == ConvState.ATTENTION and self.timer < 0.4:
            self._render_attention(buf, W, H)
            return

        # Regular frame + glow
        depth = FRAME_W + GLOW_W
        for y in range(H):
            dv = min(y, H - 1 - y)
            row = y * W
            if dv >= depth:
                # only left/right strips
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

        # Orbit dots (thinking)
        if self.state == ConvState.THINKING and self.alpha > 0.01:
            self._render_dots(buf)

    def _frame_px(self, buf: list, idx: int, x: int, y: int) -> None:
        d = _inner_sdf(x + 0.5, y + 0.5)
        if d > 0:
            a = self.alpha
        elif d > -GLOW_W:
            t = (d + GLOW_W) / GLOW_W
            a = self.alpha * t * t
        else:
            return
        if a > 0.01:
            _blend(buf, idx, self.color, a)

    def _render_attention(self, buf: list, W: int, H: int) -> None:
        progress = self.timer / 0.4
        sweep = ATTENTION_DEPTH * progress
        col = CONV_COLORS[ConvState.ATTENTION]
        fade_global = 1.0 - progress * 0.5
        limit = int(sweep) + 1
        for y in range(H):
            dv = min(y, H - 1 - y)
            if dv > limit:
                row = y * W
                for x in range(min(limit, W)):
                    self._attn_px(buf, row + x, x, sweep, col, fade_global)
                for x in range(max(0, W - limit), W):
                    self._attn_px(
                        buf, row + x, min(x, W - 1 - x), sweep, col, fade_global
                    )
                continue
            row = y * W
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
        for i in range(ORBIT_DOTS):
            pos = (self.orbit_pos - i * ORBIT_SPACING) % 1.0
            dx, dy = _perimeter_xy(pos)
            bri = brightnesses[i] if i < len(brightnesses) else 0.3
            c = _scale_color(dot_col, bri)
            r = ORBIT_DOT_R
            x0, x1 = max(0, int(dx - r - 1)), min(SCREEN_W, int(dx + r + 2))
            y0, y1 = max(0, int(dy - r - 1)), min(SCREEN_H, int(dy + r + 2))
            for y in range(y0, y1):
                row = y * SCREEN_W
                for x in range(x0, x1):
                    d = math.sqrt((x + 0.5 - dx) ** 2 + (y + 0.5 - dy) ** 2)
                    if d < r:
                        a = min(1.0, (1.0 - (d / r) ** 2) * 2.5)
                        if a > 0.01:
                            _blend(buf, row + x, c, a)

    # ── Button rendering ────────────────────────────────────────────

    def render_buttons(self, buf: list[tuple[int, int, int]]) -> None:
        """Draw PTT and Cancel buttons (call after eyes/mouth)."""
        self._draw_button_ptt(buf)
        self._draw_button_cancel(buf)

    def _draw_button_ptt(self, buf: list) -> None:
        cx, cy, r = PTT_CX, PTT_CY, BTN_RADIUS
        # Active state uses the conv-state colour
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

        # Background circle + border
        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                d = math.sqrt((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2)
                if d < r - 1:
                    _blend(buf, row + x, bg_col, bg_alpha)
                elif d < r + 0.5:
                    ba = max(0.0, 1.0 - abs(d - r + 0.5))
                    _blend(buf, row + x, border_col, ba * 0.8)

        # Icon: concentric arcs (sound wave emanation)
        dot_r = 2.5
        arc_radii = (6.0, 10.0, 14.0)
        arc_thick = 1.3
        # Arcs face right: cover ±70 degrees
        arc_min = -70.0 * math.pi / 180.0
        arc_max = 70.0 * math.pi / 180.0

        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5 - cx, y + 0.5 - cy
                dist = math.sqrt(px * px + py * py)
                # Central dot
                if dist < dot_r:
                    a = 1.0 - max(0, (dist - dot_r + 1.0))
                    _blend(buf, row + x, icon_col, min(1.0, a))
                    continue
                # Arcs
                angle = math.atan2(py, px)
                if arc_min <= angle <= arc_max:
                    for ar in arc_radii:
                        ad = abs(dist - ar)
                        if ad < arc_thick:
                            a = 1.0 - ad / arc_thick
                            # Ripple animation when active
                            if self.ptt_active:
                                phase = (self.timer * 3.0 - ar / 14.0) % 1.0
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

        # Background circle + border
        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                d = math.sqrt((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2)
                if d < r - 1:
                    _blend(buf, row + x, bg_col, bg_alpha)
                elif d < r + 0.5:
                    ba = max(0.0, 1.0 - abs(d - r + 0.5))
                    _blend(buf, row + x, border_col, ba * 0.8)

        # Icon: X mark
        arm = r * 0.45  # half-length of each arm
        thick = 2.0
        for y in range(y0, y1):
            row = y * SCREEN_W
            for x in range(x0, x1):
                px, py = x + 0.5 - cx, y + 0.5 - cy
                # Two diagonal lines: y=x and y=-x
                d1 = abs(px - py) / 1.414  # distance to y=x line
                d2 = abs(px + py) / 1.414  # distance to y=-x line
                in_bounds = abs(px) < arm and abs(py) < arm
                if not in_bounds:
                    continue
                d = min(d1, d2)
                if d < thick:
                    a = 1.0 - d / thick
                    _blend(buf, row + x, icon_col, a * 0.9)
