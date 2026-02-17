"""Face MCU client — sends face commands, receives touch/status telemetry."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from supervisor.devices.protocol import (
    FaceCfgId,
    FaceHeartbeatPayload,
    FaceMicProbePayload,
    FaceStatusPayload,
    FaceTelType,
    ParsedPacket,
    TouchEventPayload,
    build_face_audio_data,
    build_face_set_config,
    build_face_gesture,
    build_face_set_state,
    build_face_set_system,
    build_face_set_talking,
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


@dataclass(slots=True)
class MicProbeTelemetry:
    probe_seq: int = 0
    duration_ms: int = 0
    sample_count: int = 0
    read_timeouts: int = 0
    read_errors: int = 0
    selected_rms_x10: int = 0
    selected_peak: int = 0
    selected_dbfs_x10: int = 0
    selected_channel: int = 0
    active: bool = False
    rx_mono_ms: float = 0.0


@dataclass(slots=True)
class HeartbeatTelemetry:
    uptime_ms: int = 0
    status_tx_count: int = 0
    touch_tx_count: int = 0
    mic_probe_seq: int = 0
    mic_activity: bool = False
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
    seq: int = 0
    rx_mono_ms: float = 0.0


class FaceClient:
    """Send commands to and receive telemetry from the face MCU."""

    def __init__(self, transport: SerialTransport) -> None:
        self._transport = transport
        self._seq = 0
        self.telemetry = FaceTelemetry()
        self.last_touch: TouchEvent | None = None
        self.last_mic_probe: MicProbeTelemetry | None = None
        self.last_heartbeat: HeartbeatTelemetry | None = None
        self._on_touch: Callable[[TouchEvent], None] | None = None
        self._tx_packets = 0
        self._rx_face_status_packets = 0
        self._rx_touch_packets = 0
        self._rx_mic_probe_packets = 0
        self._rx_heartbeat_packets = 0
        self._rx_bad_payload_packets = 0
        self._rx_unknown_packets = 0

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
        self._tx_packets += 1

    def send_gesture(self, gesture_id: int = 0, duration_ms: int = 0) -> None:
        if not self.connected:
            return
        pkt = build_face_gesture(self._next_seq(), gesture_id, duration_ms)
        self._transport.write(pkt)
        self._tx_packets += 1

    def send_system_mode(self, mode: int = 0, param: int = 0) -> None:
        if not self.connected:
            return
        pkt = build_face_set_system(self._next_seq(), mode, 0, param)
        self._transport.write(pkt)
        self._tx_packets += 1

    def send_talking(self, talking: bool, energy: int = 0) -> None:
        """Send SET_TALKING command (speaking animation state + audio energy)."""
        if not self.connected:
            return
        pkt = build_face_set_talking(self._next_seq(), talking, energy)
        self._transport.write(pkt)
        self._tx_packets += 1

    def send_audio_data(self, pcm_chunk: bytes) -> None:
        """Send AUDIO_DATA with PCM chunk (16-bit, 16 kHz, mono)."""
        if not self.connected:
            return
        pkt = build_face_audio_data(self._next_seq(), pcm_chunk)
        self._transport.write(pkt)
        self._tx_packets += 1

    def send_set_config_u32(self, param_id: int, value_u32: int) -> bool:
        if not self.connected:
            return False
        pkt = build_face_set_config(self._next_seq(), param_id, value_u32)
        sent = self._transport.write(pkt)
        self._tx_packets += 1
        if not sent:
            log.warning("face: failed to send SET_CONFIG 0x%02X", param_id)
        return sent

    def run_audio_tone(self, duration_ms: int = 1000) -> bool:
        return self.send_set_config_u32(
            FaceCfgId.AUDIO_TEST_TONE_MS, max(1, int(duration_ms))
        )

    def run_mic_probe(self, duration_ms: int = 2000) -> bool:
        return self.send_set_config_u32(
            FaceCfgId.AUDIO_MIC_PROBE_MS, max(1, int(duration_ms))
        )

    def dump_audio_regs(self) -> bool:
        return self.send_set_config_u32(FaceCfgId.AUDIO_REG_DUMP, 0)

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
            "rx_mic_probe_packets": self._rx_mic_probe_packets,
            "rx_heartbeat_packets": self._rx_heartbeat_packets,
            "rx_bad_payload_packets": self._rx_bad_payload_packets,
            "rx_unknown_packets": self._rx_unknown_packets,
            "last_status_seq": self.telemetry.seq,
            "last_status_age_ms": round(age_ms, 1),
            "last_status_flags": self.telemetry.flags,
            "last_mic_probe": self._mic_probe_snapshot(),
            "last_heartbeat": self._heartbeat_snapshot(),
            "transport": self._transport.debug_snapshot(),
        }

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
            evt = TouchEvent(te.event_type, te.x, te.y, time.monotonic() * 1000.0)
            self.last_touch = evt
            if self._on_touch:
                self._on_touch(evt)
        elif pkt.pkt_type == FaceTelType.MIC_PROBE:
            try:
                mp = FaceMicProbePayload.unpack(pkt.payload)
            except ValueError as e:
                self._rx_bad_payload_packets += 1
                log.warning("face: bad MIC_PROBE: %s", e)
                return
            self._rx_mic_probe_packets += 1
            self.last_mic_probe = MicProbeTelemetry(
                probe_seq=mp.probe_seq,
                duration_ms=mp.duration_ms,
                sample_count=mp.sample_count,
                read_timeouts=mp.read_timeouts,
                read_errors=mp.read_errors,
                selected_rms_x10=mp.selected_rms_x10,
                selected_peak=mp.selected_peak,
                selected_dbfs_x10=mp.selected_dbfs_x10,
                selected_channel=mp.selected_channel,
                active=bool(mp.active),
                rx_mono_ms=time.monotonic() * 1000.0,
            )
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
                mic_probe_seq=hb.mic_probe_seq,
                mic_activity=bool(hb.mic_activity),
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
                seq=pkt.seq,
                rx_mono_ms=time.monotonic() * 1000.0,
            )
        else:
            self._rx_unknown_packets += 1
            log.debug("face: unknown packet type 0x%02X", pkt.pkt_type)

    def _mic_probe_snapshot(self) -> dict | None:
        mp = self.last_mic_probe
        if mp is None:
            return None
        return {
            "probe_seq": mp.probe_seq,
            "duration_ms": mp.duration_ms,
            "sample_count": mp.sample_count,
            "read_timeouts": mp.read_timeouts,
            "read_errors": mp.read_errors,
            "selected_rms_x10": mp.selected_rms_x10,
            "selected_peak": mp.selected_peak,
            "selected_dbfs_x10": mp.selected_dbfs_x10,
            "selected_channel": mp.selected_channel,
            "active": mp.active,
            "rx_mono_ms": round(mp.rx_mono_ms, 1),
        }

    def _heartbeat_snapshot(self) -> dict | None:
        hb = self.last_heartbeat
        if hb is None:
            return None
        return {
            "uptime_ms": hb.uptime_ms,
            "status_tx_count": hb.status_tx_count,
            "touch_tx_count": hb.touch_tx_count,
            "mic_probe_seq": hb.mic_probe_seq,
            "mic_activity": hb.mic_activity,
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
            "seq": hb.seq,
            "rx_mono_ms": round(hb.rx_mono_ms, 1),
        }
