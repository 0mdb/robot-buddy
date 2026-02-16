"""Tests for FaceClient — mock transport drives telemetry and commands."""

import struct

from supervisor.devices.face_client import FaceClient, FaceTelemetry, TouchEvent
from supervisor.devices.protocol import (
    FaceCmdType,
    FaceGesture,
    FaceMood,
    FaceStatusPayload,
    FaceTelType,
    TouchEventPayload,
    TouchEventType,
    build_packet,
    parse_frame,
    ParsedPacket,
)


class FakeTransport:
    """Minimal mock of SerialTransport for unit testing."""

    def __init__(self) -> None:
        self.connected = True
        self.written: list[bytes] = []
        self._on_packet = None

    def on_packet(self, cb):
        self._on_packet = cb

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def inject_packet(self, pkt: ParsedPacket) -> None:
        if self._on_packet:
            self._on_packet(pkt)


class TestFaceClientCommands:
    def setup_method(self):
        self.transport = FakeTransport()
        self.client = FaceClient(self.transport)

    def test_send_state_builds_correct_packet(self):
        self.client.send_state(emotion_id=FaceMood.HAPPY, intensity=0.5, brightness=0.8)
        assert len(self.transport.written) == 1
        pkt = self.transport.written[0]
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == FaceCmdType.SET_STATE
        mood, intensity, gx, gy, brightness = struct.unpack("<BBbbB", parsed.payload)
        assert mood == FaceMood.HAPPY
        assert intensity == 127  # 0.5 * 255 ≈ 127
        assert brightness == 204  # 0.8 * 255 ≈ 204

    def test_send_state_gaze_scaling(self):
        self.client.send_state(gaze_x=1.0, gaze_y=-1.0)
        parsed = parse_frame(self.transport.written[0][:-1])
        _, _, gx, gy, _ = struct.unpack("<BBbbB", parsed.payload)
        assert gx == 32  # 1.0 * 32
        assert gy == -32  # -1.0 * 32

    def test_send_state_clamps_intensity(self):
        self.client.send_state(intensity=2.0)
        parsed = parse_frame(self.transport.written[0][:-1])
        _, intensity, _, _, _ = struct.unpack("<BBbbB", parsed.payload)
        assert intensity == 255

    def test_send_gesture(self):
        self.client.send_gesture(FaceGesture.HEART, duration_ms=500)
        parsed = parse_frame(self.transport.written[0][:-1])
        assert parsed.pkt_type == FaceCmdType.GESTURE
        gid, dur = struct.unpack("<BH", parsed.payload)
        assert gid == FaceGesture.HEART
        assert dur == 500

    def test_send_system_mode(self):
        self.client.send_system_mode(mode=2, param=10)
        parsed = parse_frame(self.transport.written[0][:-1])
        assert parsed.pkt_type == FaceCmdType.SET_SYSTEM
        mode, _, param = struct.unpack("<BBB", parsed.payload)
        assert mode == 2
        assert param == 10

    def test_no_send_when_disconnected(self):
        self.transport.connected = False
        self.client.send_state(emotion_id=1)
        self.client.send_gesture(0)
        self.client.send_system_mode(1)
        assert len(self.transport.written) == 0

    def test_seq_increments(self):
        self.client.send_state()
        self.client.send_state()
        self.client.send_gesture(0)
        p0 = parse_frame(self.transport.written[0][:-1])
        p1 = parse_frame(self.transport.written[1][:-1])
        p2 = parse_frame(self.transport.written[2][:-1])
        assert p0.seq == 0
        assert p1.seq == 1
        assert p2.seq == 2


class TestFaceClientTelemetry:
    def setup_method(self):
        self.transport = FakeTransport()
        self.client = FaceClient(self.transport)

    def test_face_status_updates_telemetry(self):
        payload = struct.pack("<BBBB", FaceMood.ANGRY, FaceGesture.RAGE, 0, 0x01)
        pkt = ParsedPacket(pkt_type=FaceTelType.FACE_STATUS, seq=5, payload=payload)
        self.transport.inject_packet(pkt)

        t = self.client.telemetry
        assert t.mood_id == FaceMood.ANGRY
        assert t.active_gesture == FaceGesture.RAGE
        assert t.system_mode == 0
        assert t.touch_active is True
        assert t.seq == 5

    def test_touch_event_updates_last_touch(self):
        payload = struct.pack("<BHH", TouchEventType.PRESS, 100, 200)
        pkt = ParsedPacket(pkt_type=FaceTelType.TOUCH_EVENT, seq=3, payload=payload)
        self.transport.inject_packet(pkt)

        assert self.client.last_touch is not None
        assert self.client.last_touch.event_type == TouchEventType.PRESS
        assert self.client.last_touch.x == 100
        assert self.client.last_touch.y == 200

    def test_touch_callback_fires(self):
        events = []
        self.client.on_touch(lambda evt: events.append(evt))

        payload = struct.pack("<BHH", TouchEventType.RELEASE, 50, 75)
        pkt = ParsedPacket(pkt_type=FaceTelType.TOUCH_EVENT, seq=1, payload=payload)
        self.transport.inject_packet(pkt)

        assert len(events) == 1
        assert events[0].event_type == TouchEventType.RELEASE
        assert events[0].x == 50

    def test_bad_status_payload_ignored(self):
        pkt = ParsedPacket(pkt_type=FaceTelType.FACE_STATUS, seq=0, payload=b"\x00")
        self.transport.inject_packet(pkt)
        # Telemetry should remain at defaults
        assert self.client.telemetry.mood_id == 0

    def test_unknown_packet_type_ignored(self):
        pkt = ParsedPacket(pkt_type=0xFE, seq=0, payload=b"")
        self.transport.inject_packet(pkt)  # should not raise


class TestFaceTelemetryProperties:
    def test_touch_active_flag(self):
        t = FaceTelemetry(flags=0x01)
        assert t.touch_active is True
        assert t.audio_playing is False

    def test_audio_playing_flag(self):
        t = FaceTelemetry(flags=0x02)
        assert t.touch_active is False
        assert t.audio_playing is True

    def test_both_flags(self):
        t = FaceTelemetry(flags=0x03)
        assert t.touch_active is True
        assert t.audio_playing is True

    def test_no_flags(self):
        t = FaceTelemetry(flags=0)
        assert t.touch_active is False
        assert t.audio_playing is False
