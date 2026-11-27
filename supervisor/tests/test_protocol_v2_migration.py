"""v2 migration (PROTOCOL.md 3.2, amended 2026-11-27): handshake after open, ACK in either
envelope, v2 commands after the handshake, exact STATE lengths, re-negotiation on desync.
The end-to-end tests run SerialTransport + ReflexClient against the v2-only MockReflex."""

from __future__ import annotations

import asyncio
import struct

import pytest

from supervisor.devices.face_client import FaceClient
from supervisor.devices.protocol import (
    COMMON_PROTOCOL_VERSION_ACK,
    CmdType,
    StatePayload,
    TelType,
    build_command,
    build_face_gesture,
    build_packet,
    build_packet_v2,
    build_set_twist,
    parse_frame,
)
from supervisor.devices.reflex_client import ReflexClient
from supervisor.io.serial_transport import SerialTransport
from supervisor.mock.mock_reflex import MockReflex

_STATE_V1 = struct.pack("<hhhhhhHHB", 1, 2, 3, 4, 5, 6, 7, 8, 0)
_STATE_V2 = _STATE_V1 + struct.pack("<II", 4242, 99)


class TestAckEitherEnvelope:
    def test_v2_ack_parsed_while_at_v1(self):
        # What both ESP32s send: they switch first, then ACK in v2.
        frame = build_packet_v2(COMMON_PROTOCOL_VERSION_ACK, 0x0102, 77, bytes([2]))
        p = parse_frame(frame[:-1], protocol_version=1)
        assert (p.pkt_type, p.payload, p.seq, p.t_src_us) == (
            COMMON_PROTOCOL_VERSION_ACK,
            bytes([2]),
            0x0102,
            77,
        )

    def test_v1_ack_still_parsed(self):
        frame = build_packet(COMMON_PROTOCOL_VERSION_ACK, 5, bytes([2]))
        p = parse_frame(frame[:-1], protocol_version=1)
        assert (p.pkt_type, p.payload, p.seq) == (
            COMMON_PROTOCOL_VERSION_ACK,
            bytes([2]),
            5,
        )

    def test_other_v2_frames_not_reinterpreted_at_v1(self):
        # Only the ACK gets the special case: a v2 STATE read at v1 stays a (wrong) v1 parse,
        # which the exact STATE length check then rejects.
        frame = build_packet_v2(TelType.STATE, 1, 2, _STATE_V2)
        p = parse_frame(frame[:-1], protocol_version=1)
        with pytest.raises(ValueError):
            StatePayload.unpack(p.payload, protocol_version=1)


class TestEnvelopeBuilders:
    def test_default_is_v1(self):
        assert build_set_twist(3, 10, -20) == build_packet(
            CmdType.SET_TWIST, 3, struct.pack("<hh", 10, -20)
        )

    def test_v2_twist(self):
        pkt = build_set_twist(70000, 10, -20, protocol_version=2, t_src_us=5)
        p = parse_frame(pkt[:-1], protocol_version=2)
        assert (p.pkt_type, p.seq, p.t_src_us, p.payload) == (
            CmdType.SET_TWIST,
            70000,
            5,
            struct.pack("<hh", 10, -20),
        )

    def test_v2_default_timestamp_is_monotonic_us(self):
        pkt = build_command(CmdType.ESTOP, 1, protocol_version=2)
        p = parse_frame(pkt[:-1], protocol_version=2)
        assert p.t_src_us > 0

    def test_v2_face_command(self):
        pkt = build_face_gesture(9, 3, 250, protocol_version=2, t_src_us=1)
        p = parse_frame(pkt[:-1], protocol_version=2)
        assert (p.seq, p.payload) == (9, struct.pack("<BH", 3, 250))


class TestStateLength:
    def test_exact_v1(self):
        s = StatePayload.unpack(_STATE_V1, protocol_version=1)
        assert (s.speed_l_mm_s, s.cmd_seq_last_applied) == (1, 0)

    def test_exact_v2_tail(self):
        s = StatePayload.unpack(_STATE_V2, protocol_version=2)
        assert (s.cmd_seq_last_applied, s.t_cmd_applied_us) == (4242, 99)

    @pytest.mark.parametrize(
        ("data", "version"),
        [(_STATE_V2, 1), (_STATE_V1, 2), (_STATE_V1 + b"\x00", 1)],
    )
    def test_wrong_length_rejected(self, data: bytes, version: int):
        with pytest.raises(ValueError):
            StatePayload.unpack(data, protocol_version=version)

    def test_legacy_call_without_version(self):
        assert StatePayload.unpack(_STATE_V2).cmd_seq_last_applied == 4242


class _FakeTransport:
    def __init__(self, version: int) -> None:
        self.protocol_version = version
        self.sent: list[bytes] = []
        self.renegotiations = 0
        self.connected = True

    def on_packet(self, cb) -> None:  # noqa: ANN001
        self.cb = cb

    def write(self, data: bytes) -> bool:
        self.sent.append(data)
        return True

    def request_renegotiate(self) -> None:
        self.renegotiations += 1


class TestClientsFollowVersion:
    def test_reflex_twist_v2(self):
        t = _FakeTransport(2)
        ReflexClient(t).send_twist(100, 0)  # type: ignore[arg-type]
        p = parse_frame(t.sent[0][:-1], protocol_version=2)
        assert p.pkt_type == CmdType.SET_TWIST and p.t_src_us > 0

    def test_face_v2(self):
        t = _FakeTransport(2)
        FaceClient(t).send_gesture(1, 100)  # type: ignore[arg-type]
        assert len(t.sent[0]) > 15  # v2 header present

    def test_desync_triggers_renegotiate(self):
        t = _FakeTransport(1)
        client = ReflexClient(t)  # type: ignore[arg-type]
        frame = build_packet_v2(TelType.STATE, 1, 2, _STATE_V2)
        for _ in range(3):
            t.cb(parse_frame(frame[:-1], protocol_version=1))
        assert t.renegotiations == 1
        assert client.telemetry.speed_l_mm_s == 0  # garbage never applied


# ── End to end against the v2-only mock ─────────────────────────────


async def _wait(cond, timeout_s: float = 3.0) -> bool:  # noqa: ANN001
    for _ in range(int(timeout_s / 0.02)):
        if cond():
            return True
        await asyncio.sleep(0.02)
    return cond()


@pytest.fixture
def mock():
    m = MockReflex()
    m.start()
    yield m
    m.stop()


async def test_auto_negotiates_after_open(mock: MockReflex):
    transport = SerialTransport(mock.device_path, label="reflex")
    client = ReflexClient(transport)
    await transport.start()
    try:
        assert await _wait(lambda: transport.protocol_version == 2)
        assert await _wait(lambda: client.telemetry.seq > 0)
        client.send_clear_faults()
        client.send_twist(150, 0)
        seq = client.last_cmd_seq
        assert await _wait(lambda: client.telemetry.cmd_seq_last_applied == seq)
        assert client.debug_snapshot()["rx_bad_payload_packets"] <= 3
    finally:
        await transport.stop()


async def test_recovers_from_desync(mock: MockReflex):
    transport = SerialTransport(mock.device_path, label="reflex")
    client = ReflexClient(transport)
    await transport.start()
    try:
        assert await _wait(lambda: transport.protocol_version == 2)
        transport.protocol_version = 1  # as after a lost ACK or a supervisor-side reset
        n = transport.negotiations
        assert await _wait(lambda: transport.negotiations > n)
        assert await _wait(lambda: transport.protocol_version == 2)
        rx = client.debug_snapshot()["rx_state_packets"]
        assert await _wait(lambda: client.debug_snapshot()["rx_state_packets"] > rx)
    finally:
        await transport.stop()
