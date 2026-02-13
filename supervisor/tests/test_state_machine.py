"""Tests for the supervisor mode state machine."""

from supervisor.devices.protocol import Fault
from supervisor.state.datatypes import Mode
from supervisor.state.supervisor_sm import SupervisorSM


class TestAutoTransitions:
    def test_boot_to_idle_on_healthy_reflex(self):
        sm = SupervisorSM()
        assert sm.mode == Mode.BOOT
        sm.update(reflex_connected=True, fault_flags=0)
        assert sm.mode == Mode.IDLE

    def test_stays_boot_without_reflex(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=False, fault_flags=0)
        assert sm.mode == Mode.BOOT

    def test_stays_boot_with_faults(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=Fault.CMD_TIMEOUT)
        assert sm.mode == Mode.BOOT

    def test_disconnect_triggers_error(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)  # → IDLE
        sm.update(reflex_connected=False, fault_flags=0)  # → ERROR
        assert sm.mode == Mode.ERROR

    def test_severe_fault_triggers_error(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)  # → IDLE
        sm.update(reflex_connected=True, fault_flags=Fault.ESTOP)
        assert sm.mode == Mode.ERROR

    def test_tilt_triggers_error(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        sm.update(reflex_connected=True, fault_flags=Fault.TILT)
        assert sm.mode == Mode.ERROR

    def test_obstacle_does_not_trigger_error(self):
        """OBSTACLE is handled by speed caps, not mode change."""
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        sm.update(reflex_connected=True, fault_flags=Fault.OBSTACLE)
        assert sm.mode == Mode.IDLE


class TestRequestMode:
    def _idle_sm(self) -> SupervisorSM:
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        return sm

    def test_idle_to_teleop(self):
        sm = self._idle_sm()
        ok, _ = sm.request_mode(Mode.TELEOP, reflex_connected=True, fault_flags=0)
        assert ok
        assert sm.mode == Mode.TELEOP

    def test_idle_to_wander(self):
        sm = self._idle_sm()
        ok, _ = sm.request_mode(Mode.WANDER, reflex_connected=True, fault_flags=0)
        assert ok
        assert sm.mode == Mode.WANDER

    def test_teleop_to_idle(self):
        sm = self._idle_sm()
        sm.request_mode(Mode.TELEOP, reflex_connected=True, fault_flags=0)
        ok, _ = sm.request_mode(Mode.IDLE, reflex_connected=True, fault_flags=0)
        assert ok
        assert sm.mode == Mode.IDLE

    def test_cannot_teleop_from_error(self):
        sm = self._idle_sm()
        sm.update(reflex_connected=True, fault_flags=Fault.ESTOP)  # → ERROR
        ok, reason = sm.request_mode(Mode.TELEOP, reflex_connected=True, fault_flags=0)
        assert not ok
        assert "clear errors" in reason

    def test_cannot_teleop_with_faults(self):
        sm = self._idle_sm()
        ok, reason = sm.request_mode(
            Mode.TELEOP, reflex_connected=True, fault_flags=Fault.STALL
        )
        assert not ok
        assert "faults" in reason

    def test_cannot_teleop_without_reflex(self):
        sm = self._idle_sm()
        ok, reason = sm.request_mode(Mode.TELEOP, reflex_connected=False, fault_flags=0)
        assert not ok
        assert "not connected" in reason

    def test_already_in_mode(self):
        sm = self._idle_sm()
        ok, reason = sm.request_mode(Mode.IDLE, reflex_connected=True, fault_flags=0)
        assert ok
        assert "already" in reason


class TestClearError:
    def test_clear_error_success(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)  # IDLE
        sm.update(reflex_connected=True, fault_flags=Fault.ESTOP)  # ERROR
        assert sm.mode == Mode.ERROR

        ok, _ = sm.clear_error(reflex_connected=True, fault_flags=0)
        assert ok
        assert sm.mode == Mode.IDLE

    def test_clear_error_fails_with_active_faults(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        sm.update(reflex_connected=True, fault_flags=Fault.ESTOP)

        ok, reason = sm.clear_error(reflex_connected=True, fault_flags=Fault.ESTOP)
        assert not ok
        assert sm.mode == Mode.ERROR

    def test_clear_error_fails_without_reflex(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        sm.update(reflex_connected=False, fault_flags=0)  # ERROR via disconnect

        ok, _ = sm.clear_error(reflex_connected=False, fault_flags=0)
        assert not ok

    def test_clear_error_when_not_in_error(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        ok, reason = sm.clear_error(reflex_connected=True, fault_flags=0)
        assert not ok
        assert "not in ERROR" in reason
