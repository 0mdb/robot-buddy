"""Tests for FaceClient — mock transport drives telemetry and commands."""

import struct

from supervisor.devices.face_client import FaceClient
from supervisor.devices.protocol import (
    FaceButtonEventType,
    FaceCmdType,
    FaceGesture,
    FaceMood,
    FaceTelType,
    TouchEventType,
    parse_frame,
    ParsedPacket,
)


class FakeTransport:
    """Minimal mock of SerialTransport for unit testing."""

    def __init__(self) -> None:
        self.connected = True
        self.written: list[bytes] = []
        self._on_packet = None
        self._debug = {"connected": True, "rx_bytes": 0, "tx_bytes": 0}

    def on_packet(self, cb):
        self._on_packet = cb

    def write(self, data: bytes) -> bool:
        self.written.append(data)
        return True

    def inject_packet(self, pkt: ParsedPacket) -> None:
        if self._on_packet:
            self._on_packet(pkt)

    def debug_snapshot(self) -> dict:
        return dict(self._debug)


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
        assert intensity == 127
        assert brightness == 204

    def test_send_state_gaze_scaling(self):
        self.client.send_state(gaze_x=1.0, gaze_y=-1.0)
        parsed = parse_frame(self.transport.written[0][:-1])
        _, _, gx, gy, _ = struct.unpack("<BBbbB", parsed.payload)
        assert gx == 32
        assert gy == -32

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

    def test_send_talking(self):
        self.client.send_talking(True, 150)
        parsed = parse_frame(self.transport.written[0][:-1])
        assert parsed.pkt_type == FaceCmdType.SET_TALKING
        talking, energy = struct.unpack("<BB", parsed.payload)
        assert talking == 1
        assert energy == 150

    def test_no_send_when_disconnected(self):
        self.transport.connected = False
        self.client.send_state(emotion_id=1)
        self.client.send_gesture(0)
        self.client.send_system_mode(1)
        self.client.send_talking(True, 10)
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
        payload = struct.pack("<BBBB", FaceMood.ANGRY, FaceGesture.RAGE, 0, 0x07)
        pkt = ParsedPacket(pkt_type=FaceTelType.FACE_STATUS, seq=5, payload=payload)
        self.transport.inject_packet(pkt)

        t = self.client.telemetry
        assert t.mood_id == FaceMood.ANGRY
        assert t.active_gesture == FaceGesture.RAGE
        assert t.system_mode == 0
        assert t.touch_active is True
        assert t.talking is True
        assert t.ptt_listening is True
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
        self.client.subscribe_touch(lambda evt: events.append(evt))
        payload = struct.pack("<BHH", TouchEventType.RELEASE, 50, 75)
        pkt = ParsedPacket(pkt_type=FaceTelType.TOUCH_EVENT, seq=1, payload=payload)
        self.transport.inject_packet(pkt)
        assert len(events) == 1
        assert events[0].event_type == TouchEventType.RELEASE
        assert events[0].x == 50

    def test_button_event_updates_last_button(self):
        payload = struct.pack("<BBBB", 0, FaceButtonEventType.TOGGLE, 1, 0)
        pkt = ParsedPacket(pkt_type=FaceTelType.BUTTON_EVENT, seq=8, payload=payload)
        self.transport.inject_packet(pkt)
        assert self.client.last_button is not None
        assert self.client.last_button.button_id == 0
        assert self.client.last_button.event_type == FaceButtonEventType.TOGGLE
        assert self.client.last_button.state == 1

    def test_button_callback_fires(self):
        events = []
        self.client.subscribe_button(lambda evt: events.append(evt))
        payload = struct.pack("<BBBB", 1, FaceButtonEventType.CLICK, 0, 0)
        pkt = ParsedPacket(pkt_type=FaceTelType.BUTTON_EVENT, seq=9, payload=payload)
        self.transport.inject_packet(pkt)
        assert len(events) == 1
        assert events[0].button_id == 1
        assert events[0].event_type == FaceButtonEventType.CLICK

    def test_button_callbacks_fan_out_to_multiple_subscribers(self):
        events_a = []
        events_b = []
        self.client.subscribe_button(lambda evt: events_a.append(evt))
        self.client.subscribe_button(lambda evt: events_b.append(evt))
        payload = struct.pack("<BBBB", 1, FaceButtonEventType.CLICK, 1, 0)
        pkt = ParsedPacket(pkt_type=FaceTelType.BUTTON_EVENT, seq=11, payload=payload)
        self.transport.inject_packet(pkt)
        assert len(events_a) == 1
        assert len(events_b) == 1

    def test_heartbeat_updates_last_heartbeat(self):
        payload = struct.pack(
            "<IIIIIIIIIIIIIIIIBBBB",
            2000,
            80,
            2,
            5,
            50,
            5000,
            4900,
            3,
            47,
            2,
            0,
            0,
            61,
            777,
            1,
            4,
            1,
            1,
            1,
            0,
        )
        pkt = ParsedPacket(pkt_type=FaceTelType.HEARTBEAT, seq=10, payload=payload)
        self.transport.inject_packet(pkt)
        hb = self.client.last_heartbeat
        assert hb is not None
        assert hb.button_tx_count == 5
        assert hb.usb_tx_calls == 50
        assert hb.usb_rx_bytes == 777
        assert hb.usb_dtr is True
        assert hb.usb_rts is True
        assert hb.ptt_listening is True
        assert hb.seq == 10

    def test_bad_button_payload_ignored(self):
        pkt = ParsedPacket(pkt_type=FaceTelType.BUTTON_EVENT, seq=0, payload=b"\x00")
        self.transport.inject_packet(pkt)
        assert self.client.last_button is None

    def test_bad_heartbeat_payload_ignored(self):
        pkt = ParsedPacket(pkt_type=FaceTelType.HEARTBEAT, seq=0, payload=b"\x00\x01")
        self.transport.inject_packet(pkt)
        assert self.client.last_heartbeat is None

    def test_bad_status_payload_ignored(self):
        pkt = ParsedPacket(pkt_type=FaceTelType.FACE_STATUS, seq=0, payload=b"\x00")
        self.transport.inject_packet(pkt)
        assert self.client.telemetry.mood_id == 0

    def test_unknown_packet_type_ignored(self):
        pkt = ParsedPacket(pkt_type=0xFE, seq=0, payload=b"")
        self.transport.inject_packet(pkt)

    def test_debug_snapshot_contains_transport(self):
        snap = self.client.debug_snapshot()
        assert "transport" in snap
        assert snap["connected"] is True
        assert "last_button" in snap
        assert "last_heartbeat" in snap
        assert "rx_heartbeat_packets" in snap
