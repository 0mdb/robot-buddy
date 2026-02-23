"""Conversation phase transition choreographer (spec §5.1.2).

Produces timed gesture/gaze actions when conversation state transitions
occur.  Does NOT mutate face state directly — tick_loop reads outputs.

Supervisor port of tools/face_sim_v3/state/conv_choreographer.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from supervisor.devices.protocol import FaceConvState, FaceGesture, FaceMood

log = logging.getLogger(__name__)

# ── Timing constants (match sim constants.py §5.1.2) ─────────────────

TRANS_LT_GAZE_RAMP_MS = 300.0
TRANS_TS_BLINK_DELAY_MS = 0.0
TRANS_TS_BLINK_DURATION_MS = 180.0
TRANS_TS_GAZE_RAMP_DELAY_MS = 50.0
TRANS_TS_GAZE_RAMP_MS = 300.0
TRANS_SL_NOD_DELAY_MS = 100.0
TRANS_SL_NOD_DURATION_MS = 350.0
TRANS_SD_SUPPRESS_MS = 500.0

# Per-state gaze targets (normalized, match conv_state.py tables)
_GAZE_CENTER = (0.0, 0.0)
_GAZE_THINKING = (0.5, -0.3)


# ── Action descriptor ────────────────────────────────────────────────


@dataclass(slots=True)
class TransitionAction:
    """A single action to fire during a transition."""

    kind: str  # "gesture" | "mood_nudge"
    delay_ms: float
    params: dict[str, object] = field(default_factory=dict)


# ── Gaze ramp ────────────────────────────────────────────────────────


@dataclass(slots=True)
class _GazeRamp:
    """Linear-with-ease-out interpolation of gaze target."""

    start_x: float
    start_y: float
    end_x: float
    end_y: float
    duration_ms: float
    delay_ms: float = 0.0
    elapsed_ms: float = 0.0

    def update(self, dt_ms: float) -> tuple[float, float]:
        self.elapsed_ms += dt_ms
        active_ms = self.elapsed_ms - self.delay_ms
        if active_ms <= 0.0:
            return (self.start_x, self.start_y)
        t = min(1.0, active_ms / self.duration_ms) if self.duration_ms > 0 else 1.0
        # Ease-out: t' = 1 - (1-t)^2
        t_ease = 1.0 - (1.0 - t) * (1.0 - t)
        return (
            self.start_x + (self.end_x - self.start_x) * t_ease,
            self.start_y + (self.end_y - self.start_y) * t_ease,
        )

    @property
    def started(self) -> bool:
        return self.elapsed_ms >= self.delay_ms

    @property
    def done(self) -> bool:
        return (self.elapsed_ms - self.delay_ms) >= self.duration_ms


# ── Choreographer ────────────────────────────────────────────────────


class ConvTransitionChoreographer:
    """Fires timed action sequences on conversation state transitions."""

    def __init__(self) -> None:
        self._timer_ms: float = 0.0
        self._actions: list[TransitionAction] = []
        self._fired: set[int] = set()
        self._gaze_ramp: _GazeRamp | None = None
        self._suppress_mood_ms: float = 0.0
        self._total_duration_ms: float = 0.0
        self._has_blink: bool = False

    @property
    def active(self) -> bool:
        """True while a transition sequence is still playing."""
        if self._gaze_ramp is not None and not self._gaze_ramp.done:
            return True
        if self._suppress_mood_ms > 0.0 and self._timer_ms < self._suppress_mood_ms:
            return True
        return self._timer_ms < self._total_duration_ms

    @property
    def suppress_mood_pipeline(self) -> bool:
        """True when mood pipeline should be skipped."""
        return self._suppress_mood_ms > 0.0 and self._timer_ms < self._suppress_mood_ms

    @property
    def has_blink(self) -> bool:
        """True if this transition includes a blink gesture."""
        return self._has_blink

    def on_transition(self, prev: FaceConvState, new: FaceConvState) -> None:
        """Load choreography for a state transition."""
        self._reset()

        if prev == FaceConvState.LISTENING and new == FaceConvState.THINKING:
            self._setup_listening_to_thinking()
        elif prev == FaceConvState.THINKING and new == FaceConvState.SPEAKING:
            self._setup_thinking_to_speaking()
        elif prev == FaceConvState.SPEAKING and new == FaceConvState.LISTENING:
            self._setup_speaking_to_listening()
        elif prev == FaceConvState.SPEAKING and new == FaceConvState.DONE:
            self._setup_speaking_to_done()

    def update(self, dt_ms: float) -> list[TransitionAction]:
        """Advance timer, return actions ready to fire this tick."""
        if (
            not self._actions
            and self._gaze_ramp is None
            and self._suppress_mood_ms <= 0
        ):
            return []

        self._timer_ms += dt_ms
        fired: list[TransitionAction] = []

        for i, action in enumerate(self._actions):
            if i not in self._fired and self._timer_ms >= action.delay_ms:
                self._fired.add(i)
                fired.append(action)

        if self._gaze_ramp is not None:
            self._gaze_ramp.update(dt_ms)

        return fired

    def get_gaze_override(self) -> tuple[float, float] | None:
        """Return interpolated gaze if a ramp is active, else None."""
        if self._gaze_ramp is None:
            return None
        if self._gaze_ramp.done:
            return None
        return self._gaze_ramp.update(0.0)

    # ── Private helpers ──────────────────────────────────────────────

    def _reset(self) -> None:
        self._timer_ms = 0.0
        self._actions = []
        self._fired = set()
        self._gaze_ramp = None
        self._suppress_mood_ms = 0.0
        self._total_duration_ms = 0.0
        self._has_blink = False

    def _setup_listening_to_thinking(self) -> None:
        """Gaze ramp from center to aversion target."""
        self._gaze_ramp = _GazeRamp(
            start_x=_GAZE_CENTER[0],
            start_y=_GAZE_CENTER[1],
            end_x=_GAZE_THINKING[0],
            end_y=_GAZE_THINKING[1],
            duration_ms=TRANS_LT_GAZE_RAMP_MS,
        )
        self._total_duration_ms = TRANS_LT_GAZE_RAMP_MS

    def _setup_thinking_to_speaking(self) -> None:
        """Anticipation blink + gaze ramp back to center."""
        self._actions = [
            TransitionAction(
                kind="gesture",
                delay_ms=TRANS_TS_BLINK_DELAY_MS,
                params={
                    "name": "blink",
                    "gesture_id": int(FaceGesture.BLINK),
                    "duration_ms": TRANS_TS_BLINK_DURATION_MS,
                },
            ),
        ]
        self._has_blink = True

        self._gaze_ramp = _GazeRamp(
            start_x=_GAZE_THINKING[0],
            start_y=_GAZE_THINKING[1],
            end_x=_GAZE_CENTER[0],
            end_y=_GAZE_CENTER[1],
            duration_ms=TRANS_TS_GAZE_RAMP_MS,
            delay_ms=TRANS_TS_GAZE_RAMP_DELAY_MS,
        )
        self._total_duration_ms = TRANS_TS_GAZE_RAMP_DELAY_MS + TRANS_TS_GAZE_RAMP_MS

    def _setup_speaking_to_listening(self) -> None:
        """Re-engagement nod."""
        self._actions = [
            TransitionAction(
                kind="gesture",
                delay_ms=TRANS_SL_NOD_DELAY_MS,
                params={
                    "name": "nod",
                    "gesture_id": int(FaceGesture.NOD),
                    "duration_ms": TRANS_SL_NOD_DURATION_MS,
                },
            ),
        ]
        self._total_duration_ms = TRANS_SL_NOD_DELAY_MS + TRANS_SL_NOD_DURATION_MS

    def _setup_speaking_to_done(self) -> None:
        """Mood nudge to neutral + suppress pipeline."""
        self._actions = [
            TransitionAction(
                kind="mood_nudge",
                delay_ms=0.0,
                params={"mood_id": int(FaceMood.NEUTRAL), "intensity": 0.0},
            ),
        ]
        self._suppress_mood_ms = TRANS_SD_SUPPRESS_MS
        self._total_duration_ms = TRANS_SD_SUPPRESS_MS
