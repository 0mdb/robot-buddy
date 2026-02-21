"""Async serial transport with COBS framing and auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

import serial

from supervisor_v2.devices.protocol import ParsedPacket, parse_frame

log = logging.getLogger(__name__)

# Reconnect backoff bounds
_RECONNECT_MIN_S = 0.5
_RECONNECT_MAX_S = 5.0


class SerialTransport:
    """Async wrapper around pyserial with COBS frame extraction and reconnect."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        label: str = "serial",
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.label = label

        self._ser: serial.Serial | None = None
        self._buf = bytearray()
        self._connected = False
        self._running = False
        self._on_packet_handlers: list[Callable[[ParsedPacket], None]] = []
        self._on_connect: Callable[[], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

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
        self._last_bad_frame = ""
        self._last_error = ""

    @property
    def connected(self) -> bool:
        return self._connected

    def on_packet(self, cb: Callable[[ParsedPacket], None]) -> None:
        self._on_packet_handlers.append(cb)

    def on_connect(self, cb: Callable[[], None]) -> None:
        self._on_connect = cb

    def on_disconnect(self, cb: Callable[[], None]) -> None:
        self._on_disconnect = cb

    async def start(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()
        asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        self._close()

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
            except (serial.SerialException, OSError) as e:
                self._last_error = str(e)
                log.warning("%s: read error: %s", self.label, e)
                self._handle_disconnect()

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

            self._connect_count += 1
            self._connected = True
            self._buf.clear()
            log.info("%s: connected to %s", self.label, self.port)
            if self._on_connect:
                self._on_connect()
            return True
        except (serial.SerialException, OSError) as e:
            self._last_error = str(e)
            log.debug("%s: can't open %s: %s", self.label, self.port, e)
            return False

    def _blocking_read(self) -> bytes:
        """Called in executor thread. Reads available bytes."""
        self._read_ops += 1
        if not self._ser:
            return b""
        return self._ser.read(256)

    def _feed(self, data: bytes) -> None:
        """Feed raw bytes into COBS frame extractor."""
        self._rx_bytes += len(data)
        if data:
            self._last_rx_mono_ms = time.monotonic() * 1000.0
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
                    self._last_bad_frame = "frame too long (>512 bytes)"
                    log.warning("%s: frame too long, discarding", self.label)
                    self._buf.clear()

    def _dispatch_frame(self, frame: bytes) -> None:
        try:
            pkt = parse_frame(frame)
        except ValueError as e:
            self._frames_bad += 1
            self._last_bad_frame = str(e)
            log.debug("%s: bad frame: %s", self.label, e)
            return
        self._frames_ok += 1
        self._last_frame_mono_ms = time.monotonic() * 1000.0
        for handler in self._on_packet_handlers:
            handler(pkt)

    def _handle_disconnect(self) -> None:
        if self._connected:
            self._disconnect_count += 1
            self._connected = False
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
