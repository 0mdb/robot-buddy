"""Tests for face protocol packet building and parsing."""

import struct

import pytest

from supervisor.devices.protocol import (
    FaceButtonEventPayload,
    FaceButtonEventType,
    FaceCmdType,
    FaceGesture,
    FaceHeartbeatPayload,
    FaceMood,
    FaceStatusPayload,
    FaceSystemMode,
    FaceTelType,
    TouchEventPayload,
    TouchEventType,
    build_face_gesture,
    build_face_set_state,
    build_face_set_system,
    build_face_set_talking,
    build_packet,
    parse_frame,
)


class TestFaceSetState:
    def test_round_trip(self):
        pkt = build_face_set_state(seq=1, mood_id=FaceMood.HAPPY, intensity=200)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.SET_STATE
        assert parsed.seq == 1
        mood, intensity, gaze_x, gaze_y, brightness = struct.unpack("<BBbbB", parsed.payload)
        assert mood == FaceMood.HAPPY
        assert intensity == 200

    def test_gaze_signed(self):
        pkt = build_face_set_state(seq=0, mood_id=0, gaze_x=-10, gaze_y=20)
        parsed = parse_frame(pkt[:-1])
        _, _, gx, gy, _ = struct.unpack("<BBbbB", parsed.payload)
        assert gx == -10
        assert gy == 20

    def test_defaults(self):
        pkt = build_face_set_state(seq=0, mood_id=0)
        parsed = parse_frame(pkt[:-1])
        mood, intensity, gx, gy, brightness = struct.unpack("<BBbbB", parsed.payload)
        assert mood == 0
        assert intensity == 255
        assert gx == 0
        assert gy == 0
        assert brightness == 200


class TestFaceGesture:
    def test_round_trip(self):
        pkt = build_face_gesture(seq=5, gesture_id=FaceGesture.WINK_L, duration_ms=300)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.GESTURE
        assert parsed.seq == 5
        gid, dur = struct.unpack("<BH", parsed.payload)
        assert gid == FaceGesture.WINK_L
        assert dur == 300

    def test_zero_duration(self):
        pkt = build_face_gesture(seq=0, gesture_id=FaceGesture.BLINK)
        parsed = parse_frame(pkt[:-1])
        gid, dur = struct.unpack("<BH", parsed.payload)
        assert gid == FaceGesture.BLINK
        assert dur == 0


class TestFaceSetSystem:
    def test_round_trip(self):
        pkt = build_face_set_system(seq=2, mode=FaceSystemMode.BOOTING, phase=1, param=42)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.SET_SYSTEM
        mode, phase, param = struct.unpack("<BBB", parsed.payload)
        assert mode == FaceSystemMode.BOOTING
        assert phase == 1
        assert param == 42


class TestFaceSetTalking:
    def test_round_trip(self):
        pkt = build_face_set_talking(seq=9, talking=True, energy=170)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.SET_TALKING
        talking, energy = struct.unpack("<BB", parsed.payload)
        assert talking == 1
        assert energy == 170

    def test_energy_clamped(self):
        pkt = build_face_set_talking(seq=9, talking=True, energy=999)
        parsed = parse_frame(pkt[:-1])
        _, energy = struct.unpack("<BB", parsed.payload)
        assert energy == 255


class TestFaceStatusPayload:
    def test_unpack(self):
        data = struct.pack("<BBBB", FaceMood.SLEEPY, 0xFF, FaceSystemMode.NONE, 0x03)
        status = FaceStatusPayload.unpack(data)
        assert status.mood_id == FaceMood.SLEEPY
        assert status.active_gesture == 0xFF
        assert status.system_mode == FaceSystemMode.NONE
        assert status.flags == 0x03

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            FaceStatusPayload.unpack(b"\x00\x00")

    def test_as_telemetry_packet(self):
        payload = struct.pack("<BBBB", FaceMood.HAPPY, FaceGesture.LAUGH, 0, 0x07)
        pkt = build_packet(FaceTelType.FACE_STATUS, 10, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceTelType.FACE_STATUS
        status = FaceStatusPayload.unpack(parsed.payload)
        assert status.flags == 0x07


class TestTouchEventPayload:
    def test_unpack(self):
        data = struct.pack("<BHH", TouchEventType.PRESS, 120, 160)
        te = TouchEventPayload.unpack(data)
        assert te.event_type == TouchEventType.PRESS
        assert te.x == 120
        assert te.y == 160

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            TouchEventPayload.unpack(b"\x00\x00")

    def test_as_telemetry_packet(self):
        payload = struct.pack("<BHH", TouchEventType.DRAG, 50, 200)
        pkt = build_packet(FaceTelType.TOUCH_EVENT, 7, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceTelType.TOUCH_EVENT
        te = TouchEventPayload.unpack(parsed.payload)
        assert te.event_type == TouchEventType.DRAG
        assert te.x == 50
        assert te.y == 200


class TestButtonEventPayload:
    def test_unpack(self):
        data = struct.pack("<BBBB", 0, FaceButtonEventType.TOGGLE, 1, 0)
        be = FaceButtonEventPayload.unpack(data)
        assert be.button_id == 0
        assert be.event_type == FaceButtonEventType.TOGGLE
        assert be.state == 1

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            FaceButtonEventPayload.unpack(b"\x00")

    def test_as_telemetry_packet(self):
        payload = struct.pack("<BBBB", 1, FaceButtonEventType.CLICK, 0, 0)
        pkt = build_packet(FaceTelType.BUTTON_EVENT, 12, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceTelType.BUTTON_EVENT
        be = FaceButtonEventPayload.unpack(parsed.payload)
        assert be.button_id == 1
        assert be.event_type == FaceButtonEventType.CLICK


class TestHeartbeatPayload:
    def test_unpack_base_only(self):
        data = struct.pack("<IIII", 12345, 77, 3, 2)
        hb = FaceHeartbeatPayload.unpack(data)
        assert hb.uptime_ms == 12345
        assert hb.status_tx_count == 77
        assert hb.touch_tx_count == 3
        assert hb.button_tx_count == 2
        assert hb.usb_tx_calls == 0
        assert hb.usb_dtr == 0
        assert hb.ptt_listening == 0

    def test_unpack_full(self):
        payload = struct.pack(
            "<IIIIIIIIIIIIIIIIBBBB",
            2000,  # uptime_ms
            80,    # status_tx_count
            2,     # touch_tx_count
            5,     # button_tx_count
            50,    # usb_tx_calls
            5000,  # usb_tx_bytes_requested
            4900,  # usb_tx_bytes_queued
            3,     # usb_tx_short_writes
            47,    # usb_tx_flush_ok
            2,     # usb_tx_flush_not_finished
            0,     # usb_tx_flush_timeout
            0,     # usb_tx_flush_error
            61,    # usb_rx_calls
            777,   # usb_rx_bytes
            1,     # usb_rx_errors
            4,     # usb_line_state_events
            1,     # usb_dtr
            1,     # usb_rts
            1,     # ptt_listening
            0,     # reserved
        )
        hb = FaceHeartbeatPayload.unpack(payload)
        assert hb.button_tx_count == 5
        assert hb.usb_tx_calls == 50
        assert hb.usb_rx_bytes == 777
        assert hb.usb_dtr == 1
        assert hb.usb_rts == 1
        assert hb.ptt_listening == 1

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            FaceHeartbeatPayload.unpack(b"\x00\x01")


class TestFaceEnums:
    def test_command_ids_in_face_range(self):
        for cmd in FaceCmdType:
            assert 0x20 <= cmd <= 0x2F

    def test_telemetry_ids_in_face_range(self):
        for tel in FaceTelType:
            assert 0x90 <= tel <= 0x9F
