"""Mock reflex MCU using a PTY pair for development without hardware.

Speaks protocol v2 only, like the STM32G431 reflex firmware (PROTOCOL.md 3.2, amended
2026-11-27): v2 envelopes from boot, the v1-envelope SET_PROTOCOL_VERSION is the one v1 frame
it accepts, and it ACKs in v2.

Usage:
    mock = MockReflex()
    mock.start()
    # Connect supervisor to mock.device_path
    ...
    mock.stop()
"""

from __future__ import annotations

import logging
import os
import struct
import threading
import time
import tty

from supervisor.devices.protocol import (
    COMMON_PROTOCOL_VERSION_ACK,
    COMMON_SET_PROTOCOL_VERSION,
    COMMON_TIME_SYNC_REQ,
    COMMON_TIME_SYNC_RESP,
    CmdType,
    Fault,
    TelType,
    build_packet_v2,
    parse_frame,
)

from supervisor.io.cobs import decode as cobs_decode

log = logging.getLogger(__name__)

_V2_MIN_FRAME = 15  # v2 header 13 + crc 2: anything shorter is a v1 envelope

_STATE_FMT = struct.Struct(
    "<hhhhhhHHBII"
)  # v2 StatePayload: 17-byte core + cmd_seq_last_applied, t_cmd_applied_us


class MockReflex:
    """Simulated reflex MCU that accepts commands and streams telemetry."""

    def __init__(self, telemetry_hz: float = 20.0) -> None:
        self.telemetry_hz = telemetry_hz

        # Simulated state
        self.v_cmd_mm_s: int = 0
        self.w_cmd_mrad_s: int = 0
        self.v_actual_mm_s: float = 0.0
        self.w_actual_mrad_s: float = 0.0
        self.fault_flags: int = 0
        self.range_mm: int = 2000
        self.range_status: int = 0  # OK

        self._master_fd: int = -1
        self._slave_fd: int = -1
        self.device_path: str = ""
        self._running = False
        self._thread_rx: threading.Thread | None = None
        self._thread_tx: threading.Thread | None = None
        self._last_cmd_time: float = 0.0
        self._seq: int = 0
        self._cmd_seq_last: int = 0
        self._t_cmd_applied_us: int = 0
        self._cmd_timeout_s = 0.4  # matches reflex config.h

    def start(self) -> None:
        self._master_fd, self._slave_fd = os.openpty()
        # Raw from the start: a cooked slave echoes our own STATE frames back into _rx_loop
        # until the client opens it, and the leftover bytes corrupt the first real frame
        # (the v2 handshake).
        tty.setraw(self._slave_fd)
        self.device_path = os.ttyname(self._slave_fd)
        log.info("mock_reflex: PTY at %s", self.device_path)

        self._running = True
        self._last_cmd_time = time.monotonic()
        self._thread_rx = threading.Thread(target=self._rx_loop, daemon=True)
        self._thread_tx = threading.Thread(target=self._tx_loop, daemon=True)
        self._thread_rx.start()
        self._thread_tx.start()

    def stop(self) -> None:
        self._running = False
        if self._thread_rx:
            self._thread_rx.join(timeout=2)
        if self._thread_tx:
            self._thread_tx.join(timeout=2)
        for fd in (self._master_fd, self._slave_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._master_fd = -1
        self._slave_fd = -1

    def inject_fault(self, fault: Fault) -> None:
        self.fault_flags |= fault

    def clear_fault(self, fault: Fault) -> None:
        self.fault_flags &= ~fault

    # -- internals -----------------------------------------------------------

    def _rx_loop(self) -> None:
        buf = bytearray()
        while self._running:
            try:
                data = os.read(self._master_fd, 256)
            except OSError:
                time.sleep(0.01)
                continue
            if not data:
                continue

            for b in data:
                if b == 0x00:
                    if buf:
                        self._handle_frame(bytes(buf))
                        buf.clear()
                else:
                    buf.append(b)

    def _send(self, pkt_type: int, payload: bytes) -> None:
        now_us = time.monotonic_ns() // 1000
        try:
            os.write(
                self._master_fd,
                build_packet_v2(pkt_type, self._next_seq(), now_us, payload),
            )
        except OSError:
            pass

    def _handle_frame(self, frame: bytes) -> None:
        try:
            pkt = parse_frame(frame, protocol_version=2)
        except ValueError as e:
            log.debug("mock_reflex: bad frame: %s", e)
            return

        # The handshake request comes in a v1 envelope (5 bytes decoded, so parse_frame fell
        # back to v1): the only v1 frame accepted. Always ACK v2.
        if pkt.pkt_type == COMMON_SET_PROTOCOL_VERSION:
            self._send(COMMON_PROTOCOL_VERSION_ACK, bytes([2]))
            return
        if len(cobs_decode(frame)) < _V2_MIN_FRAME:
            log.debug("mock_reflex: dropped v1 frame type 0x%02X", pkt.pkt_type)
            return

        # TIME_SYNC: respond immediately, don't update cmd timeout
        if pkt.pkt_type == COMMON_TIME_SYNC_REQ:
            if len(pkt.payload) >= 8:
                ping_seq = struct.unpack_from("<I", pkt.payload, 0)[0]
                now_us = time.monotonic_ns() // 1000
                self._send(COMMON_TIME_SYNC_RESP, struct.pack("<IQ", ping_seq, now_us))
            return

        self._last_cmd_time = time.monotonic()
        self._cmd_seq_last = pkt.seq
        self._t_cmd_applied_us = (time.monotonic_ns() // 1000) & 0xFFFFFFFF

        if pkt.pkt_type == CmdType.SET_TWIST:
            if len(pkt.payload) >= 4:
                v, w = struct.unpack_from("<hh", pkt.payload)
                self.v_cmd_mm_s = v
                self.w_cmd_mrad_s = w
        elif pkt.pkt_type == CmdType.STOP:
            self.v_cmd_mm_s = 0
            self.w_cmd_mrad_s = 0
        elif pkt.pkt_type == CmdType.ESTOP:
            self.v_cmd_mm_s = 0
            self.w_cmd_mrad_s = 0
            self.fault_flags |= Fault.ESTOP
        elif pkt.pkt_type == CmdType.CLEAR_FAULTS:
            if len(pkt.payload) >= 2:
                mask = struct.unpack_from("<H", pkt.payload)[0]
                self.fault_flags &= ~mask
        elif pkt.pkt_type == CmdType.SET_CONFIG:
            if len(pkt.payload) >= 5:
                param_id = pkt.payload[0]
                log.debug("mock_reflex: SET_CONFIG param_id=0x%02X", param_id)

    def _tx_loop(self) -> None:
        period = 1.0 / self.telemetry_hz
        while self._running:
            t0 = time.monotonic()
            self._simulate_step()
            self._send_state()
            elapsed = time.monotonic() - t0
            time.sleep(max(0, period - elapsed))

    def _simulate_step(self) -> None:
        # Check command timeout
        if time.monotonic() - self._last_cmd_time > self._cmd_timeout_s:
            self.v_cmd_mm_s = 0
            self.w_cmd_mrad_s = 0
            self.fault_flags |= Fault.CMD_TIMEOUT

        # Simple first-order lag towards commanded velocity
        alpha = 0.3
        if self.fault_flags:
            self.v_actual_mm_s = 0.0
            self.w_actual_mrad_s = 0.0
        else:
            self.v_actual_mm_s += alpha * (self.v_cmd_mm_s - self.v_actual_mm_s)
            self.w_actual_mrad_s += alpha * (self.w_cmd_mrad_s - self.w_actual_mrad_s)

    def _send_state(self) -> None:
        # Convert actual velocities to wheel speeds
        v = self.v_actual_mm_s
        w = self.w_actual_mrad_s
        half_w = w * 150.0 / 2000.0  # wheelbase_mm / 2 * mrad_to_rad_like
        speed_l = int(v - half_w)
        speed_r = int(v + half_w)

        payload = _STATE_FMT.pack(
            speed_l,
            speed_r,
            int(self.w_actual_mrad_s),
            0,  # accel_x_mg (mock: flat)
            0,  # accel_y_mg
            1000,  # accel_z_mg (mock: 1g upright)
            self.fault_flags,
            self.range_mm,
            self.range_status,
            self._cmd_seq_last,
            self._t_cmd_applied_us,
        )
        self._send(TelType.STATE, payload)

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return s
