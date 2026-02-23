"""Keyboard handler — translates pygame key events to Command objects.

All state changes go through the CommandBus (never direct FaceState mutation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from tools.face_sim_v3.input.command_bus import (
    CommandBus,
    GestureCmd,
    SetConvStateCmd,
    SetFlagsCmd,
    SetStateCmd,
    SetSystemCmd,
    SetTalkingCmd,
)
from tools.face_sim_v3.state.constants import (
    ConvState,
    GestureId,
    MAX_GAZE,
    Mood,
    SystemMode,
)

if TYPE_CHECKING:
    from tools.face_sim_v3.state.face_state import FaceState

# Conversation walkthrough sequence (Tab key)
_WALKTHROUGH = [
    ConvState.IDLE,
    ConvState.ATTENTION,
    ConvState.LISTENING,
    ConvState.THINKING,
    ConvState.SPEAKING,
    ConvState.DONE,
    ConvState.IDLE,
]


class KeyboardHandler:
    """Translates pygame events into CommandBus commands."""

    def __init__(self, bus: CommandBus) -> None:
        self.bus = bus
        self.manual_gaze: bool = False
        self._walkthrough_idx: int = 0
        self._quit_requested: bool = False

    @property
    def quit_requested(self) -> bool:
        return self._quit_requested

    def handle_event(self, event: pygame.event.Event, fs: FaceState) -> None:
        """Process a single pygame KEYDOWN event."""
        if event.type != pygame.KEYDOWN:
            return

        key = event.key
        shift = bool(event.mod & pygame.KMOD_SHIFT)

        # ── Quit ─────────────────────────────────────────────
        if key in (pygame.K_q, pygame.K_ESCAPE):
            self._quit_requested = True
            return

        # ── Blink ────────────────────────────────────────────
        if key == pygame.K_SPACE:
            self.bus.push(GestureCmd(GestureId.BLINK))
            return

        # ── Holiday modes (Shift + 1-4, Shift+` to disable) ──
        if shift:
            holiday = _key_to_holiday(key)
            if holiday is not None:
                fs.holiday_mode = holiday
                fs._holiday_timer = 0.0  # Reset periodic gesture timer
                return

        # ── Moods (routed through mood sequencer) ────────────
        mood = _key_to_mood(key, shift)
        if mood is not None:
            self.bus.push(SetStateCmd(mood=mood, intensity=1.0))
            return

        # ── Gestures ─────────────────────────────────────────
        gesture = _key_to_gesture(key)
        if gesture is not None:
            self.bus.push(GestureCmd(gesture))
            return

        # ── Toggles (via flag bitmask) ───────────────────────
        flag_toggle = _key_to_flag_toggle(key, fs)
        if flag_toggle is not None:
            self.bus.push(flag_toggle)
            return

        # ── Talking ──────────────────────────────────────────
        if key == pygame.K_t:
            if fs.talking:
                self.bus.push(SetTalkingCmd(talking=False, energy=0.0))
            else:
                self.bus.push(SetTalkingCmd(talking=True, energy=0.5))
            return

        # ── Talking energy ───────────────────────────────────
        if key == pygame.K_LEFTBRACKET:
            energy = max(0.0, fs.talking_energy - 0.1)
            self.bus.push(SetTalkingCmd(talking=fs.talking, energy=energy))
            return
        if key == pygame.K_RIGHTBRACKET:
            energy = min(1.0, fs.talking_energy + 0.1)
            self.bus.push(SetTalkingCmd(talking=fs.talking, energy=energy))
            return

        # ── Brightness ───────────────────────────────────────
        if key == pygame.K_PLUS or (key == pygame.K_EQUALS and shift):
            self.bus.push(SetStateCmd(brightness=min(1.0, fs.brightness + 0.1)))
            return
        if key == pygame.K_MINUS and not shift:
            # Only if not used for SILLY mood
            pass  # Handled in mood section

        # ── Conversation states ──────────────────────────────
        conv = _key_to_conv_state(key, shift)
        if conv is not None:
            self.bus.push(SetConvStateCmd(conv))
            self._walkthrough_idx = 0
            return

        # ── Conversation walkthrough (Tab) ───────────────────
        if key == pygame.K_TAB:
            self._walkthrough_idx = (self._walkthrough_idx + 1) % len(_WALKTHROUGH)
            state = _WALKTHROUGH[self._walkthrough_idx]
            self.bus.push(SetConvStateCmd(state))
            # Enable talking during SPEAKING
            if state == ConvState.SPEAKING:
                self.bus.push(SetTalkingCmd(talking=True, energy=0.5))
            elif state in (ConvState.IDLE, ConvState.DONE):
                self.bus.push(SetTalkingCmd(talking=False, energy=0.0))
            return

        # ── System modes ─────────────────────────────────────
        sys_mode = _key_to_system(key)
        if sys_mode is not None:
            self.bus.push(SetSystemCmd(sys_mode[0], sys_mode[1]))
            return

    def handle_held_keys(self, keys: pygame.key.ScancodeWrapper) -> None:
        """Handle held arrow keys for gaze control."""
        gx, gy = 0.0, 0.0
        if keys[pygame.K_LEFT]:
            gx -= MAX_GAZE
        if keys[pygame.K_RIGHT]:
            gx += MAX_GAZE
        if keys[pygame.K_UP]:
            gy -= MAX_GAZE * 0.7
        if keys[pygame.K_DOWN]:
            gy += MAX_GAZE * 0.7

        if gx != 0.0 or gy != 0.0:
            self.bus.push(SetStateCmd(gaze_x=gx, gaze_y=gy))
            self.manual_gaze = True
        elif self.manual_gaze:
            self.bus.push(SetStateCmd(gaze_x=0.0, gaze_y=0.0))
            self.manual_gaze = False


# ── Key mapping tables ───────────────────────────────────────────────


def _key_to_mood(key: int, shift: bool) -> Mood | None:
    if shift:
        return None
    return {
        pygame.K_1: Mood.NEUTRAL,
        pygame.K_2: Mood.HAPPY,
        pygame.K_3: Mood.EXCITED,
        pygame.K_4: Mood.CURIOUS,
        pygame.K_5: Mood.SAD,
        pygame.K_6: Mood.SCARED,
        pygame.K_7: Mood.ANGRY,
        pygame.K_8: Mood.SURPRISED,
        pygame.K_9: Mood.SLEEPY,
        pygame.K_0: Mood.LOVE,
        pygame.K_MINUS: Mood.SILLY,
        pygame.K_EQUALS: Mood.THINKING,
        pygame.K_BACKSPACE: Mood.CONFUSED,
    }.get(key)


def _key_to_gesture(key: int) -> GestureId | None:
    return {
        pygame.K_c: GestureId.CONFUSED,
        pygame.K_l: GestureId.LAUGH,
        pygame.K_w: GestureId.WINK_L,
        pygame.K_e: GestureId.WINK_R,
        pygame.K_h: GestureId.HEART,
        pygame.K_x: GestureId.X_EYES,
        pygame.K_z: GestureId.SLEEPY,
        pygame.K_r: GestureId.RAGE,
        pygame.K_n: GestureId.NOD,
        pygame.K_d: GestureId.HEADSHAKE,
        pygame.K_j: GestureId.WIGGLE,
        pygame.K_u: GestureId.SURPRISE,
        pygame.K_p: GestureId.PEEK_A_BOO,
        pygame.K_y: GestureId.SHY,
        pygame.K_o: GestureId.EYE_ROLL,
        pygame.K_a: GestureId.DIZZY,
        pygame.K_v: GestureId.CELEBRATE,
        pygame.K_PERIOD: GestureId.STARTLE_RELIEF,
        pygame.K_COMMA: GestureId.THINKING_HARD,
    }.get(key)


def _key_to_flag_toggle(key: int, fs: FaceState) -> SetFlagsCmd | None:
    """Toggle a single flag and return a SetFlagsCmd, or None."""
    from tools.face_sim_v3.state.constants import (
        FLAG_AFTERGLOW,
        FLAG_AUTOBLINK,
        FLAG_EDGE_GLOW,
        FLAG_IDLE_WANDER,
        FLAG_SHOW_MOUTH,
        FLAG_SOLID_EYE,
        FLAG_SPARKLE,
    )
    from tools.face_sim_v3.state.face_state import face_get_flags

    flag_map = {
        pygame.K_i: FLAG_IDLE_WANDER,
        pygame.K_b: FLAG_AUTOBLINK,
        pygame.K_s: FLAG_SOLID_EYE,
        pygame.K_m: FLAG_SHOW_MOUTH,
        pygame.K_g: FLAG_EDGE_GLOW,
        pygame.K_k: FLAG_SPARKLE,
        pygame.K_f: FLAG_AFTERGLOW,
    }
    flag = flag_map.get(key)
    if flag is None:
        return None
    current = face_get_flags(fs)
    return SetFlagsCmd(current ^ flag)


def _key_to_conv_state(key: int, shift: bool) -> ConvState | None:
    if key == pygame.K_F7:
        return ConvState.DONE if shift else ConvState.ATTENTION
    if key == pygame.K_F8:
        return ConvState.IDLE if shift else ConvState.LISTENING
    return {
        pygame.K_F9: ConvState.PTT,
        pygame.K_F10: ConvState.THINKING,
        pygame.K_F11: ConvState.SPEAKING,
        pygame.K_F12: ConvState.ERROR,
    }.get(key)


def _key_to_holiday(key: int) -> int | None:
    """Map Shift+number keys to HolidayMode values."""
    from tools.face_sim_v3.state.constants import HolidayMode

    return {
        pygame.K_1: HolidayMode.BIRTHDAY,
        pygame.K_2: HolidayMode.HALLOWEEN,
        pygame.K_3: HolidayMode.CHRISTMAS,
        pygame.K_4: HolidayMode.NEW_YEAR,
        pygame.K_BACKQUOTE: HolidayMode.NONE,
    }.get(key)


def _key_to_system(key: int) -> tuple[SystemMode, float] | None:
    return {
        pygame.K_F1: (SystemMode.BOOTING, 0.0),
        pygame.K_F2: (SystemMode.ERROR_DISPLAY, 0.0),
        pygame.K_F3: (SystemMode.LOW_BATTERY, 0.1),
        pygame.K_F4: (SystemMode.UPDATING, 0.0),
        pygame.K_F5: (SystemMode.SHUTTING_DOWN, 0.0),
        pygame.K_F6: (SystemMode.NONE, 0.0),
    }.get(key)
