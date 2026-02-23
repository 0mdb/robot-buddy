"""Tests for core state types."""

from __future__ import annotations

from supervisor.core.state import (
    Mode,
    MOTION_MODES,
    RobotState,
    WorldState,
)
from supervisor.devices.protocol import Fault


class TestMode:
    def test_motion_modes(self):
        assert Mode.TELEOP in MOTION_MODES
        assert Mode.WANDER in MOTION_MODES
        assert Mode.IDLE not in MOTION_MODES
        assert Mode.BOOT not in MOTION_MODES
        assert Mode.ERROR not in MOTION_MODES


class TestRobotState:
    def test_defaults(self):
        s = RobotState()
        assert s.mode == Mode.BOOT
        assert not s.reflex_connected
        assert not s.any_fault

    def test_fault_detection(self):
        s = RobotState(fault_flags=Fault.ESTOP | Fault.TILT)
        assert s.has_fault(Fault.ESTOP)
        assert s.has_fault(Fault.TILT)
        assert not s.has_fault(Fault.STALL)
        assert s.any_fault

    def test_to_dict_has_required_keys(self):
        s = RobotState()
        d = s.to_dict()
        assert "mode" in d
        assert "fault_flags" in d
        assert "clock_sync" in d
        assert "reflex" in d["clock_sync"]
        assert "face" in d["clock_sync"]

    def test_clock_sync_defaults(self):
        s = RobotState()
        assert s.reflex_clock.state == "unsynced"
        assert s.face_clock.state == "unsynced"


class TestWorldState:
    def test_defaults(self):
        w = WorldState()
        assert w.clear_confidence == -1.0
        assert not w.speaking
        assert w.active_skill == "patrol_drift"
        assert w.vision_age_ms == -1.0

    def test_both_audio_links(self):
        w = WorldState()
        assert not w.both_audio_links_up
        w.mic_link_up = True
        assert not w.both_audio_links_up
        w.spk_link_up = True
        assert w.both_audio_links_up

    def test_to_dict(self):
        w = WorldState()
        d = w.to_dict()
        assert "clear_conf" in d
        assert "speaking" in d
        assert "worker_alive" in d
