"""Tests for protocol v2 builders, parsers, and version negotiation."""

from __future__ import annotations


from supervisor_v2.devices.protocol import (
    COMMON_SET_PROTOCOL_VERSION,
    ParsedPacket,
    build_packet,
    build_packet_v2,
    build_set_protocol_version,
    build_time_sync_req,
    parse_frame,
)


# ── v2 builder tests ────────────────────────────────────────────────


class TestBuildPacketV2:
    """Verify v2 packet envelope structure."""

    def test_round_trip(self):
        """Build v2 packet and parse it back, verify all fields."""
        pkt = build_packet_v2(0x42, seq=1000, t_src_us=123456789, payload=b"\xab\xcd")
        frame = pkt[:-1]  # strip trailing 0x00 delimiter
        parsed = parse_frame(frame, protocol_version=2)
        assert parsed.pkt_type == 0x42
        assert parsed.seq == 1000
        assert parsed.t_src_us == 123456789
        assert parsed.payload == b"\xab\xcd"

    def test_u32_seq_range(self):
        """Seq must support full u32 range."""
        for seq in (0, 0xFF, 0xFFFF, 0xFFFFFFFF):
            pkt = build_packet_v2(0x01, seq=seq, t_src_us=0)
            frame = pkt[:-1]
            parsed = parse_frame(frame, protocol_version=2)
            assert parsed.seq == seq

    def test_u64_t_src_us_range(self):
        """t_src_us must support large u64 values."""
        big_ts = 2**63 - 1  # max i64 (unsigned in practice)
        pkt = build_packet_v2(0x01, seq=0, t_src_us=big_ts)
        frame = pkt[:-1]
        parsed = parse_frame(frame, protocol_version=2)
        assert parsed.t_src_us == big_ts

    def test_empty_payload(self):
        """v2 packet with no payload should parse correctly."""
        pkt = build_packet_v2(0x10, seq=5, t_src_us=100)
        frame = pkt[:-1]
        parsed = parse_frame(frame, protocol_version=2)
        assert parsed.payload == b""
        assert parsed.seq == 5
        assert parsed.t_src_us == 100


# ── v1 builder backward compatibility ──────────────────────────────


class TestBuildPacketV1Compat:
    """Ensure v1 packets still parse correctly."""

    def test_v1_round_trip(self):
        """v1 build → parse should work as before."""
        pkt = build_packet(0x80, seq=42, payload=b"\x01\x02")
        frame = pkt[:-1]
        parsed = parse_frame(frame, protocol_version=1)
        assert parsed.pkt_type == 0x80
        assert parsed.seq == 42
        assert parsed.payload == b"\x01\x02"
        assert parsed.t_src_us == 0  # default

    def test_v1_default_protocol_version(self):
        """parse_frame with no protocol_version kwarg should default to v1."""
        pkt = build_packet(0x80, seq=7)
        frame = pkt[:-1]
        parsed = parse_frame(frame)
        assert parsed.seq == 7
        assert parsed.t_src_us == 0

    def test_v1_packet_parsed_as_v2_short_stays_v1(self):
        """If protocol_version=2 but packet is too short for v2, fallback to v1."""
        # A v1 packet (type + 1-byte seq + payload) with < 13 bytes body
        pkt = build_packet(0x01, seq=3, payload=b"\xaa")
        frame = pkt[:-1]
        parsed = parse_frame(frame, protocol_version=2)
        # Falls back to v1 parsing since body < _V2_HEADER_SIZE
        assert parsed.pkt_type == 0x01
        assert parsed.seq == 3


# ── SET_PROTOCOL_VERSION builder ──────────────────────────────────


class TestBuildSetProtocolVersion:
    """Verify SET_PROTOCOL_VERSION packet construction."""

    def test_packet_type(self):
        pkt = build_set_protocol_version(seq=0, version=2)
        frame = pkt[:-1]
        parsed = parse_frame(frame)
        assert parsed.pkt_type == COMMON_SET_PROTOCOL_VERSION

    def test_version_in_payload(self):
        pkt = build_set_protocol_version(seq=1, version=2)
        frame = pkt[:-1]
        parsed = parse_frame(frame)
        assert len(parsed.payload) == 1
        assert parsed.payload[0] == 2

    def test_version_1(self):
        pkt = build_set_protocol_version(seq=0, version=1)
        frame = pkt[:-1]
        parsed = parse_frame(frame)
        assert parsed.payload[0] == 1


# ── parse_frame v2 ─────────────────────────────────────────────────


class TestParseFrameV2:
    """Verify v2 parsing extracts the extended header correctly."""

    def test_crc_mismatch_raises(self):
        """Corrupted frame should raise ValueError."""
        pkt = build_packet_v2(0x01, seq=0, t_src_us=0, payload=b"\x00")
        frame = bytearray(pkt[:-1])
        # Flip a bit in the frame to corrupt it
        frame[1] ^= 0xFF
        try:
            parse_frame(bytes(frame), protocol_version=2)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_too_short_raises(self):
        """Frame decoding to < 4 bytes should raise ValueError."""
        # Minimal invalid: just a couple bytes that COBS-decode to < 4
        try:
            parse_frame(b"\x01", protocol_version=2)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


# ── build_time_sync_req v2 ─────────────────────────────────────────


class TestBuildTimeSyncReqV2:
    """Verify time sync request respects protocol_version parameter."""

    def test_v1_default(self):
        pkt = build_time_sync_req(seq=0, ping_seq=42)
        frame = pkt[:-1]
        parsed = parse_frame(frame, protocol_version=1)
        # v1 packet, should have seq=0, payload with ping_seq
        assert parsed.seq == 0

    def test_v2_has_t_src_us(self):
        pkt = build_time_sync_req(
            seq=100, ping_seq=42, protocol_version=2, t_src_us=999999
        )
        frame = pkt[:-1]
        parsed = parse_frame(frame, protocol_version=2)
        assert parsed.seq == 100
        assert parsed.t_src_us == 999999
        # Payload should still contain ping_seq + reserved
        assert len(parsed.payload) == 8  # u32 + u32


# ── ParsedPacket defaults ──────────────────────────────────────────


class TestParsedPacketDefaults:
    """Verify ParsedPacket field defaults."""

    def test_defaults(self):
        p = ParsedPacket(pkt_type=0, seq=0, payload=b"")
        assert p.t_src_us == 0
        assert p.t_pi_rx_ns == 0

    def test_t_pi_rx_ns_writable(self):
        """Transport sets t_pi_rx_ns after parsing."""
        p = ParsedPacket(pkt_type=0, seq=0, payload=b"")
        p.t_pi_rx_ns = 12345678
        assert p.t_pi_rx_ns == 12345678
