"""Stub face MCU client — gracefully no-ops when face is absent."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class FaceClient:
    """Placeholder face client. Logs warnings and no-ops all commands."""

    def __init__(self) -> None:
        self._connected = False
        log.info("face: stub client initialized (no face MCU connected)")

    @property
    def connected(self) -> bool:
        return self._connected

    def send_state(
        self,
        emotion_id: int = 0,
        intensity: float = 1.0,
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
        brightness: float = 1.0,
    ) -> None:
        if not self._connected:
            return

    def send_gesture(self, gesture_id: int = 0) -> None:
        if not self._connected:
            return
