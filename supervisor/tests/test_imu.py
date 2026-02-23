"""Tests for IMU data handling: derived fields, fault detection, serialization."""

from __future__ import annotations

import math

from supervisor.core.state import RobotState
from supervisor.core.tick_loop import TickLoop
from supervisor.devices.protocol import Fault


class _FakeWorkers:
    """Minimal WorkerManager stub — only interface TickLoop touches at construction."""

    async def send_to(self, *_a, **_kw) -> bool:
        return False

    def worker_snapshot(self) -> dict:
        return {}


class TestImuDerivedFields:
    """Verify tilt_angle_deg and accel_magnitude_mg computed correctly."""

    def test_flat_tilt_zero(self):
        """Flat on table: accel_x=0, accel_z=1000 mg → tilt ≈ 0°."""
        s = RobotState(accel_x_mg=0, accel_z_mg=1000)
        tilt = math.degrees(math.atan2(s.accel_x_mg, s.accel_z_mg))
        assert abs(tilt) < 0.1

    def test_45_degree_tilt(self):
        """45° forward tilt: accel_x ≈ accel_z → tilt ≈ 45°."""
        s = RobotState(accel_x_mg=707, accel_z_mg=707)
        tilt = math.degrees(math.atan2(s.accel_x_mg, s.accel_z_mg))
        assert abs(tilt - 45.0) < 1.0

    def test_90_degree_tilt(self):
        """Tipped on side: accel_x=1000, accel_z=0 → tilt ≈ 90°."""
        s = RobotState(accel_x_mg=1000, accel_z_mg=0)
        tilt = math.degrees(math.atan2(s.accel_x_mg, s.accel_z_mg))
        assert abs(tilt - 90.0) < 0.1

    def test_accel_magnitude_at_rest(self):
        """Upright at rest: magnitude ≈ 1g = 1000 mg."""
        s = RobotState(accel_x_mg=0, accel_y_mg=0, accel_z_mg=1000)
        mag = math.sqrt(s.accel_x_mg**2 + s.accel_y_mg**2 + s.accel_z_mg**2)
        assert abs(mag - 1000.0) < 1.0

    def test_accel_magnitude_tilted(self):
        """Tilted 45°: magnitude should still ≈ 1000 mg (gravity conserved)."""
        s = RobotState(accel_x_mg=707, accel_y_mg=0, accel_z_mg=707)
        mag = math.sqrt(s.accel_x_mg**2 + s.accel_y_mg**2 + s.accel_z_mg**2)
        assert abs(mag - 1000.0) < 2.0  # rounding tolerance on 707 approximation


class TestImuFieldsPropagateViaTickLoop:
    """Verify _on_reflex_telemetry writes derived fields to robot state."""

    def _make_tel(self, **kwargs):
        """Create a minimal mock telemetry object."""

        class FakeTel:
            speed_l_mm_s = 0
            speed_r_mm_s = 0
            gyro_z_mrad_s = 0
            accel_x_mg = 0
            accel_y_mg = 0
            accel_z_mg = 1000
            battery_mv = 7400
            fault_flags = 0
            range_mm = 500
            range_status = 0
            seq = 1
            rx_mono_ms = 0.0
            v_meas_mm_s = 0.0
            w_meas_mrad_s = 0.0

        tel = FakeTel()
        for k, v in kwargs.items():
            setattr(tel, k, v)
        return tel

    def _make_loop(self):
        return TickLoop(reflex=None, face=None, workers=_FakeWorkers())

    def test_raw_fields_propagate(self):
        loop = self._make_loop()
        tel = self._make_tel(
            accel_x_mg=100, accel_y_mg=50, accel_z_mg=990, gyro_z_mrad_s=250
        )
        loop._on_reflex_telemetry(tel)
        assert loop.robot.accel_x_mg == 100
        assert loop.robot.accel_y_mg == 50
        assert loop.robot.accel_z_mg == 990
        assert loop.robot.gyro_z_mrad_s == 250

    def test_tilt_angle_computed(self):
        """tilt_angle_deg is set from atan2(accel_x, accel_z)."""
        loop = self._make_loop()
        # 45° tilt
        loop._on_reflex_telemetry(self._make_tel(accel_x_mg=707, accel_z_mg=707))
        assert abs(loop.robot.tilt_angle_deg - 45.0) < 1.0

    def test_accel_magnitude_computed(self):
        """accel_magnitude_mg is set from sqrt(x²+y²+z²)."""
        loop = self._make_loop()
        loop._on_reflex_telemetry(
            self._make_tel(accel_x_mg=0, accel_y_mg=0, accel_z_mg=1000)
        )
        assert abs(loop.robot.accel_magnitude_mg - 1000.0) < 1.0

    def test_flat_tilt_angle_is_zero(self):
        """At rest flat: tilt_angle_deg ≈ 0."""
        loop = self._make_loop()
        loop._on_reflex_telemetry(self._make_tel(accel_x_mg=0, accel_z_mg=1000))
        assert abs(loop.robot.tilt_angle_deg) < 0.1


class TestImuDerivedInSerialisation:
    """Verify derived IMU fields appear in to_dict() output."""

    def test_to_dict_has_tilt_angle(self):
        s = RobotState()
        d = s.to_dict()
        assert "tilt_angle_deg" in d

    def test_to_dict_has_accel_magnitude(self):
        s = RobotState()
        d = s.to_dict()
        assert "accel_magnitude_mg" in d

    def test_to_dict_tilt_rounded(self):
        s = RobotState()
        s.tilt_angle_deg = 12.34567
        d = s.to_dict()
        assert d["tilt_angle_deg"] == 12.3

    def test_to_dict_magnitude_rounded(self):
        s = RobotState()
        s.accel_magnitude_mg = 999.876
        d = s.to_dict()
        assert d["accel_magnitude_mg"] == 999.9


class TestImuFailFaultDetection:
    """Verify IMU_FAIL fault flag gates motion and is detectable."""

    def test_imu_fail_flag_detected(self):
        s = RobotState(fault_flags=Fault.IMU_FAIL)
        assert s.has_fault(Fault.IMU_FAIL)
        assert s.any_fault

    def test_no_imu_fail_when_clear(self):
        s = RobotState(fault_flags=0)
        assert not s.has_fault(Fault.IMU_FAIL)
        assert not s.any_fault

    def test_imu_fail_bit_position(self):
        """IMU_FAIL is bit 4 (value 16)."""
        assert int(Fault.IMU_FAIL) == (1 << 4)

    def test_other_faults_dont_set_imu_fail(self):
        s = RobotState(fault_flags=Fault.ESTOP | Fault.TILT | Fault.STALL)
        assert not s.has_fault(Fault.IMU_FAIL)
        assert s.any_fault
