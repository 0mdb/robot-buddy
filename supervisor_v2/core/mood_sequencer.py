"""Mood transition choreography (spec §5.1.1).

4-phase sequence:
  ANTICIPATION (100ms) — trigger blink
  RAMP_DOWN    (150ms) — linear intensity current→0.0
  SWITCH       (1 tick) — apply new mood_id at intensity 0.0
  RAMP_UP      (200ms) — linear intensity 0.0→target

Total ~470ms for a full transition.

Supervisor port of tools/face_sim_v3/state/mood_sequencer.py.
Does not mutate face state directly; tick_loop reads outputs.
"""

from __future__ import annotations

import logging
from enum import IntEnum

log = logging.getLogger(__name__)

# Timing constants (match sim constants.py §5.1.1)
SEQ_ANTICIPATION_S = 0.100  # 100 ms blink
SEQ_RAMP_DOWN_S = 0.150  # 150 ms linear ramp
SEQ_RAMP_UP_S = 0.200  # 200 ms linear ramp
SEQ_MIN_HOLD_S = 0.500  # 500 ms minimum hold before next transition


class SeqPhase(IntEnum):
    IDLE = 0
    ANTICIPATION = 1
    RAMP_DOWN = 2
    SWITCH = 3
    RAMP_UP = 4


class MoodSequencer:
    """Choreographs mood transitions with blink + crossfade."""

    def __init__(self) -> None:
        self.phase: SeqPhase = SeqPhase.IDLE
        self.timer: float = 0.0
        self.mood_id: int = 0  # FaceMood.NEUTRAL
        self.intensity: float = 1.0
        self.target_mood_id: int = 0
        self.target_intensity: float = 1.0
        self.hold_timer: float = SEQ_MIN_HOLD_S  # Ready for first request
        self._queued_mood_id: int | None = None
        self._queued_intensity: float = 1.0
        self._start_intensity: float = 1.0
        self._blink_pending: bool = False
        self._changed: bool = False

    @property
    def transitioning(self) -> bool:
        """True during any non-IDLE phase."""
        return self.phase != SeqPhase.IDLE

    def consume_blink(self) -> bool:
        """Return True once when ANTICIPATION blink should fire."""
        if self._blink_pending:
            self._blink_pending = False
            return True
        return False

    def consume_changed(self) -> bool:
        """Return True once when mood/intensity changed during IDLE."""
        if self._changed:
            self._changed = False
            return True
        return False

    def request_mood(self, mood_id: int, intensity: float = 1.0) -> None:
        """Request a mood transition. Queues if busy or too soon."""
        # Same mood, same intensity: no-op
        if mood_id == self.mood_id and abs(intensity - self.target_intensity) < 0.01:
            return

        # Mid-transition: queue
        if self.phase != SeqPhase.IDLE:
            self._queued_mood_id = mood_id
            self._queued_intensity = intensity
            return

        # Too soon since last transition for a mood change: queue
        if self.hold_timer < SEQ_MIN_HOLD_S and mood_id != self.mood_id:
            self._queued_mood_id = mood_id
            self._queued_intensity = intensity
            return

        # Same mood, just intensity change: skip choreography
        if mood_id == self.mood_id:
            self.target_intensity = intensity
            return

        self._start_transition(mood_id, intensity)

    def update(self, dt: float) -> None:
        """Advance one tick. *dt* is in seconds."""
        self.hold_timer += dt

        if self.phase == SeqPhase.IDLE:
            # Handle intensity-only ramps (same mood, different target)
            if abs(self.intensity - self.target_intensity) > 0.01:
                ramp_speed = dt / SEQ_RAMP_UP_S
                if self.intensity < self.target_intensity:
                    self.intensity = min(
                        self.target_intensity,
                        self.intensity + ramp_speed,
                    )
                else:
                    self.intensity = max(
                        self.target_intensity,
                        self.intensity - ramp_speed,
                    )
                self._changed = True

            # Process queued mood
            if self._queued_mood_id is not None:
                mid = self._queued_mood_id
                inten = self._queued_intensity
                self._queued_mood_id = None
                self.request_mood(mid, inten)
            return

        self.timer += dt

        if self.phase == SeqPhase.ANTICIPATION:
            if self.timer == dt:  # First frame of phase
                self._blink_pending = True
            if self.timer >= SEQ_ANTICIPATION_S:
                self.phase = SeqPhase.RAMP_DOWN
                self.timer = 0.0

        elif self.phase == SeqPhase.RAMP_DOWN:
            progress = min(1.0, self.timer / SEQ_RAMP_DOWN_S)
            self.intensity = self._start_intensity * (1.0 - progress)
            if self.timer >= SEQ_RAMP_DOWN_S:
                self.phase = SeqPhase.SWITCH
                self.timer = 0.0

        elif self.phase == SeqPhase.SWITCH:
            self.mood_id = self.target_mood_id
            self.intensity = 0.0
            self.phase = SeqPhase.RAMP_UP
            self.timer = 0.0

        elif self.phase == SeqPhase.RAMP_UP:
            progress = min(1.0, self.timer / SEQ_RAMP_UP_S)
            self.intensity = self.target_intensity * progress
            if self.timer >= SEQ_RAMP_UP_S:
                self.intensity = self.target_intensity
                self.phase = SeqPhase.IDLE
                self.hold_timer = 0.0
                self._changed = True

                # Process queued mood
                if self._queued_mood_id is not None:
                    mid = self._queued_mood_id
                    inten = self._queued_intensity
                    self._queued_mood_id = None
                    self._start_transition(mid, inten)

    def _start_transition(self, mood_id: int, intensity: float) -> None:
        self.target_mood_id = mood_id
        self.target_intensity = intensity
        self._start_intensity = self.intensity
        self.phase = SeqPhase.ANTICIPATION
        self.timer = 0.0
