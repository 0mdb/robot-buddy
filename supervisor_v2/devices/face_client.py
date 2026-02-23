"""Face MCU client — sends face commands, receives touch/button/status telemetry."""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from supervisor_v2.devices.protocol import (
    FACE_FLAGS_ALL,
    FaceButtonEventPayload,
    FaceCmdType,
    FaceHeartbeatPayload,
    FaceStatusPayload,
    FaceTelType,
    ParsedPacket,
    TouchEventPayload,
    build_face_gesture,
    build_face_set_conv_state,
    build_face_set_flags,
    build_face_set_state,
    build_face_set_system,
    build_face_set_talking,
)
from supervisor_v2.io.serial_transport import SerialTransport

if TYPE_CHECKING:
    from supervisor_v2.api.protocol_capture import ProtocolCapture

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
    def talking(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def ptt_listening(self) -> bool:
        return bool(self.flags & 0x04)


@dataclass(slots=True)
class TouchEvent:
    event_type: int = 0
    x: int = 0
    y: int = 0
    timestamp_mono_ms: float = 0.0


@dataclass(slots=True)
class ButtonEvent:
    button_id: int = 0
    event_type: int = 0
    state: int = 0
    timestamp_mono_ms: float = 0.0


@dataclass(slots=True)
class HeartbeatTelemetry:
    uptime_ms: int = 0
    status_tx_count: int = 0
    touch_tx_count: int = 0
    button_tx_count: int = 0
    usb_tx_calls: int = 0
    usb_tx_bytes_requested: int = 0
    usb_tx_bytes_queued: int = 0
    usb_tx_short_writes: int = 0
    usb_tx_flush_ok: int = 0
    usb_tx_flush_not_finished: int = 0
    usb_tx_flush_timeout: int = 0
    usb_tx_flush_error: int = 0
    usb_rx_calls: int = 0
    usb_rx_bytes: int = 0
    usb_rx_errors: int = 0
    usb_line_state_events: int = 0
    usb_dtr: bool = False
    usb_rts: bool = False
    ptt_listening: bool = False
    seq: int = 0
    rx_mono_ms: float = 0.0


class FaceClient:
    """Send commands to and receive telemetry from the face MCU."""

    def __init__(
        self,
        transport: SerialTransport,
        capture: ProtocolCapture | None = None,
    ) -> None:
        self._transport = transport
        self._capture = capture
        self._seq = 0
        self.telemetry = FaceTelemetry()
        self.last_touch: TouchEvent | None = None
        self.last_button: ButtonEvent | None = None
        self.last_heartbeat: HeartbeatTelemetry | None = None
        self._touch_subscribers: list[Callable[[TouchEvent], None]] = []
        self._button_subscribers: list[Callable[[ButtonEvent], None]] = []
        self._tx_packets = 0
        self._rx_face_status_packets = 0
        self._rx_touch_packets = 0
        self._rx_button_packets = 0
        self._rx_heartbeat_packets = 0
        self._rx_bad_payload_packets = 0
        self._rx_unknown_packets = 0
        self.last_talking_energy_cmd = 0
        self.last_flags_cmd = FACE_FLAGS_ALL

        transport.on_packet(self._handle_packet)

    @property
    def connected(self) -> bool:
        return self._transport.connected

    def subscribe_touch(self, cb: Callable[[TouchEvent], None]) -> None:
        self._touch_subscribers.append(cb)

    def subscribe_button(self, cb: Callable[[ButtonEvent], None]) -> None:
        self._button_subscribers.append(cb)

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
        seq = self._next_seq()
        pkt = build_face_set_state(
            seq,
            emotion_id,
            intensity_u8,
            gaze_x_i8,
            gaze_y_i8,
            brightness_u8,
        )
        self._transport.write(pkt)
        self._tx_packets += 1
        if self._capture and self._capture.active:
            self._capture.capture_tx(
                "face",
                FaceCmdType.SET_STATE,
                seq,
                struct.pack(
                    "<BBbbB",
                    emotion_id,
                    intensity_u8,
                    gaze_x_i8,
                    gaze_y_i8,
                    brightness_u8,
                ),
            )

    def send_gesture(self, gesture_id: int = 0, duration_ms: int = 0) -> None:
        if not self.connected:
            return
        seq = self._next_seq()
        pkt = build_face_gesture(seq, gesture_id, duration_ms)
        self._transport.write(pkt)
        self._tx_packets += 1
        if self._capture and self._capture.active:
            self._capture.capture_tx(
                "face",
                FaceCmdType.GESTURE,
                seq,
                struct.pack("<BH", gesture_id, duration_ms),
            )

    def send_system_mode(self, mode: int = 0, param: int = 0) -> None:
        if not self.connected:
            return
        seq = self._next_seq()
        pkt = build_face_set_system(seq, mode, 0, param)
        self._transport.write(pkt)
        self._tx_packets += 1
        if self._capture and self._capture.active:
            self._capture.capture_tx(
                "face",
                FaceCmdType.SET_SYSTEM,
                seq,
                struct.pack("<BBB", mode, 0, param),
            )

    def send_talking(self, talking: bool, energy: int = 0) -> None:
        """Send SET_TALKING command (speaking animation state + energy)."""
        if not self.connected:
            return
        energy_u8 = max(0, min(255, int(energy)))
        seq = self._next_seq()
        pkt = build_face_set_talking(seq, talking, energy_u8)
        self._transport.write(pkt)
        self._tx_packets += 1
        self.last_talking_energy_cmd = energy_u8 if talking else 0
        if self._capture and self._capture.active:
            self._capture.capture_tx(
                "face",
                FaceCmdType.SET_TALKING,
                seq,
                struct.pack("<BB", 1 if talking else 0, energy_u8),
            )

    def send_flags(self, flags: int) -> None:
        """Send SET_FLAGS command (renderer/animation feature toggles)."""
        if not self.connected:
            return
        flags_u8 = int(flags) & FACE_FLAGS_ALL
        seq = self._next_seq()
        pkt = build_face_set_flags(seq, flags_u8)
        self._transport.write(pkt)
        self._tx_packets += 1
        self.last_flags_cmd = flags_u8
        if self._capture and self._capture.active:
            self._capture.capture_tx(
                "face",
                FaceCmdType.SET_FLAGS,
                seq,
                struct.pack("<B", flags_u8),
            )

    def send_conv_state(self, conv_state: int) -> None:
        """Send SET_CONV_STATE command (conversation phase for border animation)."""
        if not self.connected:
            return
        seq = self._next_seq()
        pkt = build_face_set_conv_state(seq, int(conv_state))
        self._transport.write(pkt)
        self._tx_packets += 1
        if self._capture and self._capture.active:
            self._capture.capture_tx(
                "face",
                FaceCmdType.SET_CONV_STATE,
                seq,
                struct.pack("<B", conv_state & 0xFF),
            )

    def debug_snapshot(self) -> dict:
        now_ms = time.monotonic() * 1000.0
        age_ms = 0.0
        if self.telemetry.rx_mono_ms > 0:
            age_ms = max(0.0, now_ms - self.telemetry.rx_mono_ms)

        return {
            "connected": self.connected,
            "tx_packets": self._tx_packets,
            "rx_face_status_packets": self._rx_face_status_packets,
            "rx_touch_packets": self._rx_touch_packets,
            "rx_button_packets": self._rx_button_packets,
            "rx_heartbeat_packets": self._rx_heartbeat_packets,
            "rx_bad_payload_packets": self._rx_bad_payload_packets,
            "rx_unknown_packets": self._rx_unknown_packets,
            "last_status_seq": self.telemetry.seq,
            "last_status_age_ms": round(age_ms, 1),
            "last_status_flags": self.telemetry.flags,
            "last_talking_energy_cmd": self.last_talking_energy_cmd,
            "last_render_flags_cmd": self.last_flags_cmd,
            "last_button": self._button_snapshot(),
            "last_heartbeat": self._heartbeat_snapshot(),
            "transport": self._transport.debug_snapshot(),
        }

    # -- internals -----------------------------------------------------------

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) & 0xFF
        return s

    def _handle_packet(self, pkt: ParsedPacket) -> None:
        if self._capture and self._capture.active:
            self._capture.capture_rx("face", pkt.pkt_type, pkt.seq, pkt.payload)

        if pkt.pkt_type == FaceTelType.FACE_STATUS:
            try:
                status = FaceStatusPayload.unpack(pkt.payload)
            except ValueError as e:
                self._rx_bad_payload_packets += 1
                log.warning("face: bad FACE_STATUS: %s", e)
                return
            self._rx_face_status_packets += 1
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
                self._rx_bad_payload_packets += 1
                log.warning("face: bad TOUCH_EVENT: %s", e)
                return
            self._rx_touch_packets += 1
            touch_evt = TouchEvent(te.event_type, te.x, te.y, time.monotonic() * 1000.0)
            self.last_touch = touch_evt
            for touch_cb in tuple(self._touch_subscribers):
                touch_cb(touch_evt)

        elif pkt.pkt_type == FaceTelType.BUTTON_EVENT:
            try:
                bp = FaceButtonEventPayload.unpack(pkt.payload)
            except ValueError as e:
                self._rx_bad_payload_packets += 1
                log.warning("face: bad BUTTON_EVENT: %s", e)
                return
            self._rx_button_packets += 1
            button_evt = ButtonEvent(
                button_id=bp.button_id,
                event_type=bp.event_type,
                state=bp.state,
                timestamp_mono_ms=time.monotonic() * 1000.0,
            )
            self.last_button = button_evt
            for button_cb in tuple(self._button_subscribers):
                button_cb(button_evt)

        elif pkt.pkt_type == FaceTelType.HEARTBEAT:
            try:
                hb = FaceHeartbeatPayload.unpack(pkt.payload)
            except ValueError as e:
                self._rx_bad_payload_packets += 1
                log.warning("face: bad HEARTBEAT: %s", e)
                return
            self._rx_heartbeat_packets += 1
            self.last_heartbeat = HeartbeatTelemetry(
                uptime_ms=hb.uptime_ms,
                status_tx_count=hb.status_tx_count,
                touch_tx_count=hb.touch_tx_count,
                button_tx_count=hb.button_tx_count,
                usb_tx_calls=hb.usb_tx_calls,
                usb_tx_bytes_requested=hb.usb_tx_bytes_requested,
                usb_tx_bytes_queued=hb.usb_tx_bytes_queued,
                usb_tx_short_writes=hb.usb_tx_short_writes,
                usb_tx_flush_ok=hb.usb_tx_flush_ok,
                usb_tx_flush_not_finished=hb.usb_tx_flush_not_finished,
                usb_tx_flush_timeout=hb.usb_tx_flush_timeout,
                usb_tx_flush_error=hb.usb_tx_flush_error,
                usb_rx_calls=hb.usb_rx_calls,
                usb_rx_bytes=hb.usb_rx_bytes,
                usb_rx_errors=hb.usb_rx_errors,
                usb_line_state_events=hb.usb_line_state_events,
                usb_dtr=bool(hb.usb_dtr),
                usb_rts=bool(hb.usb_rts),
                ptt_listening=bool(hb.ptt_listening),
                seq=pkt.seq,
                rx_mono_ms=time.monotonic() * 1000.0,
            )

        else:
            self._rx_unknown_packets += 1
            log.debug("face: unknown packet type 0x%02X", pkt.pkt_type)

    def _button_snapshot(self) -> dict | None:
        btn = self.last_button
        if btn is None:
            return None
        return {
            "button_id": btn.button_id,
            "event_type": btn.event_type,
            "state": btn.state,
            "timestamp_mono_ms": round(btn.timestamp_mono_ms, 1),
        }

    def _heartbeat_snapshot(self) -> dict | None:
        hb = self.last_heartbeat
        if hb is None:
            return None
        return {
            "uptime_ms": hb.uptime_ms,
            "status_tx_count": hb.status_tx_count,
            "touch_tx_count": hb.touch_tx_count,
            "button_tx_count": hb.button_tx_count,
            "usb": {
                "tx_calls": hb.usb_tx_calls,
                "tx_bytes_requested": hb.usb_tx_bytes_requested,
                "tx_bytes_queued": hb.usb_tx_bytes_queued,
                "tx_short_writes": hb.usb_tx_short_writes,
                "tx_flush_ok": hb.usb_tx_flush_ok,
                "tx_flush_not_finished": hb.usb_tx_flush_not_finished,
                "tx_flush_timeout": hb.usb_tx_flush_timeout,
                "tx_flush_error": hb.usb_tx_flush_error,
                "rx_calls": hb.usb_rx_calls,
                "rx_bytes": hb.usb_rx_bytes,
                "rx_errors": hb.usb_rx_errors,
                "line_state_events": hb.usb_line_state_events,
                "dtr": hb.usb_dtr,
                "rts": hb.usb_rts,
            },
            "ptt_listening": hb.ptt_listening,
            "seq": hb.seq,
            "rx_mono_ms": round(hb.rx_mono_ms, 1),
        }
