"""Conversation state machine (spec §12).

Pure state management — no rendering (that lives in render/border.py).
Auto-transitions: ATTENTION→LISTENING, ERROR→fallback, DONE→IDLE.
"""

from __future__ import annotations

import random

from tools.face_sim_v3.state.constants import (
    ATTENTION_DURATION,
    BACKCHANNEL_INTEREST_MAX_SCALE,
    BACKCHANNEL_INTEREST_ONSET,
    BACKCHANNEL_INTEREST_RAMP,
    BACKCHANNEL_NOD_MIN,
    BACKCHANNEL_NOD_RANGE,
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

        # Backchannel state
        self.next_nod: float = (
            BACKCHANNEL_NOD_MIN + random.random() * BACKCHANNEL_NOD_RANGE
        )
        self.nod_pending: bool = False
        self.interest_scale: float = 1.0

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

        # Reset backchannel on state change
        self.next_nod = BACKCHANNEL_NOD_MIN + random.random() * BACKCHANNEL_NOD_RANGE
        self.nod_pending = False
        self.interest_scale = 1.0

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

        # Backchannel during LISTENING
        if self.state == ConvState.LISTENING:
            # Periodic NOD
            if self.timer >= self.next_nod:
                self.nod_pending = True
                self.next_nod = (
                    self.timer
                    + BACKCHANNEL_NOD_MIN
                    + random.random() * BACKCHANNEL_NOD_RANGE
                )

            # Interest escalation after prolonged listening
            if self.timer > BACKCHANNEL_INTEREST_ONSET:
                t = (
                    self.timer - BACKCHANNEL_INTEREST_ONSET
                ) / BACKCHANNEL_INTEREST_RAMP
                t = min(1.0, t)
                self.interest_scale = 1.0 + (BACKCHANNEL_INTEREST_MAX_SCALE - 1.0) * t
