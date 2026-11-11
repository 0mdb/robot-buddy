"""Whole-screen touch gesture classifier (spec §9.5).

Mirrors the face MCU classifier: each touch becomes at most one gesture.

- Tap:        released within TOUCH_TAP_MAX_MS, moved <= TOUCH_MOVE_TOL_PX.
- Long-press: held >= TOUCH_LONG_PRESS_MS, moved <= TOUCH_MOVE_TOL_PX; fires at
              the threshold while still held (release afterwards reports nothing).
- Drag:       moved > TOUCH_MOVE_TOL_PX at any point -> no tap / long-press.
- Pet:        a drag whose finger path reaches TOUCH_PET_PATH_PX; PET fires once
              while held (a stroke that only qualifies on lift reports nothing).
- In-between: released between tap and long-press thresholds -> no gesture.

Pure logic: times are passed in (ms) so the classifier is deterministic and
testable without pygame. In the sim, mouse press/move/release = touch.
"""

from __future__ import annotations

from enum import IntEnum

from tools.face_sim_v3.state.constants import (
    TOUCH_LONG_PRESS_MS,
    TOUCH_MOVE_TOL_PX,
    TOUCH_PET_PATH_PX,
    TOUCH_RING_FLASH_MS,
    TOUCH_RING_SHOW_MS,
    TOUCH_TAP_MAX_MS,
)


class TouchGesture(IntEnum):
    NONE = 0
    TAP = 1  # -> BUTTON_EVENT(SCREEN, CLICK)
    LONG_PRESS = 2  # -> BUTTON_EVENT(SCREEN, LONG_PRESS)
    PET = 3  # -> BUTTON_EVENT(SCREEN, PET)


class TouchClassifier:
    """Classifies one touch at a time into TAP / LONG_PRESS / nothing."""

    def __init__(self) -> None:
        self.active: bool = False  # finger currently down
        self.x: int = 0  # current touch point (screen px)
        self.y: int = 0
        self._x0: int = 0  # touch-down point
        self._y0: int = 0
        self._t0_ms: float = 0.0
        self._dragged: bool = False
        self._long_fired: bool = False
        self._pet_fired: bool = False
        self._path_px: float = 0.0
        # Flash after long-press fires (may outlive the touch)
        self._flash_until_ms: float = -1.0
        self.flash_x: int = 0
        self.flash_y: int = 0

    # ── Touch input ─────────────────────────────────────────────────

    def press(self, x: int, y: int, now_ms: float) -> None:
        self.active = True
        self.x, self.y = x, y
        self._x0, self._y0 = x, y
        self._t0_ms = now_ms
        self._dragged = False
        self._long_fired = False
        self._pet_fired = False
        self._path_px = 0.0

    def move(self, x: int, y: int, now_ms: float) -> TouchGesture:
        """Update the touch point. May fire LONG_PRESS if the threshold passed."""
        if not self.active:
            return TouchGesture.NONE
        self._path_px += ((x - self.x) ** 2 + (y - self.y) ** 2) ** 0.5
        self.x, self.y = x, y
        dx = x - self._x0
        dy = y - self._y0
        if dx * dx + dy * dy > TOUCH_MOVE_TOL_PX * TOUCH_MOVE_TOL_PX:
            self._dragged = True
        return self.update(now_ms)

    def release(self, x: int, y: int, now_ms: float) -> TouchGesture:
        """Finger lifted. Returns TAP if the touch qualifies, else NONE."""
        if not self.active:
            return TouchGesture.NONE
        # A long-press due exactly now fires first (MCU polls before release)
        g = self.move(x, y, now_ms)
        self.active = False
        if g == TouchGesture.LONG_PRESS:
            return TouchGesture.LONG_PRESS
        if self._dragged or self._long_fired:
            return TouchGesture.NONE
        if now_ms - self._t0_ms < TOUCH_TAP_MAX_MS:
            return TouchGesture.TAP
        return TouchGesture.NONE

    def update(self, now_ms: float) -> TouchGesture:
        """Per-frame poll while held. LONG_PRESS once at the threshold, or PET once per stroke."""
        if not self.active or self._long_fired:
            return TouchGesture.NONE
        if self._dragged:
            if not self._pet_fired and self._path_px >= TOUCH_PET_PATH_PX:
                self._pet_fired = True
                return TouchGesture.PET
            return TouchGesture.NONE
        if now_ms - self._t0_ms >= TOUCH_LONG_PRESS_MS:
            self._long_fired = True
            self._flash_until_ms = now_ms + TOUCH_RING_FLASH_MS
            self.flash_x, self.flash_y = self.x, self.y
            return TouchGesture.LONG_PRESS
        return TouchGesture.NONE

    @property
    def petting(self) -> bool:
        """Finger down and stroking (PET has fired for this touch)."""
        return self.active and self._pet_fired

    def cancel(self) -> None:
        """Abort the current touch (e.g. a system overlay became active)."""
        self.active = False
        self._dragged = False
        self._long_fired = False
        self._pet_fired = False
        self._flash_until_ms = -1.0

    # ── Feedback queries ────────────────────────────────────────────

    def ring_progress(self, now_ms: float) -> float | None:
        """Long-press ring fill in [0, 1], or None when the ring is hidden."""
        if not self.active or self._dragged or self._long_fired:
            return None
        held = now_ms - self._t0_ms
        if held < TOUCH_RING_SHOW_MS:
            return None
        span = TOUCH_LONG_PRESS_MS - TOUCH_RING_SHOW_MS
        return min(1.0, (held - TOUCH_RING_SHOW_MS) / span)

    def ring_flash(self, now_ms: float) -> float | None:
        """Remaining flash fraction in (0, 1] after a long-press, else None."""
        remaining = self._flash_until_ms - now_ms
        if remaining <= 0:
            return None
        return remaining / TOUCH_RING_FLASH_MS
