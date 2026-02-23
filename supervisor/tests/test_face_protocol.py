"""Tests for face protocol SET_CONV_STATE builder and FaceClient.send_conv_state."""

from __future__ import annotations

import struct
from typing import Callable

from supervisor.devices.face_client import FaceClient
from supervisor.devices.protocol import (
    FaceCmdType,
    FaceConvState,
    ParsedPacket,
    build_face_set_conv_state,
    parse_frame,
)


# ── Protocol builder tests ───────────────────────────────────────────


class TestBuildFaceSetConvState:
    """Verify SET_CONV_STATE packet builder."""

    def test_packet_type_byte(self):
        """Built packet must contain type byte 0x25."""
        pkt = build_face_set_conv_state(seq=0, conv_state=FaceConvState.LISTENING)
        # COBS-encoded, so parse it back
        frame = pkt[:-1]  # strip trailing 0x00 delimiter
        parsed = parse_frame(frame)
        assert parsed.pkt_type == 0x25

    def test_round_trip_all_states(self):
        """Build and parse each conversation state, verify payload matches."""
        for state in FaceConvState:
            pkt = build_face_set_conv_state(seq=42, conv_state=int(state))
            frame = pkt[:-1]
            parsed = parse_frame(frame)
            assert parsed.pkt_type == FaceCmdType.SET_CONV_STATE
            assert parsed.seq == 42
            assert len(parsed.payload) == 1
            assert parsed.payload[0] == state

    def test_payload_format(self):
        """Payload must be a single byte matching the conv_state value."""
        pkt = build_face_set_conv_state(seq=7, conv_state=5)
        frame = pkt[:-1]
        parsed = parse_frame(frame)
        (value,) = struct.unpack("<B", parsed.payload)
        assert value == 5

    def test_conv_state_masked(self):
        """Values > 255 should be masked to u8."""
        pkt = build_face_set_conv_state(seq=0, conv_state=0x105)
        frame = pkt[:-1]
        parsed = parse_frame(frame)
        assert parsed.payload[0] == 0x05


# ── FaceClient.send_conv_state tests ─────────────────────────────────


class FakeTransport:
    """Minimal mock of SerialTransport for FaceClient testing."""

    def __init__(self) -> None:
        self.connected = True
        self.written: list[bytes] = []
        self._handlers: list[Callable[[ParsedPacket], None]] = []

    def on_packet(self, cb: Callable[[ParsedPacket], None]) -> None:
        self._handlers.append(cb)

    def write(self, data: bytes) -> bool:
        self.written.append(data)
        return True


class TestFaceClientSendConvState:
    """Verify FaceClient.send_conv_state sends correct packets."""

    def test_sends_packet(self):
        transport = FakeTransport()
        client = FaceClient(transport)
        client.send_conv_state(int(FaceConvState.THINKING))
        assert len(transport.written) == 1

    def test_packet_parses_correctly(self):
        transport = FakeTransport()
        client = FaceClient(transport)
        client.send_conv_state(int(FaceConvState.SPEAKING))
        pkt_bytes = transport.written[0]
        frame = pkt_bytes[:-1]
        parsed = parse_frame(frame)
        assert parsed.pkt_type == FaceCmdType.SET_CONV_STATE
        assert parsed.payload[0] == FaceConvState.SPEAKING

    def test_no_send_when_disconnected(self):
        transport = FakeTransport()
        transport.connected = False
        client = FaceClient(transport)
        client.send_conv_state(int(FaceConvState.LISTENING))
        assert len(transport.written) == 0

    def test_increments_tx_packets(self):
        transport = FakeTransport()
        client = FaceClient(transport)
        before = client._tx_packets
        client.send_conv_state(int(FaceConvState.IDLE))
        assert client._tx_packets == before + 1
