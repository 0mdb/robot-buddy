"""Debug HUD overlay — renders state info below the canvas.

Shows mood, conv state, flags, gaze, gestures, timing, key help.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from tools.face_sim_v3.render.border import BorderRenderer
    from tools.face_sim_v3.state.conv_state import ConvStateMachine
    from tools.face_sim_v3.state.face_state import FaceState
    from tools.face_sim_v3.state.guardrails import Guardrails
    from tools.face_sim_v3.state.mood_sequencer import MoodSequencer

from tools.face_sim_v3.state.constants import SystemMode


class DebugOverlay:
    """Renders debug HUD using pygame font below the main canvas."""

    def __init__(self) -> None:
        self.font: pygame.font.Font | None = None
        self.frame_time_ms: float = 0.0

    def init_font(self) -> None:
        self.font = pygame.font.SysFont("monospace", 14)

    def render(
        self,
        surface: pygame.Surface,
        y_offset: int,
        fs: FaceState,
        conv_sm: ConvStateMachine,
        border: BorderRenderer,
        sequencer: MoodSequencer,
        guardrails: Guardrails,
    ) -> None:
        if self.font is None:
            self.init_font()
        font = self.font
        assert font is not None

        y = y_offset

        # Line 1: Mood + intensity + sequencer phase
        mood_name = fs.mood.name
        seq_phase = sequencer.phase.name
        seq_timer = sequencer.timer
        line1 = (
            f"Mood: {mood_name}({fs.mood})  "
            f"Intensity: {fs.expression_intensity:.2f}  "
            f"Seq: {seq_phase} ({seq_timer:.3f}s)"
        )
        self._draw(surface, font, line1, (160, 200, 255), 10, y)
        y += 18

        # Line 2: Conv state + border
        conv_name = conv_sm.state.name
        border_alpha = border.alpha
        br, bg, bb = border.color
        lr, lg, lb = border.led_color
        line2 = (
            f"Conv: {conv_name}  "
            f"Border: a={border_alpha:.2f} c=({br},{bg},{bb})  "
            f"LED: ({lr},{lg},{lb})"
        )
        conv_col = border.color if border.alpha > 0.1 else (100, 100, 110)
        self._draw(surface, font, line2, conv_col, 10, y)
        y += 18

        # Line 3: Flags
        idle_s = "ON" if fs.anim.idle else "off"
        blink_s = "ON" if fs.anim.autoblink else "off"
        style_s = "SOLID" if fs.solid_eye else "PUPIL"
        mouth_s = "ON" if fs.show_mouth else "off"
        glow_s = "ON" if fs.fx.edge_glow else "off"
        sparkle_s = "ON" if fs.fx.sparkle else "off"
        aftglow_s = "ON" if fs.fx.afterglow else "off"
        line3 = (
            f"Idle:{idle_s} Blink:{blink_s} Style:{style_s} "
            f"Mouth:{mouth_s} Glow:{glow_s} Sparkle:{sparkle_s} "
            f"Afterglow:{aftglow_s}"
        )
        self._draw(surface, font, line3, (130, 140, 150), 10, y)
        y += 18

        # Line 4: Gaze + talking + brightness
        gx = fs.eye_l.gaze_x
        gy = fs.eye_l.gaze_y
        talk_s = f"TALK({fs.talking_energy:.1f})" if fs.talking else "off"
        line4 = (
            f"Gaze: ({gx:.1f},{gy:.1f})  "
            f"Talk: {talk_s}  "
            f"Bright: {fs.brightness:.1f}  "
            f"Frame: {self.frame_time_ms:.1f}ms"
        )
        self._draw(surface, font, line4, (120, 130, 140), 10, y)
        y += 18

        # Line 5: Active gesture + guardrail info
        gesture_s = "none"
        if fs.active_gesture != 0xFF:
            from tools.face_sim_v3.state.constants import GestureId

            try:
                gesture_s = GestureId(fs.active_gesture).name
            except ValueError:
                gesture_s = f"?{fs.active_gesture}"
        sys_name = fs.system.mode.name if fs.system.mode != SystemMode.NONE else ""
        line5 = f"Gesture: {gesture_s}"
        if sys_name:
            line5 += f"  |  SYSTEM: {sys_name}"
        self._draw(surface, font, line5, (120, 130, 140), 10, y)
        y += 20

        # Key help lines
        help_lines = [
            "1-0,-,=,BS:moods  SPACE:blink  C L W E H X Z R N D J U P Y O A V . ,:gestures",
            "I:idle B:blink S:style M:mouth G:glow K:sparkle F:afterglow T:talk [/]:energy",
            "F7:attn F8:listen F9:ptt F10:think F11:speak F12:error  Sh+F7:done Sh+F8:idle  TAB:walk",
            "F1:boot F2:error F3:battery F4:update F5:shutdown F6:clear  +/-:brightness  Q/Esc:quit",
            "Sh+1:birthday Sh+2:halloween Sh+3:christmas Sh+4:newyear Sh+`:off",
        ]
        for line in help_lines:
            self._draw(surface, font, line, (80, 85, 95), 10, y)
            y += 16

    @staticmethod
    def _draw(
        surface: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        x: int,
        y: int,
    ) -> None:
        surf = font.render(text, True, color)
        surface.blit(surf, (x, y))
