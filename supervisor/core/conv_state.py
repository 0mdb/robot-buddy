"""Conversation state tracker for the supervisor tick loop.

Tracks the current conversation phase and provides per-state overrides
for gaze, flags, and mood hints. Auto-transitions handle timed phases
(ATTENTION→LISTENING, ERROR→fallback, DONE→IDLE). Backchannel NODs
fire during prolonged LISTENING.

Port of tools/face_sim_v3/state/conv_state.py (canonical sim source).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from supervisor.devices.protocol import (
    FACE_FLAG_AUTOBLINK,
    FACE_FLAG_EDGE_GLOW,
    FACE_FLAG_IDLE_WANDER,
    FACE_FLAG_SHOW_MOUTH,
    FACE_FLAG_SOLID_EYE,
    FACE_FLAG_SPARKLE,
    FaceConvState,
    FaceMood,
)

# ── Timing constants (match sim constants.py) ────────────────────────

ATTENTION_DURATION_MS = 400.0
ERROR_TOTAL_DURATION_MS = 800.0
DONE_FADE_DURATION_MS = 500.0

# Backchannel
BACKCHANNEL_NOD_MIN_MS = 3000.0
BACKCHANNEL_NOD_RANGE_MS = 2000.0
BACKCHANNEL_INTEREST_ONSET_MS = 10000.0
BACKCHANNEL_INTEREST_MAX_SCALE = 1.05
BACKCHANNEL_INTEREST_RAMP_MS = 20000.0

# Error micro-aversion
ERROR_AVERSION_DURATION_MS = 200.0
ERROR_AVERSION_GAZE_X = -0.3  # Normalized

# ── Per-state tables (match sim constants.py) ─────────────────────────

# Gaze overrides: (gx, gy) normalized or None for no override
_CONV_GAZE: dict[FaceConvState, tuple[float, float] | None] = {
    FaceConvState.IDLE: None,
    FaceConvState.ATTENTION: (0.0, 0.0),
    FaceConvState.LISTENING: (0.0, 0.0),
    FaceConvState.PTT: (0.0, 0.0),
    FaceConvState.THINKING: (0.5, -0.3),
    FaceConvState.SPEAKING: (0.0, 0.0),
    FaceConvState.ERROR: None,  # Micro-aversion handled separately
    FaceConvState.DONE: None,
}

# Mood hints: (mood_id, intensity) or None
_CONV_MOOD_HINTS: dict[FaceConvState, tuple[int, float] | None] = {
    FaceConvState.IDLE: None,
    FaceConvState.ATTENTION: None,
    FaceConvState.LISTENING: (int(FaceMood.NEUTRAL), 0.3),
    FaceConvState.PTT: (int(FaceMood.NEUTRAL), 0.3),
    FaceConvState.THINKING: (int(FaceMood.THINKING), 0.5),
    FaceConvState.SPEAKING: None,
    FaceConvState.ERROR: None,
    FaceConvState.DONE: None,
}

# Flag overrides per state (-1 = no change)
_FLAGS_DEFAULT = (
    FACE_FLAG_IDLE_WANDER
    | FACE_FLAG_AUTOBLINK
    | FACE_FLAG_SOLID_EYE
    | FACE_FLAG_SHOW_MOUTH
    | FACE_FLAG_EDGE_GLOW
    | FACE_FLAG_SPARKLE
)
_FLAGS_NO_WANDER = (
    FACE_FLAG_AUTOBLINK
    | FACE_FLAG_SOLID_EYE
    | FACE_FLAG_SHOW_MOUTH
    | FACE_FLAG_EDGE_GLOW
    | FACE_FLAG_SPARKLE
)
_FLAGS_NO_WANDER_NO_SPARKLE = (
    FACE_FLAG_AUTOBLINK
    | FACE_FLAG_SOLID_EYE
    | FACE_FLAG_SHOW_MOUTH
    | FACE_FLAG_EDGE_GLOW
)

_CONV_FLAGS: dict[FaceConvState, int] = {
    FaceConvState.IDLE: _FLAGS_DEFAULT,
    FaceConvState.ATTENTION: _FLAGS_NO_WANDER,
    FaceConvState.LISTENING: _FLAGS_NO_WANDER,
    FaceConvState.PTT: _FLAGS_NO_WANDER,
    FaceConvState.THINKING: _FLAGS_NO_WANDER_NO_SPARKLE,
    FaceConvState.SPEAKING: _FLAGS_NO_WANDER,
    FaceConvState.ERROR: -1,  # No change
    FaceConvState.DONE: _FLAGS_DEFAULT,
}

# Gaze scale factor (SET_STATE gaze is ±127 i8 mapped to ±MAX_GAZE)
MAX_GAZE = 12.0


# ── ConvStateTracker ──────────────────────────────────────────────────


@dataclass(slots=True)
class ConvStateTracker:
    """Conversation state machine with auto-transitions and backchannel."""

    state: FaceConvState = FaceConvState.IDLE
    prev_state: FaceConvState = FaceConvState.IDLE
    timer_ms: float = 0.0
    session_active: bool = False
    ptt_held: bool = False

    # Backchannel
    next_nod_ms: float = field(
        default_factory=lambda: (
            BACKCHANNEL_NOD_MIN_MS + random.random() * BACKCHANNEL_NOD_RANGE_MS
        )
    )
    nod_pending: bool = False
    interest_scale: float = 1.0

    # Transition detection (consumed by tick_loop each tick)
    _changed: bool = False

    def set_state(self, new_state: FaceConvState) -> None:
        """Transition to a new conversation state."""
        if new_state == self.state:
            return
        self.prev_state = self.state
        self.state = new_state
        self.timer_ms = 0.0
        self._changed = True

        # Track session lifecycle
        if new_state == FaceConvState.ATTENTION:
            self.session_active = True
        elif new_state == FaceConvState.IDLE:
            self.session_active = False

        # Reset backchannel on any state change
        self.next_nod_ms = (
            BACKCHANNEL_NOD_MIN_MS + random.random() * BACKCHANNEL_NOD_RANGE_MS
        )
        self.nod_pending = False
        self.interest_scale = 1.0

    def consume_changed(self) -> bool:
        """Return True once per state transition (then resets)."""
        if self._changed:
            self._changed = False
            return True
        return False

    def update(self, dt_ms: float) -> None:
        """Advance timer and handle auto-transitions."""
        self.timer_ms += dt_ms

        if self.state == FaceConvState.ATTENTION:
            if self.timer_ms >= ATTENTION_DURATION_MS:
                if self.ptt_held:
                    self.set_state(FaceConvState.PTT)
                else:
                    self.set_state(FaceConvState.LISTENING)

        elif self.state == FaceConvState.ERROR:
            if self.timer_ms >= ERROR_TOTAL_DURATION_MS:
                if self.session_active:
                    self.set_state(FaceConvState.LISTENING)
                else:
                    self.set_state(FaceConvState.IDLE)

        elif self.state == FaceConvState.DONE:
            if self.timer_ms >= DONE_FADE_DURATION_MS:
                self.set_state(FaceConvState.IDLE)

        # Backchannel during LISTENING
        if self.state == FaceConvState.LISTENING:
            # Periodic NOD
            if self.timer_ms >= self.next_nod_ms:
                self.nod_pending = True
                self.next_nod_ms = (
                    self.timer_ms
                    + BACKCHANNEL_NOD_MIN_MS
                    + random.random() * BACKCHANNEL_NOD_RANGE_MS
                )

            # Interest escalation after prolonged listening
            if self.timer_ms > BACKCHANNEL_INTEREST_ONSET_MS:
                t = (self.timer_ms - BACKCHANNEL_INTEREST_ONSET_MS) / max(
                    1.0, BACKCHANNEL_INTEREST_RAMP_MS
                )
                t = min(1.0, t)
                self.interest_scale = 1.0 + (BACKCHANNEL_INTEREST_MAX_SCALE - 1.0) * t

    def get_gaze_override(self) -> tuple[float, float] | None:
        """Return (gaze_x, gaze_y) normalized override, or None."""
        # Error micro-aversion during first 200ms
        if (
            self.state == FaceConvState.ERROR
            and self.timer_ms < ERROR_AVERSION_DURATION_MS
        ):
            return (ERROR_AVERSION_GAZE_X, 0.0)

        return _CONV_GAZE.get(self.state)

    def get_gaze_for_send(self) -> tuple[float, float] | None:
        """Return gaze as floats for FaceClient.send_state().

        The send_state API converts: i8 = int(float * 32).
        The MCU converts: physical_gaze = i8 / 127.0 * MAX_GAZE.
        So float = (normalized * MAX_GAZE) / MAX_GAZE * 127.0 / 32.0
                 = normalized * 127.0 / 32.0 ≈ normalized * 3.97
        """
        gaze = self.get_gaze_override()
        if gaze is None:
            return None
        scale = 127.0 / 32.0  # Convert normalized to send_state float space
        return (gaze[0] * scale, gaze[1] * scale)

    def get_flags(self) -> int:
        """Return flag bitmask for current state, or -1 for no change."""
        return _CONV_FLAGS.get(self.state, -1)

    def get_mood_hint(self) -> tuple[int, float] | None:
        """Return (mood_id, intensity) hint, or None."""
        return _CONV_MOOD_HINTS.get(self.state)

    def consume_nod(self) -> bool:
        """Return True once when a backchannel NOD should fire."""
        if self.nod_pending:
            self.nod_pending = False
            return True
        return False
