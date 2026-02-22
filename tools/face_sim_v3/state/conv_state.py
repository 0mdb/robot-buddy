"""Conversation state machine (spec §12).

Pure state management — no rendering (that lives in render/border.py).
Auto-transitions: ATTENTION→LISTENING, ERROR→fallback, DONE→IDLE.
"""

from __future__ import annotations

from tools.face_sim_v3.state.constants import (
    ATTENTION_DURATION,
    DONE_FADE_DURATION,
    ERROR_TOTAL_DURATION,
    ConvState,
)


class ConvStateMachine:
    """Conversation state machine with auto-transitions."""

    def __init__(self) -> None:
        self.state: ConvState = ConvState.IDLE
        self.prev_state: ConvState = ConvState.IDLE
        self.timer: float = 0.0
        self.session_active: bool = False
        self.ptt_held: bool = False

    def set_state(self, new_state: ConvState) -> None:
        if new_state == self.state:
            return
        self.prev_state = self.state
        self.state = new_state
        self.timer = 0.0

        # Track session lifecycle
        if new_state == ConvState.ATTENTION:
            self.session_active = True
        elif new_state == ConvState.IDLE:
            self.session_active = False

    def update(self, dt: float) -> None:
        """Advance timer and handle auto-transitions."""
        self.timer += dt

        if self.state == ConvState.ATTENTION:
            if self.timer >= ATTENTION_DURATION:
                if self.ptt_held:
                    self.set_state(ConvState.PTT)
                else:
                    self.set_state(ConvState.LISTENING)

        elif self.state == ConvState.ERROR:
            if self.timer >= ERROR_TOTAL_DURATION:
                # Return to LISTENING if session active, else IDLE
                if self.session_active:
                    self.set_state(ConvState.LISTENING)
                else:
                    self.set_state(ConvState.IDLE)

        elif self.state == ConvState.DONE:
            if self.timer >= DONE_FADE_DURATION:
                self.set_state(ConvState.IDLE)
