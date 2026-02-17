"""Tests for face protocol packet building and parsing."""

import struct

import pytest

from supervisor.devices.protocol import (
    FaceCmdType,
    FaceCfgId,
    FaceHeartbeatPayload,
    FaceMicProbePayload,
    FaceGesture,
    FaceMood,
    FaceStatusPayload,
    FaceSystemMode,
    FaceTelType,
    TouchEventPayload,
    TouchEventType,
    build_face_set_config,
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


class TestFaceSetConfig:
    def test_round_trip_tone_ms(self):
        pkt = build_face_set_config(seq=4, param_id=FaceCfgId.AUDIO_TEST_TONE_MS, value_u32=1500)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.SET_CONFIG
        assert parsed.seq == 4
        param_id, value = struct.unpack("<B4s", parsed.payload)
        assert param_id == FaceCfgId.AUDIO_TEST_TONE_MS
        assert struct.unpack("<I", value)[0] == 1500

    def test_round_trip_reg_dump(self):
        pkt = build_face_set_config(seq=9, param_id=FaceCfgId.AUDIO_REG_DUMP, value_u32=0)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.SET_CONFIG
        param_id, value = struct.unpack("<B4s", parsed.payload)
        assert param_id == FaceCfgId.AUDIO_REG_DUMP
        assert struct.unpack("<I", value)[0] == 0


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


class TestMicProbePayload:
    def test_unpack(self):
        data = struct.pack(
            "<IIIHHHHhBB",
            7,      # probe_seq
            3000,   # duration_ms
            1234,   # sample_count
            5,      # read_timeouts
            1,      # read_errors
            3210,   # selected_rms_x10
            1450,   # selected_peak
            -123,   # selected_dbfs_x10
            2,      # selected_channel
            1,      # active
        )
        mp = FaceMicProbePayload.unpack(data)
        assert mp.probe_seq == 7
        assert mp.duration_ms == 3000
        assert mp.sample_count == 1234
        assert mp.read_timeouts == 5
        assert mp.read_errors == 1
        assert mp.selected_rms_x10 == 3210
        assert mp.selected_peak == 1450
        assert mp.selected_dbfs_x10 == -123
        assert mp.selected_channel == 2
        assert mp.active == 1

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            FaceMicProbePayload.unpack(b"\x00\x01")

    def test_as_telemetry_packet(self):
        payload = struct.pack("<IIIHHHHhBB", 1, 2000, 800, 2, 0, 900, 500, -180, 1, 0)
        pkt = build_packet(FaceTelType.MIC_PROBE, 12, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceTelType.MIC_PROBE
        mp = FaceMicProbePayload.unpack(parsed.payload)
        assert mp.probe_seq == 1
        assert mp.selected_channel == 1
        assert mp.active == 0


class TestHeartbeatPayload:
    def test_unpack(self):
        data = struct.pack(
            "<IIIIB",
            12345,  # uptime_ms
            77,     # status_tx_count
            3,      # touch_tx_count
            5,      # mic_probe_seq
            1,      # mic_activity
        )
        hb = FaceHeartbeatPayload.unpack(data)
        assert hb.uptime_ms == 12345
        assert hb.status_tx_count == 77
        assert hb.touch_tx_count == 3
        assert hb.mic_probe_seq == 5
        assert hb.mic_activity == 1
        assert hb.usb_tx_calls == 0
        assert hb.usb_tx_bytes_requested == 0
        assert hb.usb_dtr == 0
        assert hb.usb_rts == 0

    def test_unpack_with_usb_diag_extension(self):
        base = struct.pack("<IIIIB", 12345, 77, 3, 5, 1)
        usb = struct.pack(
            "<IIIIIIIIIIIIBB",
            10,    # usb_tx_calls
            1100,  # usb_tx_bytes_requested
            1000,  # usb_tx_bytes_queued
            2,     # usb_tx_short_writes
            9,     # usb_tx_flush_ok
            1,     # usb_tx_flush_not_finished
            0,     # usb_tx_flush_timeout
            0,     # usb_tx_flush_error
            55,    # usb_rx_calls
            321,   # usb_rx_bytes
            4,     # usb_rx_errors
            3,     # usb_line_state_events
            1,     # usb_dtr
            1,     # usb_rts
        )
        hb = FaceHeartbeatPayload.unpack(base + usb)
        assert hb.usb_tx_calls == 10
        assert hb.usb_tx_bytes_requested == 1100
        assert hb.usb_tx_bytes_queued == 1000
        assert hb.usb_tx_short_writes == 2
        assert hb.usb_tx_flush_ok == 9
        assert hb.usb_tx_flush_not_finished == 1
        assert hb.usb_rx_bytes == 321
        assert hb.usb_line_state_events == 3
        assert hb.usb_dtr == 1
        assert hb.usb_rts == 1

    def test_unpack_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            FaceHeartbeatPayload.unpack(b"\x00\x01")

    def test_as_telemetry_packet(self):
        payload = struct.pack("<IIIIB", 5000, 100, 2, 9, 0)
        pkt = build_packet(FaceTelType.HEARTBEAT, 18, payload)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceTelType.HEARTBEAT
        hb = FaceHeartbeatPayload.unpack(parsed.payload)
        assert hb.uptime_ms == 5000
        assert hb.status_tx_count == 100
        assert hb.mic_activity == 0


class TestFaceEnums:
    def test_mood_values(self):
        assert FaceMood.NEUTRAL == 0
        assert FaceMood.HAPPY == 1
        assert FaceMood.EXCITED == 2
        assert FaceMood.CURIOUS == 3
        assert FaceMood.SAD == 4
        assert FaceMood.SCARED == 5
        assert FaceMood.ANGRY == 6
        assert FaceMood.SURPRISED == 7
        assert FaceMood.SLEEPY == 8
        assert FaceMood.LOVE == 9
        assert FaceMood.SILLY == 10
        assert FaceMood.THINKING == 11

    def test_gesture_values(self):
        assert FaceGesture.BLINK == 0
        assert FaceGesture.RAGE == 9
        assert FaceGesture.NOD == 10
        assert FaceGesture.HEADSHAKE == 11
        assert FaceGesture.WIGGLE == 12

    def test_system_mode_values(self):
        assert FaceSystemMode.NONE == 0
        assert FaceSystemMode.SHUTTING_DOWN == 5

    def test_command_ids_in_face_range(self):
        for cmd in FaceCmdType:
            assert 0x20 <= cmd <= 0x2F

    def test_telemetry_ids_in_face_range(self):
        for tel in FaceTelType:
            assert 0x90 <= tel <= 0x9F
