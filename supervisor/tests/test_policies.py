"""Tests for safety policies."""

from supervisor.devices.protocol import Fault, RangeStatus
from supervisor.state.datatypes import DesiredTwist, Mode, RobotState
from supervisor.state.policies import SafetyConfig, apply_safety


def _make_state(**kwargs) -> RobotState:
    defaults = dict(
        mode=Mode.TELEOP,
        reflex_connected=True,
        fault_flags=0,
        range_mm=2000,
        range_status=RangeStatus.OK,
    )
    defaults.update(kwargs)
    s = RobotState()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


class TestModeGate:
    def test_idle_zeroes_twist(self):
        s = _make_state(mode=Mode.IDLE)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0
        assert result.w_mrad_s == 0
        assert len(s.speed_caps) == 1
        assert "mode" in s.speed_caps[0].reason

    def test_error_zeroes_twist(self):
        s = _make_state(mode=Mode.ERROR)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0

    def test_boot_zeroes_twist(self):
        s = _make_state(mode=Mode.BOOT)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0

    def test_teleop_allows_twist(self):
        s = _make_state(mode=Mode.TELEOP)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 200
        assert result.w_mrad_s == 500

    def test_wander_allows_twist(self):
        s = _make_state(mode=Mode.WANDER)
        result = apply_safety(DesiredTwist(100, 100), s)
        assert result.v_mm_s == 100


class TestFaultGate:
    def test_estop_zeroes_twist(self):
        s = _make_state(fault_flags=Fault.ESTOP)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0
        assert "fault" in s.speed_caps[0].reason

    def test_cmd_timeout_zeroes_twist(self):
        s = _make_state(fault_flags=Fault.CMD_TIMEOUT)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0

    def test_combined_faults(self):
        s = _make_state(fault_flags=Fault.TILT | Fault.STALL)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0


class TestDisconnectGate:
    def test_disconnected_zeroes_twist(self):
        s = _make_state(reflex_connected=False)
        result = apply_safety(DesiredTwist(200, 500), s)
        assert result.v_mm_s == 0
        assert "disconnect" in s.speed_caps[0].reason


class TestUltrasonicCaps:
    def test_close_range_caps_25(self):
        s = _make_state(range_mm=250, range_status=RangeStatus.OK)
        result = apply_safety(DesiredTwist(200, 400), s)
        assert result.v_mm_s == 50  # 200 * 0.25
        assert result.w_mrad_s == 100  # 400 * 0.25

    def test_medium_range_caps_50(self):
        s = _make_state(range_mm=400, range_status=RangeStatus.OK)
        result = apply_safety(DesiredTwist(200, 400), s)
        assert result.v_mm_s == 100  # 200 * 0.50
        assert result.w_mrad_s == 200

    def test_far_range_no_cap(self):
        s = _make_state(range_mm=1000, range_status=RangeStatus.OK)
        result = apply_safety(DesiredTwist(200, 400), s)
        assert result.v_mm_s == 200
        assert result.w_mrad_s == 400
        assert len(s.speed_caps) == 0

    def test_stale_range_caps_50(self):
        s = _make_state(range_mm=0, range_status=RangeStatus.TIMEOUT)
        result = apply_safety(DesiredTwist(200, 400), s)
        assert result.v_mm_s == 100
        assert "stale" in s.speed_caps[0].reason

    def test_not_ready_caps_50(self):
        s = _make_state(range_mm=0, range_status=RangeStatus.NOT_READY)
        result = apply_safety(DesiredTwist(200, 400), s)
        assert result.v_mm_s == 100


class TestCustomSafetyConfig:
    def test_custom_close_threshold(self):
        cfg = SafetyConfig(range_close_mm=200, speed_cap_close_scale=0.10)
        s = _make_state(range_mm=150, range_status=RangeStatus.OK)
        result = apply_safety(DesiredTwist(200, 400), s, cfg)
        assert result.v_mm_s == 20  # 200 * 0.10
        assert result.w_mrad_s == 40

    def test_custom_medium_threshold(self):
        cfg = SafetyConfig(range_close_mm=100, range_medium_mm=800,
                           speed_cap_medium_scale=0.75)
        s = _make_state(range_mm=600, range_status=RangeStatus.OK)
        result = apply_safety(DesiredTwist(200, 400), s, cfg)
        assert result.v_mm_s == 150  # 200 * 0.75

    def test_custom_stale_scale(self):
        cfg = SafetyConfig(speed_cap_stale_scale=0.30)
        s = _make_state(range_mm=0, range_status=RangeStatus.TIMEOUT)
        result = apply_safety(DesiredTwist(200, 400), s, cfg)
        assert result.v_mm_s == 60  # 200 * 0.30


class TestSpeedCapsCleared:
    def test_caps_reset_each_call(self):
        s = _make_state(range_mm=250, range_status=RangeStatus.OK)
        apply_safety(DesiredTwist(200, 0), s)
        assert len(s.speed_caps) == 1

        # Call again with no caps needed
        s.range_mm = 2000
        apply_safety(DesiredTwist(200, 0), s)
        assert len(s.speed_caps) == 0
