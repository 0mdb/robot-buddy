"""Face MCU client — sends face commands, receives touch/status telemetry."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from supervisor.devices.protocol import (
    FaceStatusPayload,
    FaceTelType,
    ParsedPacket,
    TouchEventPayload,
    build_face_gesture,
    build_face_set_state,
    build_face_set_system,
)
from supervisor.io.serial_transport import SerialTransport

log = logging.getLogger(__name__)


@dataclass(slots=True)
class FaceTelemetry:
    """Latest status from face MCU."""

    mood_id: int = 0
    active_gesture: int = 0xFF
    system_mode: int = 0
    flags: int = 0
    rx_mono_ms: float = 0.0
    seq: int = 0

    @property
    def touch_active(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def audio_playing(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def mic_activity(self) -> bool:
        return bool(self.flags & 0x04)


@dataclass(slots=True)
class TouchEvent:
    event_type: int = 0
    x: int = 0
    y: int = 0
    timestamp_mono_ms: float = 0.0


class FaceClient:
    """Send commands to and receive telemetry from the face MCU."""

    def __init__(self, transport: SerialTransport) -> None:
        self._transport = transport
        self._seq = 0
        self.telemetry = FaceTelemetry()
        self.last_touch: TouchEvent | None = None
        self._on_touch: Callable[[TouchEvent], None] | None = None

        transport.on_packet(self._handle_packet)

    @property
    def connected(self) -> bool:
        return self._transport.connected

    def on_touch(self, cb: Callable[[TouchEvent], None]) -> None:
        self._on_touch = cb

    def send_state(
        self,
        emotion_id: int = 0,
        intensity: float = 1.0,
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
        brightness: float = 1.0,
    ) -> None:
        if not self.connected:
            return
        intensity_u8 = max(0, min(255, int(intensity * 255)))
        gaze_x_i8 = max(-128, min(127, int(gaze_x * 32)))
        gaze_y_i8 = max(-128, min(127, int(gaze_y * 32)))
        brightness_u8 = max(0, min(255, int(brightness * 255)))
        pkt = build_face_set_state(
            self._next_seq(),
            emotion_id,
            intensity_u8,
            gaze_x_i8,
            gaze_y_i8,
            brightness_u8,
        )
        self._transport.write(pkt)

    def send_gesture(self, gesture_id: int = 0, duration_ms: int = 0) -> None:
        if not self.connected:
            return
        pkt = build_face_gesture(self._next_seq(), gesture_id, duration_ms)
        self._transport.write(pkt)

    def send_system_mode(self, mode: int = 0, param: int = 0) -> None:
        if not self.connected:
            return
        pkt = build_face_set_system(self._next_seq(), mode, 0, param)
        self._transport.write(pkt)

    # -- internals -----------------------------------------------------------

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        return s

    def _handle_packet(self, pkt: ParsedPacket) -> None:
        if pkt.pkt_type == FaceTelType.FACE_STATUS:
            try:
                status = FaceStatusPayload.unpack(pkt.payload)
            except ValueError as e:
                log.warning("face: bad FACE_STATUS: %s", e)
                return
            t = self.telemetry
            t.mood_id = status.mood_id
            t.active_gesture = status.active_gesture
            t.system_mode = status.system_mode
            t.flags = status.flags
            t.rx_mono_ms = time.monotonic() * 1000.0
            t.seq = pkt.seq

        elif pkt.pkt_type == FaceTelType.TOUCH_EVENT:
            try:
                te = TouchEventPayload.unpack(pkt.payload)
            except ValueError as e:
                log.warning("face: bad TOUCH_EVENT: %s", e)
                return
            evt = TouchEvent(te.event_type, te.x, te.y, time.monotonic() * 1000.0)
            self.last_touch = evt
            if self._on_touch:
                self._on_touch(evt)
        else:
            log.debug("face: unknown packet type 0x%02X", pkt.pkt_type)
