"""High-level client for the reflex MCU."""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass
from typing import Callable

from supervisor.devices.protocol import (
    Fault,
    ParsedPacket,
    RangeStatus,
    StatePayload,
    TelType,
    build_clear_faults,
    build_estop,
    build_set_config,
    build_set_twist,
    build_stop,
)
from supervisor.io.serial_transport import SerialTransport

log = logging.getLogger(__name__)

# Kinematics (must match config.h)
WHEELBASE_MM = 150.0

# ConfigParam IDs — must match ConfigParam enum in config.h
REFLEX_PARAM_IDS: dict[str, int] = {
    "reflex.kV": 0x01,
    "reflex.kS": 0x02,
    "reflex.Kp": 0x03,
    "reflex.Ki": 0x04,
    "reflex.min_pwm": 0x05,
    "reflex.max_pwm": 0x06,
    "reflex.max_v_mm_s": 0x10,
    "reflex.max_a_mm_s2": 0x11,
    "reflex.max_w_mrad_s": 0x12,
    "reflex.max_aw_mrad_s2": 0x13,
    "reflex.K_yaw": 0x20,
    "reflex.cmd_timeout_ms": 0x30,
    "reflex.soft_stop_ramp_ms": 0x31,
    "reflex.tilt_thresh_deg": 0x32,
    "reflex.tilt_hold_ms": 0x33,
    "reflex.stall_thresh_ms": 0x34,
    "reflex.stall_speed_thresh": 0x35,
    "reflex.range_stop_mm": 0x40,
    "reflex.range_release_mm": 0x41,
    "reflex.imu_odr_hz": 0x50,
    "reflex.imu_gyro_range_dps": 0x51,
    "reflex.imu_accel_range_g": 0x52,
}


@dataclass(slots=True)
class ReflexTelemetry:
    """Latest parsed STATE from the reflex MCU."""

    speed_l_mm_s: int = 0
    speed_r_mm_s: int = 0
    gyro_z_mrad_s: int = 0
    battery_mv: int = 0
    fault_flags: int = 0
    range_mm: int = 0
    range_status: int = RangeStatus.NOT_READY
    echo_us: int = 0
    rx_mono_ms: float = 0.0
    seq: int = 0

    @property
    def v_meas_mm_s(self) -> float:
        return (self.speed_l_mm_s + self.speed_r_mm_s) / 2.0

    @property
    def w_meas_mrad_s(self) -> float:
        return (self.speed_r_mm_s - self.speed_l_mm_s) / WHEELBASE_MM * 1000.0

    def has_fault(self, f: Fault) -> bool:
        return bool(self.fault_flags & f)

    @property
    def any_fault(self) -> bool:
        return self.fault_flags != 0


class ReflexClient:
    """Send commands to and receive telemetry from the reflex MCU."""

    def __init__(self, transport: SerialTransport) -> None:
        self._transport = transport
        self._seq = 0
        self.telemetry = ReflexTelemetry()
        self._on_telemetry: Callable[[ReflexTelemetry], None] | None = None

        transport.on_packet(self._handle_packet)

    @property
    def connected(self) -> bool:
        return self._transport.connected

    def on_telemetry(self, cb: Callable[[ReflexTelemetry], None]) -> None:
        self._on_telemetry = cb

    def send_twist(self, v_mm_s: int, w_mrad_s: int) -> None:
        pkt = build_set_twist(self._next_seq(), v_mm_s, w_mrad_s)
        self._transport.write(pkt)

    def send_stop(self, reason: int = 0) -> None:
        pkt = build_stop(self._next_seq(), reason)
        self._transport.write(pkt)

    def send_estop(self) -> None:
        pkt = build_estop(self._next_seq())
        self._transport.write(pkt)

    def send_clear_faults(self, mask: int = 0xFFFF) -> None:
        pkt = build_clear_faults(self._next_seq(), mask)
        self._transport.write(pkt)

    def send_set_config(self, param_name: str, value: int | float) -> bool:
        """Send a SET_CONFIG command for a named parameter.

        Returns True if the param is known and the packet was sent.
        """
        param_id = REFLEX_PARAM_IDS.get(param_name)
        if param_id is None:
            log.warning("send_set_config: unknown param %r", param_name)
            return False

        # Determine encoding from param registry type
        # Float params: kV, kS, Kp, Ki, K_yaw, tilt_thresh_deg
        float_params = {0x01, 0x02, 0x03, 0x04, 0x20, 0x32}
        if param_id in float_params:
            value_bytes = struct.pack("<f", float(value))
        else:
            # All others are int (u32 or i32 on wire, truncated on MCU side)
            value_bytes = struct.pack("<i", int(value))

        pkt = build_set_config(self._next_seq(), param_id, value_bytes)
        self._transport.write(pkt)
        log.info("SET_CONFIG %s (0x%02X) = %s", param_name, param_id, value)
        return True

    # -- internals -----------------------------------------------------------

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        return s

    def _handle_packet(self, pkt: ParsedPacket) -> None:
        if pkt.pkt_type == TelType.STATE:
            try:
                state = StatePayload.unpack(pkt.payload)
            except ValueError as e:
                log.warning("reflex: bad STATE payload: %s", e)
                return

            t = self.telemetry
            t.speed_l_mm_s = state.speed_l_mm_s
            t.speed_r_mm_s = state.speed_r_mm_s
            t.gyro_z_mrad_s = state.gyro_z_mrad_s
            t.battery_mv = state.battery_mv
            t.fault_flags = state.fault_flags
            t.range_mm = state.range_mm
            t.range_status = state.range_status
            t.echo_us = state.echo_us
            t.rx_mono_ms = time.monotonic() * 1000.0
            t.seq = pkt.seq

            if self._on_telemetry:
                self._on_telemetry(t)
        else:
            log.debug("reflex: unknown packet type 0x%02X", pkt.pkt_type)
