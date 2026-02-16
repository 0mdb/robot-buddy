"""Tests for protocol packet building and parsing."""

import struct

import pytest

from supervisor.devices.protocol import (
    CmdType,
    Fault,
    StatePayload,
    TelType,
    build_clear_faults,
    build_estop,
    build_packet,
    build_set_twist,
    build_stop,
    parse_frame,
)


class TestBuildAndParse:
    def test_set_twist_round_trip(self):
        pkt = build_set_twist(seq=0, v_mm_s=100, w_mrad_s=500)
        assert pkt[-1:] == b"\x00"  # ends with delimiter
        frame = pkt[:-1]  # strip delimiter
        parsed = parse_frame(frame)
        assert parsed.pkt_type == CmdType.SET_TWIST
        assert parsed.seq == 0
        v, w = struct.unpack("<hh", parsed.payload)
        assert v == 100
        assert w == 500

    def test_set_twist_negative(self):
        pkt = build_set_twist(seq=5, v_mm_s=-200, w_mrad_s=-1000)
        parsed = parse_frame(pkt[:-1])
        v, w = struct.unpack("<hh", parsed.payload)
        assert v == -200
        assert w == -1000

    def test_stop_round_trip(self):
        pkt = build_stop(seq=10, reason=1)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == CmdType.STOP
        assert parsed.payload == b"\x01"

    def test_estop_round_trip(self):
        pkt = build_estop(seq=99)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == CmdType.ESTOP
        assert parsed.seq == 99
        assert parsed.payload == b""

    def test_clear_faults_round_trip(self):
        pkt = build_clear_faults(seq=7, mask=0x0003)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == CmdType.CLEAR_FAULTS
        mask = struct.unpack("<H", parsed.payload)[0]
        assert mask == 0x0003

    def test_seq_wraps(self):
        pkt = build_set_twist(seq=255, v_mm_s=0, w_mrad_s=0)
        parsed = parse_frame(pkt[:-1])
        assert parsed.seq == 255

        pkt = build_set_twist(seq=256, v_mm_s=0, w_mrad_s=0)
        parsed = parse_frame(pkt[:-1])
        assert parsed.seq == 0  # wraps


class TestStatePayload:
    def test_unpack(self):
        data = struct.pack("<hhhHHHBH", -100, 150, -500, 7400, 0x0003, 1234, 0, 7194)
        state = StatePayload.unpack(data)
        assert state.speed_l_mm_s == -100
        assert state.speed_r_mm_s == 150
        assert state.gyro_z_mrad_s == -500
        assert state.battery_mv == 7400
        assert state.fault_flags == 0x0003
        assert state.range_mm == 1234
        assert state.range_status == 0
        assert state.echo_us == 7194

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            StatePayload.unpack(b"\x00" * 10)


class TestStateTelemetryPacket:
    def test_build_and_parse_state(self):
        payload = struct.pack("<hhhHHHBH", 100, 110, 50, 7200, 0, 500, 0, 2915)
        pkt = build_packet(TelType.STATE, 42, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == TelType.STATE
        assert parsed.seq == 42
        state = StatePayload.unpack(parsed.payload)
        assert state.speed_l_mm_s == 100
        assert state.speed_r_mm_s == 110
        assert state.range_mm == 500
        assert state.echo_us == 2915


class TestCrcValidation:
    def test_corrupted_frame_rejected(self):
        pkt = build_set_twist(seq=0, v_mm_s=100, w_mrad_s=0)
        frame = bytearray(pkt[:-1])
        # Flip a bit in the middle of the COBS-encoded data
        if len(frame) > 3:
            frame[3] ^= 0x01
        with pytest.raises(ValueError):
            parse_frame(bytes(frame))

    def test_truncated_frame_rejected(self):
        with pytest.raises(ValueError):
            parse_frame(b"\x02\x10")  # too short after COBS decode


class TestFaultFlags:
    def test_individual_faults(self):
        assert Fault.CMD_TIMEOUT == 0x0001
        assert Fault.ESTOP == 0x0002
        assert Fault.OBSTACLE == 0x0040

    def test_combined(self):
        flags = Fault.ESTOP | Fault.TILT
        assert flags & Fault.ESTOP
        assert flags & Fault.TILT
        assert not (flags & Fault.STALL)
