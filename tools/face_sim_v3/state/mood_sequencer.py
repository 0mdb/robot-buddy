"""Mood transition choreography (spec §5.1.1).

4-phase sequence:
  ANTICIPATION (100ms) — trigger blink
  RAMP_DOWN    (150ms) — linear intensity current→0.0
  SWITCH       (1 tick) — apply new mood_id at intensity 0.0
  RAMP_UP      (200ms) — linear intensity 0.0→target

Total ~470ms for a full transition.
"""

from __future__ import annotations

from enum import IntEnum

from tools.face_sim_v3.state.constants import (
    SEQ_ANTICIPATION_DURATION,
    SEQ_MIN_HOLD,
    SEQ_RAMP_DOWN_DURATION,
    SEQ_RAMP_UP_DURATION,
    Mood,
)
from tools.face_sim_v3.state.face_state import (
    FaceState,
    face_blink,
    face_set_expression_intensity,
    face_set_mood,
)


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
        self.current_mood: Mood = Mood.NEUTRAL
        self.current_intensity: float = 1.0
        self.target_mood: Mood = Mood.NEUTRAL
        self.target_intensity: float = 1.0
        self.hold_timer: float = 0.0
        self.queued_mood: Mood | None = None
        self.queued_intensity: float = 1.0
        self._start_intensity: float = 1.0

    def request_mood(self, mood: Mood, intensity: float = 1.0) -> None:
        """Request a mood transition. Queues if hold timer hasn't elapsed."""
        if mood == self.current_mood and abs(intensity - self.target_intensity) < 0.01:
            return

        if self.phase != SeqPhase.IDLE:
            # Mid-transition: queue for later
            self.queued_mood = mood
            self.queued_intensity = intensity
            return

        if self.hold_timer < SEQ_MIN_HOLD and mood != self.current_mood:
            # Too soon since last transition: queue
            self.queued_mood = mood
            self.queued_intensity = intensity
            return

        # Same mood, just intensity change: skip choreography
        if mood == self.current_mood:
            self.target_intensity = intensity
            return

        self._start_transition(mood, intensity)

    def _start_transition(self, mood: Mood, intensity: float) -> None:
        self.target_mood = mood
        self.target_intensity = intensity
        self._start_intensity = self.current_intensity
        self.phase = SeqPhase.ANTICIPATION
        self.timer = 0.0

    def update(self, fs: FaceState, dt: float) -> None:
        """Advance one frame. Calls face_blink/face_set_mood/face_set_expression_intensity."""
        self.hold_timer += dt

        # Handle intensity-only changes (same mood)
        if self.phase == SeqPhase.IDLE:
            if abs(self.current_intensity - self.target_intensity) > 0.01:
                # Smooth ramp toward target
                ramp_speed = dt / SEQ_RAMP_UP_DURATION
                if self.current_intensity < self.target_intensity:
                    self.current_intensity = min(
                        self.target_intensity,
                        self.current_intensity + ramp_speed,
                    )
                else:
                    self.current_intensity = max(
                        self.target_intensity,
                        self.current_intensity - ramp_speed,
                    )
                face_set_expression_intensity(fs, self.current_intensity)

            # Check for queued mood
            if self.queued_mood is not None:
                mood = self.queued_mood
                intensity = self.queued_intensity
                self.queued_mood = None
                self.request_mood(mood, intensity)
            return

        self.timer += dt

        if self.phase == SeqPhase.ANTICIPATION:
            if self.timer == dt:  # First frame of phase
                face_blink(fs)
            if self.timer >= SEQ_ANTICIPATION_DURATION:
                self.phase = SeqPhase.RAMP_DOWN
                self.timer = 0.0

        elif self.phase == SeqPhase.RAMP_DOWN:
            progress = min(1.0, self.timer / SEQ_RAMP_DOWN_DURATION)
            self.current_intensity = self._start_intensity * (1.0 - progress)
            face_set_expression_intensity(fs, self.current_intensity)
            if self.timer >= SEQ_RAMP_DOWN_DURATION:
                self.phase = SeqPhase.SWITCH
                self.timer = 0.0

        elif self.phase == SeqPhase.SWITCH:
            self.current_mood = self.target_mood
            self.current_intensity = 0.0
            face_set_mood(fs, self.current_mood)
            face_set_expression_intensity(fs, 0.0)
            self.phase = SeqPhase.RAMP_UP
            self.timer = 0.0

        elif self.phase == SeqPhase.RAMP_UP:
            progress = min(1.0, self.timer / SEQ_RAMP_UP_DURATION)
            self.current_intensity = self.target_intensity * progress
            face_set_expression_intensity(fs, self.current_intensity)
            if self.timer >= SEQ_RAMP_UP_DURATION:
                self.current_intensity = self.target_intensity
                face_set_expression_intensity(fs, self.current_intensity)
                self.phase = SeqPhase.IDLE
                self.hold_timer = 0.0

                # Check for queued mood
                if self.queued_mood is not None:
                    mood = self.queued_mood
                    intensity = self.queued_intensity
                    self.queued_mood = None
                    self._start_transition(mood, intensity)
