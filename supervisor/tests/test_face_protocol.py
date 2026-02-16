"""Tests for face protocol packet building and parsing."""

import struct

import pytest

from supervisor.devices.protocol import (
    FaceCmdType,
    FaceGesture,
    FaceMood,
    FaceStatusPayload,
    FaceSystemMode,
    FaceTelType,
    TouchEventPayload,
    TouchEventType,
    build_face_gesture,
    build_face_set_state,
    build_face_set_system,
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


class TestFaceStatusPayload:
    def test_unpack(self):
        data = struct.pack("<BBBB", FaceMood.TIRED, 0xFF, FaceSystemMode.NONE, 0x03)
        status = FaceStatusPayload.unpack(data)
        assert status.mood_id == FaceMood.TIRED
        assert status.active_gesture == 0xFF
        assert status.system_mode == FaceSystemMode.NONE
        assert status.flags == 0x03

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            FaceStatusPayload.unpack(b"\x00\x00")

    def test_as_telemetry_packet(self):
        payload = struct.pack("<BBBB", FaceMood.HAPPY, FaceGesture.LAUGH, 0, 0x01)
        pkt = build_packet(FaceTelType.FACE_STATUS, 10, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceTelType.FACE_STATUS
        status = FaceStatusPayload.unpack(parsed.payload)
        assert status.mood_id == FaceMood.HAPPY
        assert status.active_gesture == FaceGesture.LAUGH
        assert status.flags == 0x01


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


class TestFaceEnums:
    def test_mood_values(self):
        assert FaceMood.DEFAULT == 0
        assert FaceMood.TIRED == 1
        assert FaceMood.ANGRY == 2
        assert FaceMood.HAPPY == 3

    def test_gesture_values(self):
        assert FaceGesture.BLINK == 0
        assert FaceGesture.RAGE == 9

    def test_system_mode_values(self):
        assert FaceSystemMode.NONE == 0
        assert FaceSystemMode.SHUTTING_DOWN == 5

    def test_command_ids_in_face_range(self):
        for cmd in FaceCmdType:
            assert 0x20 <= cmd <= 0x2F

    def test_telemetry_ids_in_face_range(self):
        for tel in FaceTelType:
            assert 0x90 <= tel <= 0x9F
