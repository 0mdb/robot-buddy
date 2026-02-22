"""Command bus — all state changes flow through protocol-equivalent commands.

Matches MCU protocol command IDs (spec §9):
  SET_STATE  0x20 — mood, intensity, gaze, brightness
  GESTURE    0x21 — gesture trigger with optional duration
  SET_SYSTEM 0x22 — system mode overlay
  SET_TALKING 0x23 — talking flag + energy level
  SET_FLAGS  0x24 — feature flag bitmask
  SET_CONV   0x25 — conversation state transition

No direct FaceState mutation from keyboard — all inputs go through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.face_sim_v3.state.constants import ConvState, GestureId, Mood, SystemMode
from tools.face_sim_v3.state.face_state import (
    FaceState,
    face_set_expression_intensity,
    face_set_flags,
    face_set_gaze,
    face_set_mood,
    face_set_system_mode,
    face_trigger_gesture,
)


# ── Command types ────────────────────────────────────────────────────


@dataclass
class SetStateCmd:
    """SET_STATE (0x20): mood + intensity + gaze + brightness."""

    mood: Mood | None = None
    intensity: float | None = None
    gaze_x: float | None = None
    gaze_y: float | None = None
    brightness: float | None = None


@dataclass
class GestureCmd:
    """GESTURE (0x21): trigger gesture with optional duration."""

    gesture_id: GestureId
    duration_ms: int = 0


@dataclass
class SetSystemCmd:
    """SET_SYSTEM (0x22): system mode overlay."""

    mode: SystemMode
    param: float = 0.0


@dataclass
class SetTalkingCmd:
    """SET_TALKING (0x23): talking flag + energy."""

    talking: bool
    energy: float = 0.0


@dataclass
class SetFlagsCmd:
    """SET_FLAGS (0x24): feature flag bitmask."""

    flags: int


@dataclass
class SetConvStateCmd:
    """SET_CONV_STATE (0x25): conversation state transition."""

    conv_state: ConvState


Command = (
    SetStateCmd
    | GestureCmd
    | SetSystemCmd
    | SetTalkingCmd
    | SetFlagsCmd
    | SetConvStateCmd
)


# ── Command Bus ──────────────────────────────────────────────────────


@dataclass
class CommandBus:
    """Queues and dispatches commands per frame.

    Last-value-wins semantics per command type (matches MCU behavior).
    """

    _queue: list[Command] = field(default_factory=list)

    def push(self, cmd: Command) -> None:
        """Queue a command for dispatch on the next frame."""
        self._queue.append(cmd)

    def dispatch(self, fs: FaceState, conv_sm: object | None = None) -> None:
        """Apply all queued commands to FaceState (and optionally ConvStateMachine).

        Commands are applied in order; for duplicate types, last one wins
        naturally since later writes overwrite earlier ones.

        conv_sm: optional ConvStateMachine instance (typed as object to
        avoid circular import — will be ConvStateMachine at runtime).
        """
        for cmd in self._queue:
            if isinstance(cmd, SetStateCmd):
                _apply_set_state(fs, cmd)
            elif isinstance(cmd, GestureCmd):
                _apply_gesture(fs, cmd)
            elif isinstance(cmd, SetSystemCmd):
                _apply_system(fs, cmd)
            elif isinstance(cmd, SetTalkingCmd):
                _apply_talking(fs, cmd)
            elif isinstance(cmd, SetFlagsCmd):
                _apply_flags(fs, cmd)
            elif isinstance(cmd, SetConvStateCmd):
                _apply_conv_state(cmd, conv_sm)
        self._queue.clear()

    @property
    def pending(self) -> int:
        return len(self._queue)


# ── Command application ─────────────────────────────────────────────


def _apply_set_state(fs: FaceState, cmd: SetStateCmd) -> None:
    if cmd.mood is not None:
        face_set_mood(fs, cmd.mood)
    if cmd.intensity is not None:
        face_set_expression_intensity(fs, cmd.intensity)
    if cmd.gaze_x is not None and cmd.gaze_y is not None:
        face_set_gaze(fs, cmd.gaze_x, cmd.gaze_y)
    if cmd.brightness is not None:
        fs.brightness = max(0.0, min(1.0, cmd.brightness))


def _apply_gesture(fs: FaceState, cmd: GestureCmd) -> None:
    face_trigger_gesture(fs, cmd.gesture_id, cmd.duration_ms)


def _apply_system(fs: FaceState, cmd: SetSystemCmd) -> None:
    face_set_system_mode(fs, cmd.mode, cmd.param)


def _apply_talking(fs: FaceState, cmd: SetTalkingCmd) -> None:
    fs.talking = cmd.talking
    fs.talking_energy = max(0.0, min(1.0, cmd.energy))


def _apply_flags(fs: FaceState, cmd: SetFlagsCmd) -> None:
    face_set_flags(fs, cmd.flags)


def _apply_conv_state(cmd: SetConvStateCmd, conv_sm: object | None) -> None:
    if conv_sm is not None and hasattr(conv_sm, "set_state"):
        conv_sm.set_state(cmd.conv_state)  # type: ignore[attr-defined]
