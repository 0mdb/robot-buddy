"""Negative affect guardrails (spec §7).

Three mechanisms:
1. Context gate: SAD/SCARED/ANGRY blocked outside conversation
2. Intensity cap: per-mood maximum (ANGRY 0.5, SCARED 0.6, SAD 0.7, SURPRISED 0.8)
3. Duration cap: auto-recovery to NEUTRAL after max duration
"""

from __future__ import annotations

import time

from tools.face_sim_v3.state.constants import (
    GUARDRAIL_INTENSITY_CAP,
    GUARDRAIL_MAX_DURATION,
    NEGATIVE_MOODS,
    Mood,
)


class Guardrails:
    """Enforces negative affect limits."""

    def __init__(self) -> None:
        self._mood_start: float = 0.0
        self._current_mood: Mood = Mood.NEUTRAL
        self._fired: bool = False  # True if recovery was triggered this mood

    def check(
        self,
        mood: Mood,
        intensity: float,
        conversation_active: bool,
    ) -> tuple[Mood, float]:
        """Check guardrails and return (mood, intensity) — possibly modified.

        Returns (NEUTRAL, 0.0) if mood should be reset.
        """
        now = time.monotonic()

        # Track mood changes
        if mood != self._current_mood:
            self._current_mood = mood
            self._mood_start = now
            self._fired = False

        # 1. Context gate: negative moods blocked outside conversation
        if mood in NEGATIVE_MOODS and not conversation_active:
            return Mood.NEUTRAL, 0.0

        # 2. Intensity cap
        cap = GUARDRAIL_INTENSITY_CAP.get(mood)
        if cap is not None:
            intensity = min(intensity, cap)

        # 3. Duration cap
        max_dur = GUARDRAIL_MAX_DURATION.get(mood)
        if max_dur is not None and not self._fired:
            elapsed = now - self._mood_start
            if elapsed > max_dur:
                self._fired = True
                return Mood.NEUTRAL, 0.0

        return mood, intensity
