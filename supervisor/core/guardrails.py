"""Negative affect guardrails (spec §7).

Three mechanisms:
1. Context gate: SAD/SCARED/ANGRY blocked outside conversation
2. Intensity cap: per-mood maximum (ANGRY 0.5, SCARED 0.6, SAD 0.7, SURPRISED 0.8)
3. Duration cap: auto-recovery to NEUTRAL after max duration

Supervisor port of tools/face_sim_v3/state/guardrails.py.
"""

from __future__ import annotations

import logging

from supervisor.devices.protocol import FaceMood

log = logging.getLogger(__name__)

# Moods blocked outside conversation (context gate)
NEGATIVE_MOOD_IDS: frozenset[int] = frozenset(
    {int(FaceMood.SAD), int(FaceMood.SCARED), int(FaceMood.ANGRY)}
)

# Per-mood intensity caps
INTENSITY_CAP: dict[int, float] = {
    int(FaceMood.ANGRY): 0.5,
    int(FaceMood.SCARED): 0.6,
    int(FaceMood.SAD): 0.7,
    int(FaceMood.SURPRISED): 0.8,
}

# Per-mood maximum duration before auto-recovery (seconds)
MAX_DURATION_S: dict[int, float] = {
    int(FaceMood.ANGRY): 2.0,
    int(FaceMood.SCARED): 2.0,
    int(FaceMood.SAD): 4.0,
    int(FaceMood.SURPRISED): 3.0,
}

_NEUTRAL_ID = int(FaceMood.NEUTRAL)


class Guardrails:
    """Enforces negative affect limits for child safety."""

    def __init__(self) -> None:
        self._mood_start: float = 0.0
        self._current_mood_id: int = _NEUTRAL_ID
        self._fired: bool = False

    def check(
        self,
        mood_id: int,
        intensity: float,
        conversation_active: bool,
        now: float,
    ) -> tuple[int, float]:
        """Apply guardrails. Returns *(mood_id, intensity)*, possibly modified.

        Args:
            mood_id: Target mood (FaceMood int value).
            intensity: Target intensity (0.0–1.0).
            conversation_active: Whether a conversation session is active.
            now: Current time in seconds (monotonic).
        """
        # Track mood changes
        if mood_id != self._current_mood_id:
            self._current_mood_id = mood_id
            self._mood_start = now
            self._fired = False

        # 1. Context gate: negative moods blocked outside conversation
        if mood_id in NEGATIVE_MOOD_IDS and not conversation_active:
            return _NEUTRAL_ID, 0.0

        # 2. Intensity cap
        cap = INTENSITY_CAP.get(mood_id)
        if cap is not None:
            intensity = min(intensity, cap)

        # 3. Duration cap
        max_dur = MAX_DURATION_S.get(mood_id)
        if max_dur is not None and not self._fired:
            elapsed = now - self._mood_start
            if elapsed > max_dur:
                self._fired = True
                return _NEUTRAL_ID, 0.0

        return mood_id, intensity
