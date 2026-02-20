"""Supervisor mode state machine.

Transitions:
    BOOT  → IDLE    (reflex connected and healthy)
    IDLE  → TELEOP  (set_mode command)
    IDLE  → WANDER  (set_mode command)
    Any   → ERROR   (reflex disconnect, severe fault, e-stop)
    ERROR → IDLE    (clear_e_stop + faults cleared + reflex connected)
"""

from __future__ import annotations

import logging

from supervisor_v2.devices.protocol import Fault
from supervisor_v2.core.state import Mode, MOTION_MODES

log = logging.getLogger(__name__)

# Faults that force ERROR mode
_SEVERE_FAULTS = Fault.ESTOP | Fault.TILT | Fault.BROWNOUT


class SupervisorSM:
    """Simple mode state machine with guarded transitions."""

    def __init__(self) -> None:
        self._mode = Mode.BOOT

    @property
    def mode(self) -> Mode:
        return self._mode

    def update(
        self,
        reflex_connected: bool,
        fault_flags: int,
    ) -> Mode:
        """Called each tick. Evaluates auto-transitions based on system health."""

        # Any mode → ERROR on disconnect or severe fault
        if not reflex_connected and self._mode != Mode.BOOT:
            self._transition(Mode.ERROR, "reflex disconnected")
        elif fault_flags & _SEVERE_FAULTS:
            self._transition(Mode.ERROR, f"severe fault 0x{fault_flags:04X}")

        # BOOT → IDLE when reflex is connected and healthy
        elif self._mode == Mode.BOOT and reflex_connected and fault_flags == 0:
            self._transition(Mode.IDLE, "reflex ready")

        return self._mode

    def request_mode(
        self,
        target: Mode,
        reflex_connected: bool,
        fault_flags: int,
    ) -> tuple[bool, str]:
        """Handle explicit mode change request. Returns (success, reason)."""

        if target == self._mode:
            return True, "already in mode"

        # ERROR can only be exited via clear_error
        if self._mode == Mode.ERROR:
            return False, "must clear errors first"

        # Can only enter motion modes from IDLE
        if target in MOTION_MODES:
            if self._mode != Mode.IDLE:
                return False, f"can only enter {target.value} from IDLE"
            if not reflex_connected:
                return False, "reflex not connected"
            if fault_flags != 0:
                return False, f"faults active: 0x{fault_flags:04X}"
            self._transition(target, "user request")
            return True, "ok"

        # Return to IDLE from motion modes
        if target == Mode.IDLE:
            if self._mode in MOTION_MODES:
                self._transition(Mode.IDLE, "user request")
                return True, "ok"
            return False, f"cannot go to IDLE from {self._mode.value}"

        return False, f"unsupported mode: {target.value}"

    def clear_error(
        self,
        reflex_connected: bool,
        fault_flags: int,
    ) -> tuple[bool, str]:
        """Attempt to exit ERROR mode. Returns (success, reason)."""
        if self._mode != Mode.ERROR:
            return False, "not in ERROR mode"
        if not reflex_connected:
            return False, "reflex not connected"
        if fault_flags & _SEVERE_FAULTS:
            return False, f"severe faults still active: 0x{fault_flags:04X}"
        self._transition(Mode.IDLE, "error cleared")
        return True, "ok"

    def _transition(self, target: Mode, reason: str) -> None:
        if target != self._mode:
            log.info("mode: %s → %s (%s)", self._mode.value, target.value, reason)
            self._mode = target
