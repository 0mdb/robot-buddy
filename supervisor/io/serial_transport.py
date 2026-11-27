"""Async serial transport with COBS framing and auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

import serial

from supervisor.devices.protocol import (
    COMMON_PROTOCOL_VERSION_ACK,
    ParsedPacket,
    build_set_protocol_version,
    parse_frame,
)

log = logging.getLogger(__name__)

# Reconnect backoff bounds
_RECONNECT_MIN_S = 0.5
_RECONNECT_MAX_S = 5.0

# If no *valid* frame arrives for this long on a "connected" link, treat it as a
# disconnect: reopen and re-run the protocol handshake. Two cases:
#  - silent hang: pyserial keeps timing out on .read() without raising when a
#    USB device wedges;
#  - MCU rebooted under us on a link that never drops (the face on the Pi's GPIO
#    UART): it comes back at protocol v1 while we parse v2, so bytes keep
#    arriving but every frame is bad. Only a reopen + handshake recovers that.
# Reflex heartbeat is 10 Hz and the face is similarly chatty, so 3 s is well past
# any healthy gap.
_RX_STALL_TIMEOUT_MS = 3000.0

# The ESP32-S3 ROM prints this on UART0 at every reset (can't be turned off without
# an eFuse). On a link that never drops (the face on the Pi's GPIO UART) it is the
# only sign the MCU rebooted, so treat it as a disconnect, as USB re-enumeration
# would be. Seen only at 115200: the ROM's fixed rate.
_MCU_RESET_MARKER = b"ESP-ROM:"


_POST_CONNECT_DISCARD_S = 0.2  # _feed drops everything this long after open (ROM text)
_NEGOTIATE_ATTEMPTS = 3  # v2 handshake tries per connect (all our MCUs speak v2)
_NEGOTIATE_RETRY_S = 1.0


class SerialTransport:
    """Async wrapper around pyserial with COBS frame extraction and reconnect."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        label: str = "serial",
        *,
        auto_negotiate: bool = True,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.label = label
        # Send SET_PROTOCOL_VERSION(2) after every open (PROTOCOL.md 3.2, amended 2026-11-27).
        self.auto_negotiate = auto_negotiate
        self._negotiate_task: asyncio.Task[bool] | None = None
        self.negotiations = 0

        self._ser: serial.Serial | None = None
        self._buf = bytearray()
        self._connected = False
        self._running = False
        self._on_packet_handlers: list[Callable[[ParsedPacket], None]] = []
        self._on_raw_frame: Callable[[int, str, bytes], None] | None = None
        self._on_connect: Callable[[], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Protocol version (1=legacy, 2=v2 with u32 seq + u64 t_src_us).
        # Set to 2 after successful SET_PROTOCOL_VERSION handshake.
        self.protocol_version: int = 1

        # Debug counters (for /debug/devices and troubleshooting).
        self._connect_count = 0
        self._disconnect_count = 0
        self._read_ops = 0
        self._write_ops = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._frames_ok = 0
        self._frames_bad = 0
        self._frames_too_long = 0
        self._write_errors = 0
        self._write_timeouts = 0
        self._last_rx_mono_ms = 0.0
        self._last_frame_mono_ms = 0.0
        self._last_good_mono_ms = (
            0.0  # last valid frame, or connect; drives the stall watchdog
        )
        self._rx_tail = (
            b""  # last bytes of the previous read, to catch a marker split across reads
        )
        self._mcu_resets_seen = 0
        self._last_bad_frame = ""
        self._last_error = ""
        self._connect_mono: float = 0.0  # monotonic time of last connect

    @property
    def connected(self) -> bool:
        return self._connected

    def on_packet(self, cb: Callable[[ParsedPacket], None]) -> None:
        self._on_packet_handlers.append(cb)

    def on_connect(self, cb: Callable[[], None]) -> None:
        self._on_connect = cb

    def on_raw_frame(self, cb: Callable[[int, str, bytes], None]) -> None:
        """Register callback for raw frames: (t_pi_rx_ns, label, frame_bytes)."""
        self._on_raw_frame = cb

    def on_disconnect(self, cb: Callable[[], None]) -> None:
        self._on_disconnect = cb

    async def start(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()
        asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        self._close()

    @property
    def negotiating(self) -> bool:
        """A v2 handshake is scheduled or in flight (frames may be in the other envelope)."""
        return self._negotiate_task is not None and not self._negotiate_task.done()

    def request_renegotiate(self) -> None:
        """Run the v2 handshake in the background unless one is already running. Called after
        every open, and by clients that see envelope desync (wrong STATE length)."""
        if self._loop is None or not self._connected:
            return
        if self._negotiate_task is not None and not self._negotiate_task.done():
            return
        self.negotiations += 1
        self._negotiate_task = self._loop.create_task(self._negotiate_with_retry())

    async def _negotiate_with_retry(self) -> bool:
        # Wait out _feed's post-connect discard window (ROM text), or the ACK is thrown away;
        # then retry: an ESP32 reset by the port open may still be booting.
        wait_s = self._connect_mono + _POST_CONNECT_DISCARD_S + 0.05 - time.monotonic()
        if wait_s > 0:
            await asyncio.sleep(wait_s)
        for attempt in range(_NEGOTIATE_ATTEMPTS):
            if not self._connected:
                return False
            if await self.negotiate_v2():
                return True
            if attempt + 1 < _NEGOTIATE_ATTEMPTS:
                await asyncio.sleep(_NEGOTIATE_RETRY_S)
        return False

    async def negotiate_v2(self, timeout_s: float = 0.5) -> bool:
        """Send SET_PROTOCOL_VERSION(2) and wait for ACK.

        Returns True if MCU acknowledged v2, False on timeout (stays v1).
        """
        if not self._connected:
            return False

        ack_event = asyncio.Event()
        ack_version: list[int] = []

        def _on_ack(pkt: ParsedPacket) -> None:
            if pkt.pkt_type == COMMON_PROTOCOL_VERSION_ACK:
                v = pkt.payload[0] if pkt.payload else 0
                ack_version.append(v)
                ack_event.set()

        self._on_packet_handlers.append(_on_ack)
        try:
            pkt = build_set_protocol_version(0, version=2)
            self.write(pkt)
            try:
                await asyncio.wait_for(ack_event.wait(), timeout=timeout_s)
            except asyncio.TimeoutError:
                log.warning(
                    "%s: v2 handshake timeout (%.0f ms), staying at v1",
                    self.label,
                    timeout_s * 1000,
                )
                return False

            if ack_version and ack_version[0] == 2:
                self.protocol_version = 2
                log.info("%s: protocol v2 negotiated", self.label)
                return True
            log.warning("%s: unexpected ACK version %s", self.label, ack_version)
            return False
        finally:
            self._on_packet_handlers.remove(_on_ack)

    def write(self, data: bytes) -> bool:
        """Write raw bytes (already COBS-framed). Non-blocking best-effort."""
        self._write_ops += 1
        if self._ser and self._connected:
            try:
                written = self._ser.write(data) or 0
                if written != len(data):
                    self._write_timeouts += 1
                    self._last_error = f"Short write ({written}/{len(data)} bytes)"
                    return False
                self._tx_bytes += written
                return True
            except serial.SerialTimeoutException as e:
                # Non-fatal: drop this frame and keep loop responsive.
                self._write_timeouts += 1
                self._last_error = str(e)
                return False
            except (serial.SerialException, OSError) as e:
                self._write_errors += 1
                self._last_error = str(e)
                log.warning("%s: write error: %s", self.label, e)
                self._handle_disconnect()
                return False
        return False

    def debug_snapshot(self) -> dict:
        dtr = None
        rts = None
        if self._ser:
            try:
                dtr = bool(self._ser.dtr)
                rts = bool(self._ser.rts)
            except Exception:
                pass

        return {
            "port": self.port,
            "label": self.label,
            "connected": self._connected,
            "protocol_version": self.protocol_version,
            "dtr": dtr,
            "rts": rts,
            "connect_count": self._connect_count,
            "disconnect_count": self._disconnect_count,
            "read_ops": self._read_ops,
            "write_ops": self._write_ops,
            "rx_bytes": self._rx_bytes,
            "tx_bytes": self._tx_bytes,
            "frames_ok": self._frames_ok,
            "frames_bad": self._frames_bad,
            "frames_too_long": self._frames_too_long,
            "mcu_resets_seen": self._mcu_resets_seen,
            "write_errors": self._write_errors,
            "write_timeouts": self._write_timeouts,
            "last_rx_mono_ms": round(self._last_rx_mono_ms, 1),
            "last_frame_mono_ms": round(self._last_frame_mono_ms, 1),
            "last_bad_frame": self._last_bad_frame,
            "last_error": self._last_error,
        }

    # -- internals -----------------------------------------------------------

    async def _run_loop(self) -> None:
        loop = self._loop
        if loop is None:
            loop = asyncio.get_running_loop()
            self._loop = loop
        backoff = _RECONNECT_MIN_S
        while self._running:
            if not self._connected:
                if self._try_open():
                    backoff = _RECONNECT_MIN_S
                else:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _RECONNECT_MAX_S)
                    continue

            try:
                data = await loop.run_in_executor(None, self._blocking_read)
                if data:
                    self._feed(data)
                self._check_rx_stall()
            except (serial.SerialException, OSError) as e:
                self._last_error = str(e)
                log.warning("%s: read error: %s", self.label, e)
                self._handle_disconnect()

            # Always yield so the event loop can process HTTP, tick loop,
            # and other tasks.  Without this, fast-returning reads (data
            # always available) can starve uvicorn's socket accept loop.
            await asyncio.sleep(0)

    def _try_open(self) -> bool:
        try:
            self._ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=0.05,  # 50ms blocking read timeout
                write_timeout=0.1,  # bounded write latency; avoid indefinite event-loop stalls
            )
            # Keep CDC host line-state asserted; some device stacks gate OUT traffic on DTR/RTS.
            try:
                self._ser.dtr = True
                self._ser.rts = True
            except Exception:
                pass

            self._connect_mono = time.monotonic()
            self._connect_count += 1
            self._connected = True
            self._buf.clear()
            self._rx_tail = b""
            # Seed so the RX-stall watchdog doesn't trip before the first frame.
            self._last_rx_mono_ms = self._connect_mono * 1000.0
            self._last_good_mono_ms = self._connect_mono * 1000.0
            log.info("%s: connected to %s", self.label, self.port)
            if self._on_connect:
                self._on_connect()
            if self.auto_negotiate:
                self.request_renegotiate()
            return True
        except (serial.SerialException, OSError) as e:
            self._last_error = str(e)
            log.debug("%s: can't open %s: %s", self.label, self.port, e)
            return False

    def _check_rx_stall(self) -> None:
        """Disconnect if no valid frame has arrived within _RX_STALL_TIMEOUT_MS."""
        if not self._connected or self._last_good_mono_ms <= 0:
            return
        now_ms = time.monotonic() * 1000.0
        stall_ms = now_ms - self._last_good_mono_ms
        if stall_ms <= _RX_STALL_TIMEOUT_MS:
            return
        bytes_flowing = now_ms - self._last_rx_mono_ms < _RX_STALL_TIMEOUT_MS
        what = "no valid frame" if bytes_flowing else "rx stalled"
        self._last_error = f"{what} {stall_ms:.0f} ms"
        log.warning(
            "%s: %s for %.0f ms, treating as disconnect", self.label, what, stall_ms
        )
        self._handle_disconnect()

    def _blocking_read(self) -> bytes:
        """Called in executor thread. Reads available bytes."""
        self._read_ops += 1
        if not self._ser:
            return b""
        return self._ser.read(256)

    def _saw_mcu_reset(self, data: bytes) -> bool:
        """Disconnect (so we reopen and resync) if the ROM reset banner went past."""
        window = self._rx_tail + data
        self._rx_tail = window[-(len(_MCU_RESET_MARKER) - 1) :]
        if _MCU_RESET_MARKER not in window:
            return False
        self._mcu_resets_seen += 1
        self._rx_tail = b""
        self._last_error = "MCU reset (ROM banner)"
        log.warning("%s: MCU reset detected (ROM banner), reconnecting", self.label)
        self._handle_disconnect()
        return True

    def _feed(self, data: bytes) -> None:
        """Feed raw bytes into COBS frame extractor."""
        self._rx_bytes += len(data)
        if not data:
            return
        self._last_rx_mono_ms = time.monotonic() * 1000.0
        if self._saw_mcu_reset(data):
            return
        # Discard data for 200ms after connect to flush ROM bootloader text.
        if time.monotonic() - self._connect_mono < _POST_CONNECT_DISCARD_S:
            self._buf.clear()
            return
        for b in data:
            if b == 0x00:
                if self._buf:
                    self._dispatch_frame(bytes(self._buf))
                    self._buf.clear()
            else:
                self._buf.append(b)
                if len(self._buf) > 512:
                    self._frames_too_long += 1
                    self._frames_bad += 1
                    preview = bytes(self._buf[:64])
                    hex_str = preview.hex(" ")
                    ascii_str = preview.decode("ascii", errors="replace")
                    self._last_bad_frame = f"frame too long ({len(self._buf)} bytes)"
                    log.warning(
                        "%s: frame too long (%d bytes), first 64: %s | %s",
                        self.label,
                        len(self._buf),
                        hex_str,
                        ascii_str,
                    )
                    self._buf.clear()

    def _dispatch_frame(self, frame: bytes) -> None:
        t_pi_rx_ns = time.monotonic_ns()
        if self._on_raw_frame:
            self._on_raw_frame(t_pi_rx_ns, self.label, frame)
        try:
            pkt = parse_frame(frame, protocol_version=self.protocol_version)
        except ValueError as e:
            self._frames_bad += 1
            self._last_bad_frame = str(e)
            log.debug("%s: bad frame: %s", self.label, e)
            return
        pkt.t_pi_rx_ns = t_pi_rx_ns
        self._frames_ok += 1
        self._last_frame_mono_ms = t_pi_rx_ns / 1_000_000.0
        self._last_good_mono_ms = self._last_frame_mono_ms
        for handler in self._on_packet_handlers:
            handler(pkt)

    def _handle_disconnect(self) -> None:
        if self._connected:
            self._disconnect_count += 1
            self._connected = False
            self.protocol_version = 1  # Reset to v1; re-negotiate on reconnect
            log.warning("%s: disconnected from %s", self.label, self.port)
            if self._on_disconnect:
                self._on_disconnect()
        self._close()

    def _close(self) -> None:
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self._connected = False
