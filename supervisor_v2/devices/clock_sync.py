"""Clock sync engine — estimates clock offset between Pi and an MCU.

Implements PROTOCOL.md sections 2.2-2.4:
- Sends TIME_SYNC_REQ pings on its own async schedule
- Processes TIME_SYNC_RESP responses
- Maintains a 16-sample sliding window
- Uses min-RTT sample for offset estimate
- State machine: unsynced -> synced -> degraded
- Drift estimation via exponential low-pass filter
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from supervisor_v2.core.state import ClockSync
from supervisor_v2.devices.protocol import (
    COMMON_TIME_SYNC_RESP,
    ParsedPacket,
    TimeSyncRespPayload,
    build_time_sync_req,
)

if TYPE_CHECKING:
    from supervisor_v2.io.serial_transport import SerialTransport

log = logging.getLogger(__name__)

# ── Constants (PROTOCOL.md section 2.2-2.4) ─────────────────────

_WINDOW_SIZE = 16
_INITIAL_HZ = 5.0
_STEADY_HZ = 2.0
_INITIAL_SAMPLE_COUNT = 20
_PING_TIMEOUT_S = 0.5
_RTT_THRESHOLD_NS = 10_000_000  # 10 ms — ESP32-S3 Full-Speed USB typical RTT is 2-5 ms
_STALE_TIMEOUT_NS = 5_000_000_000  # 5 seconds
_MIN_SAMPLES_FOR_SYNCED = 5
_CONSECUTIVE_BAD_RTT_FOR_DEGRADED = 10
_DRIFT_ALPHA = 0.1
_DRIFT_WARN_THRESHOLD = 100.0  # us/s


@dataclass(slots=True)
class _SyncSample:
    rtt_ns: int
    offset_ns: int
    t_pi_rx_ns: int


class ClockSyncEngine:
    """Per-MCU async clock sync task (PROTOCOL.md section 2.2)."""

    def __init__(
        self,
        transport: SerialTransport,
        clock_state: ClockSync,
        label: str,
    ) -> None:
        self._transport = transport
        self._clock = clock_state
        self._label = label

        self._ping_seq: int = 0
        self._pending_ping_seq: int | None = None
        self._t_ping_tx_ns: int = 0
        self._pkt_seq: int = 0

        self._window: deque[_SyncSample] = deque(maxlen=_WINDOW_SIZE)
        self._total_samples: int = 0
        self._consecutive_bad_rtt: int = 0

        self._prev_offset_ns: int | None = None
        self._prev_offset_t_ns: int | None = None
        self._drift_filtered: float = 0.0

        transport.on_packet(self._handle_packet)

    async def run(self) -> None:
        """Run the sync loop. Call as an asyncio task."""
        log.info("%s: clock sync started", self._label)
        try:
            while True:
                if self._total_samples < _INITIAL_SAMPLE_COUNT:
                    interval = 1.0 / _INITIAL_HZ
                else:
                    interval = 1.0 / _STEADY_HZ

                if self._transport.connected:
                    self._check_timeout()
                    self._send_ping()

                await asyncio.sleep(interval)

                self._check_stale()
        except asyncio.CancelledError:
            pass
        finally:
            log.info("%s: clock sync stopped", self._label)

    # ── Ping / Pong ──────────────────────────────────────────────

    def _send_ping(self) -> None:
        if self._pending_ping_seq is not None:
            return

        self._ping_seq += 1
        self._pending_ping_seq = self._ping_seq
        self._t_ping_tx_ns = time.monotonic_ns()

        pkt = build_time_sync_req(self._next_pkt_seq(), self._ping_seq)
        self._transport.write(pkt)

    def _handle_packet(self, pkt: ParsedPacket) -> None:
        if pkt.pkt_type != COMMON_TIME_SYNC_RESP:
            return

        t_pi_rx_ns = time.monotonic_ns()

        try:
            resp = TimeSyncRespPayload.unpack(pkt.payload)
        except ValueError as e:
            log.warning("%s: bad TIME_SYNC_RESP: %s", self._label, e)
            return

        if self._pending_ping_seq is None or resp.ping_seq != self._pending_ping_seq:
            return

        self._pending_ping_seq = None

        rtt_ns = t_pi_rx_ns - self._t_ping_tx_ns
        t_src_ns = resp.t_src_us * 1000
        offset_ns = t_pi_rx_ns - t_src_ns - (rtt_ns // 2)

        sample = _SyncSample(rtt_ns=rtt_ns, offset_ns=offset_ns, t_pi_rx_ns=t_pi_rx_ns)
        self._window.append(sample)
        self._total_samples += 1

        if rtt_ns > _RTT_THRESHOLD_NS:
            self._consecutive_bad_rtt += 1
        else:
            self._consecutive_bad_rtt = 0

        best = self._min_rtt_sample()
        if best is not None:
            self._update_drift(best.offset_ns, t_pi_rx_ns)
            self._clock.offset_ns = best.offset_ns
            self._clock.rtt_min_us = best.rtt_ns // 1000
            self._clock.t_last_sync_ns = t_pi_rx_ns

        self._clock.samples = self._total_samples
        self._clock.drift_us_per_s = round(self._drift_filtered, 3)

        self._update_state(t_pi_rx_ns)

    def _min_rtt_sample(self) -> _SyncSample | None:
        best: _SyncSample | None = None
        for s in self._window:
            if s.rtt_ns <= _RTT_THRESHOLD_NS:
                if best is None or s.rtt_ns < best.rtt_ns:
                    best = s
        return best

    # ── State Machine ────────────────────────────────────────────

    def _update_state(self, now_ns: int) -> None:
        prev = self._clock.state
        good = self._min_rtt_sample() is not None

        if prev == "unsynced":
            if self._total_samples >= _MIN_SAMPLES_FOR_SYNCED and good:
                self._clock.state = "synced"
        elif prev == "synced":
            if self._is_degraded(now_ns):
                self._clock.state = "degraded"
        elif prev == "degraded":
            if good:
                self._clock.state = "synced"

        if self._clock.state != prev:
            log.info(
                "%s: clock %s -> %s (samples=%d, rtt_min=%d us)",
                self._label,
                prev,
                self._clock.state,
                self._total_samples,
                self._clock.rtt_min_us,
            )

    def _is_degraded(self, now_ns: int) -> bool:
        if self._clock.t_last_sync_ns > 0:
            if now_ns - self._clock.t_last_sync_ns > _STALE_TIMEOUT_NS:
                return True
        if self._consecutive_bad_rtt >= _CONSECUTIVE_BAD_RTT_FOR_DEGRADED:
            return True
        return False

    # ── Timeout / Stale ──────────────────────────────────────────

    def _check_timeout(self) -> None:
        if self._pending_ping_seq is None:
            return
        elapsed_ns = time.monotonic_ns() - self._t_ping_tx_ns
        if elapsed_ns > int(_PING_TIMEOUT_S * 1_000_000_000):
            log.debug(
                "%s: ping %d timed out (%.1f ms)",
                self._label,
                self._pending_ping_seq,
                elapsed_ns / 1_000_000,
            )
            self._pending_ping_seq = None

    def _check_stale(self) -> None:
        if self._clock.state == "synced":
            now_ns = time.monotonic_ns()
            if self._is_degraded(now_ns):
                log.warning("%s: clock sync degraded (stale or bad RTT)", self._label)
                self._clock.state = "degraded"

    # ── Drift Estimation ─────────────────────────────────────────

    def _update_drift(self, offset_ns: int, t_ns: int) -> None:
        if self._prev_offset_ns is not None and self._prev_offset_t_ns is not None:
            dt_ns = t_ns - self._prev_offset_t_ns
            if dt_ns > 0:
                d_offset_us = (offset_ns - self._prev_offset_ns) / 1000.0
                dt_s = dt_ns / 1_000_000_000.0
                raw_drift = d_offset_us / dt_s
                self._drift_filtered = (
                    _DRIFT_ALPHA * raw_drift + (1 - _DRIFT_ALPHA) * self._drift_filtered
                )
                if abs(self._drift_filtered) > _DRIFT_WARN_THRESHOLD:
                    log.warning(
                        "%s: high drift %.1f us/s", self._label, self._drift_filtered
                    )

        self._prev_offset_ns = offset_ns
        self._prev_offset_t_ns = t_ns

    # ── Helpers ──────────────────────────────────────────────────

    def _next_pkt_seq(self) -> int:
        s = self._pkt_seq
        self._pkt_seq = (self._pkt_seq + 1) & 0xFF
        return s
