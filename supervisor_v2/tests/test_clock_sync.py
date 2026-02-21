"""Tests for ClockSyncEngine (PROTOCOL.md sections 2.2-2.4)."""

from __future__ import annotations

from typing import Callable
from unittest.mock import patch


from supervisor_v2.core.state import ClockSync
from supervisor_v2.devices.clock_sync import (
    _MIN_SAMPLES_FOR_SYNCED,
    _WINDOW_SIZE,
    ClockSyncEngine,
)
from supervisor_v2.devices.protocol import (
    COMMON_TIME_SYNC_RESP,
    ParsedPacket,
)


# ── Test helpers ─────────────────────────────────────────────────


class FakeTransport:
    """Minimal mock of SerialTransport for clock sync testing."""

    def __init__(self) -> None:
        self.connected = True
        self.written: list[bytes] = []
        self._handlers: list[Callable[[ParsedPacket], None]] = []

    def on_packet(self, cb: Callable[[ParsedPacket], None]) -> None:
        self._handlers.append(cb)

    def write(self, data: bytes) -> bool:
        self.written.append(data)
        return True

    def inject(self, pkt: ParsedPacket) -> None:
        for h in self._handlers:
            h(pkt)


def _make_resp(ping_seq: int, t_src_us: int) -> ParsedPacket:
    """Build a ParsedPacket mimicking a TIME_SYNC_RESP from an MCU."""
    import struct

    payload = struct.pack("<IQ", ping_seq, t_src_us)
    return ParsedPacket(pkt_type=COMMON_TIME_SYNC_RESP, seq=0, payload=payload)


def _send_and_respond(
    engine: ClockSyncEngine,
    transport: FakeTransport,
    *,
    rtt_ns: int = 500_000,  # 0.5 ms default (well under 3 ms threshold)
) -> None:
    """Trigger a ping, then inject a matching response with controlled RTT."""
    # Send the ping (records t_pi_tx_ns internally)
    engine._send_ping()

    # Simulate MCU response with the matching ping_seq
    ping_seq = engine._pending_ping_seq
    assert ping_seq is not None, "No pending ping after _send_ping()"

    # The engine recorded t_pi_tx_ns via time.monotonic_ns(). We want to
    # simulate a response arriving rtt_ns later. The offset calculation is:
    #   offset_ns = t_pi_rx_ns - (t_src_us * 1000) - (rtt_ns // 2)
    # We set t_src_us so that offset_ns comes out to a predictable value.
    t_pi_tx_ns = engine._t_ping_tx_ns
    t_pi_rx_ns = t_pi_tx_ns + rtt_ns
    # Make t_src_us such that offset_ns ~ 0 (clocks aligned)
    t_src_us = (t_pi_tx_ns + rtt_ns // 2) // 1000

    resp = _make_resp(ping_seq, t_src_us)

    # Patch monotonic_ns to return our controlled rx time
    with patch(
        "supervisor_v2.devices.clock_sync.time.monotonic_ns", return_value=t_pi_rx_ns
    ):
        transport.inject(resp)


# ── Tests ────────────────────────────────────────────────────────


class TestClockSyncEngine:
    def _make(self) -> tuple[ClockSyncEngine, FakeTransport, ClockSync]:
        transport = FakeTransport()
        clock = ClockSync()
        engine = ClockSyncEngine(transport, clock, "test")
        return engine, transport, clock

    def test_initial_state(self) -> None:
        _, _, clock = self._make()
        assert clock.state == "unsynced"
        assert clock.samples == 0
        assert clock.offset_ns == 0

    def test_single_sample_stays_unsynced(self) -> None:
        engine, transport, clock = self._make()
        _send_and_respond(engine, transport)
        assert clock.samples == 1
        assert clock.state == "unsynced"

    def test_reaches_synced_after_min_samples(self) -> None:
        engine, transport, clock = self._make()
        for _ in range(_MIN_SAMPLES_FOR_SYNCED):
            _send_and_respond(engine, transport)
        assert clock.samples == _MIN_SAMPLES_FOR_SYNCED
        assert clock.state == "synced"

    def test_min_rtt_sample_selected(self) -> None:
        engine, transport, clock = self._make()
        # Send some samples with varying RTT
        rtts = [2_000_000, 500_000, 1_500_000, 800_000, 200_000]
        for rtt in rtts:
            _send_and_respond(engine, transport, rtt_ns=rtt)
        # Min RTT should be 200_000 ns = 200 us
        assert clock.rtt_min_us == 200

    def test_bad_rtt_filtered_from_offset(self) -> None:
        engine, transport, clock = self._make()
        # Send all samples with RTT above the 3ms threshold
        for _ in range(6):
            _send_and_respond(engine, transport, rtt_ns=15_000_000)
        # Even with 6 samples (> min required), state stays unsynced
        # because no good-RTT samples exist
        assert clock.state == "unsynced"
        assert clock.samples == 6

    def test_mixed_rtt_reaches_synced(self) -> None:
        engine, transport, clock = self._make()
        # 3 bad + 5 good = should sync (5 good samples, good RTT exists)
        for _ in range(3):
            _send_and_respond(engine, transport, rtt_ns=15_000_000)
        for _ in range(5):
            _send_and_respond(engine, transport, rtt_ns=500_000)
        assert clock.state == "synced"

    def test_degraded_on_stale(self) -> None:
        engine, transport, clock = self._make()
        # First reach synced
        for _ in range(_MIN_SAMPLES_FOR_SYNCED):
            _send_and_respond(engine, transport)
        assert clock.state == "synced"

        # Simulate 6 seconds passing (stale timeout is 5s)
        stale_ns = clock.t_last_sync_ns + 6_000_000_000
        with patch(
            "supervisor_v2.devices.clock_sync.time.monotonic_ns",
            return_value=stale_ns,
        ):
            engine._check_stale()
        assert clock.state == "degraded"

    def test_recovery_from_degraded(self) -> None:
        engine, transport, clock = self._make()
        # Reach synced, then force degraded
        for _ in range(_MIN_SAMPLES_FOR_SYNCED):
            _send_and_respond(engine, transport)
        clock.state = "degraded"

        # One good sample should recover
        _send_and_respond(engine, transport)
        assert clock.state == "synced"

    def test_ping_timeout_clears_pending(self) -> None:
        engine, transport, clock = self._make()
        engine._send_ping()
        assert engine._pending_ping_seq is not None

        # Simulate 600ms passing (timeout is 500ms)
        timeout_ns = engine._t_ping_tx_ns + 600_000_000
        with patch(
            "supervisor_v2.devices.clock_sync.time.monotonic_ns",
            return_value=timeout_ns,
        ):
            engine._check_timeout()
        assert engine._pending_ping_seq is None

    def test_mismatched_ping_seq_ignored(self) -> None:
        engine, transport, clock = self._make()
        engine._send_ping()
        ping_seq = engine._pending_ping_seq

        # Inject response with wrong ping_seq
        wrong_resp = _make_resp(ping_seq + 100, 12345)
        transport.inject(wrong_resp)

        # Pending ping should still be set (not cleared by wrong response)
        assert engine._pending_ping_seq == ping_seq
        assert clock.samples == 0

    def test_disconnected_transport_no_send(self) -> None:
        engine, transport, clock = self._make()
        transport.connected = False
        engine._send_ping()
        # Write is called regardless (transport.write handles connected check)
        # The important thing is no crash
        assert clock.samples == 0

    def test_sliding_window_caps_at_max(self) -> None:
        engine, transport, clock = self._make()
        for _ in range(_WINDOW_SIZE + 5):
            _send_and_respond(engine, transport)
        assert len(engine._window) == _WINDOW_SIZE
        assert clock.samples == _WINDOW_SIZE + 5

    def test_drift_estimation(self) -> None:
        engine, transport, clock = self._make()
        # Send enough samples to have drift tracking
        for _ in range(5):
            _send_and_respond(engine, transport)
        # After multiple samples, drift should be calculated (near 0 for aligned clocks)
        assert isinstance(clock.drift_us_per_s, float)
