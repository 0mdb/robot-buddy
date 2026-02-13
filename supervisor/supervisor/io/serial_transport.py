"""Async serial transport with COBS framing and auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import serial

from supervisor.devices.protocol import ParsedPacket, parse_frame

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
        self._on_packet: Callable[[ParsedPacket], None] | None = None
        self._on_connect: Callable[[], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def on_packet(self, cb: Callable[[ParsedPacket], None]) -> None:
        self._on_packet = cb

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

    def write(self, data: bytes) -> None:
        """Write raw bytes (already COBS-framed). Non-blocking best-effort."""
        if self._ser and self._connected:
            try:
                self._ser.write(data)
            except (serial.SerialException, OSError) as e:
                log.warning("%s: write error: %s", self.label, e)
                self._handle_disconnect()

    # -- internals -----------------------------------------------------------

    async def _run_loop(self) -> None:
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
                data = await self._loop.run_in_executor(None, self._blocking_read)
                if data:
                    self._feed(data)
            except (serial.SerialException, OSError) as e:
                log.warning("%s: read error: %s", self.label, e)
                self._handle_disconnect()

    def _try_open(self) -> bool:
        try:
            self._ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=0.05,  # 50ms blocking read timeout
            )
            self._connected = True
            self._buf.clear()
            log.info("%s: connected to %s", self.label, self.port)
            if self._on_connect:
                self._on_connect()
            return True
        except (serial.SerialException, OSError) as e:
            log.debug("%s: can't open %s: %s", self.label, self.port, e)
            return False

    def _blocking_read(self) -> bytes:
        """Called in executor thread. Reads available bytes."""
        if not self._ser:
            return b""
        return self._ser.read(256)

    def _feed(self, data: bytes) -> None:
        """Feed raw bytes into COBS frame extractor."""
        for b in data:
            if b == 0x00:
                if self._buf:
                    self._dispatch_frame(bytes(self._buf))
                    self._buf.clear()
            else:
                self._buf.append(b)
                if len(self._buf) > 512:
                    log.warning("%s: frame too long, discarding", self.label)
                    self._buf.clear()

    def _dispatch_frame(self, frame: bytes) -> None:
        try:
            pkt = parse_frame(frame)
        except ValueError as e:
            log.debug("%s: bad frame: %s", self.label, e)
            return
        if self._on_packet:
            self._on_packet(pkt)

    def _handle_disconnect(self) -> None:
        if self._connected:
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
