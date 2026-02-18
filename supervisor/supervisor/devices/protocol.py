"""Binary protocol matching esp32-reflex wire format.

Packet structure (before COBS):
    [type:u8] [seq:u8] [payload:N] [crc16:u16-LE]

On wire: COBS-encode the above, then append 0x00 delimiter.
All multi-byte values are little-endian.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from supervisor.io.cobs import decode as cobs_decode
from supervisor.io.cobs import encode as cobs_encode
from supervisor.io.crc import crc16


# -- Packet type IDs --------------------------------------------------------


class CmdType(IntEnum):
    SET_TWIST = 0x10
    STOP = 0x11
    ESTOP = 0x12
    SET_LIMITS = 0x13
    CLEAR_FAULTS = 0x14
    SET_CONFIG = 0x15


class TelType(IntEnum):
    STATE = 0x80


# -- Fault flags (bitfield, matches Fault enum in shared_state.h) -----------


class Fault(IntEnum):
    NONE = 0
    CMD_TIMEOUT = 1 << 0
    ESTOP = 1 << 1
    TILT = 1 << 2
    STALL = 1 << 3
    IMU_FAIL = 1 << 4
    BROWNOUT = 1 << 5
    OBSTACLE = 1 << 6


class RangeStatus(IntEnum):
    OK = 0
    TIMEOUT = 1
    OUT_OF_RANGE = 2
    NOT_READY = 3


# -- Face command types (host → face MCU): 0x20–0x2F -----------------------


class FaceCmdType(IntEnum):
    SET_STATE = 0x20
    GESTURE = 0x21
    SET_SYSTEM = 0x22
    SET_TALKING = 0x23
    AUDIO_DATA = 0x24
    SET_CONFIG = 0x25


class FaceTelType(IntEnum):
    FACE_STATUS = 0x90
    TOUCH_EVENT = 0x91
    MIC_PROBE = 0x92
    HEARTBEAT = 0x93
    MIC_AUDIO = 0x94


class FaceCfgId(IntEnum):
    AUDIO_TEST_TONE_MS = 0xA0
    AUDIO_MIC_PROBE_MS = 0xA1
    AUDIO_REG_DUMP = 0xA2
    AUDIO_MIC_STREAM_ENABLE = 0xA3


class FaceMood(IntEnum):
    NEUTRAL = 0
    HAPPY = 1
    EXCITED = 2
    CURIOUS = 3
    SAD = 4
    SCARED = 5
    ANGRY = 6
    SURPRISED = 7
    SLEEPY = 8
    LOVE = 9
    SILLY = 10
    THINKING = 11


class FaceGesture(IntEnum):
    BLINK = 0
    WINK_L = 1
    WINK_R = 2
    CONFUSED = 3
    LAUGH = 4
    SURPRISE = 5
    HEART = 6
    X_EYES = 7
    SLEEPY = 8
    RAGE = 9
    NOD = 10
    HEADSHAKE = 11
    WIGGLE = 12


class FaceSystemMode(IntEnum):
    NONE = 0
    BOOTING = 1
    ERROR_DISPLAY = 2
    LOW_BATTERY = 3
    UPDATING = 4
    SHUTTING_DOWN = 5


class TouchEventType(IntEnum):
    PRESS = 0
    RELEASE = 1
    DRAG = 2


# -- Telemetry payloads -----------------------------------------------------


@dataclass(slots=True)
class StatePayload:
    speed_l_mm_s: int
    speed_r_mm_s: int
    gyro_z_mrad_s: int
    battery_mv: int
    fault_flags: int
    range_mm: int
    range_status: int

    _FMT = struct.Struct("<hhhHHHB")  # 15 bytes

    @classmethod
    def unpack(cls, data: bytes) -> StatePayload:
        if len(data) < cls._FMT.size:
            raise ValueError(f"STATE payload too short: {len(data)} < {cls._FMT.size}")
        fields = cls._FMT.unpack_from(data)
        return cls(*fields)


@dataclass(slots=True)
class FaceStatusPayload:
    mood_id: int
    active_gesture: int
    system_mode: int
    flags: int

    _FMT = struct.Struct("<BBBB")  # 4 bytes

    @classmethod
    def unpack(cls, data: bytes) -> FaceStatusPayload:
        if len(data) < cls._FMT.size:
            raise ValueError(f"FACE_STATUS payload too short: {len(data)}")
        return cls(*cls._FMT.unpack_from(data))


@dataclass(slots=True)
class TouchEventPayload:
    event_type: int
    x: int
    y: int

    _FMT = struct.Struct("<BHH")  # 5 bytes

    @classmethod
    def unpack(cls, data: bytes) -> TouchEventPayload:
        if len(data) < cls._FMT.size:
            raise ValueError(f"TOUCH_EVENT payload too short: {len(data)}")
        return cls(*cls._FMT.unpack_from(data))


@dataclass(slots=True)
class FaceMicProbePayload:
    probe_seq: int
    duration_ms: int
    sample_count: int
    read_timeouts: int
    read_errors: int
    selected_rms_x10: int
    selected_peak: int
    selected_dbfs_x10: int
    selected_channel: int
    active: int

    _FMT = struct.Struct("<IIIHHHHhBB")  # 24 bytes

    @classmethod
    def unpack(cls, data: bytes) -> FaceMicProbePayload:
        if len(data) < cls._FMT.size:
            raise ValueError(f"MIC_PROBE payload too short: {len(data)}")
        return cls(*cls._FMT.unpack_from(data))


@dataclass(slots=True)
class FaceMicAudioPayload:
    chunk_seq: int
    chunk_len: int
    flags: int
    pcm: bytes

    _HDR_FMT = struct.Struct("<IHBB")  # chunk_seq, chunk_len, flags, reserved

    @classmethod
    def unpack(cls, data: bytes) -> FaceMicAudioPayload:
        if len(data) < cls._HDR_FMT.size:
            raise ValueError(f"MIC_AUDIO payload too short: {len(data)}")
        chunk_seq, chunk_len, flags, _ = cls._HDR_FMT.unpack_from(data)
        end = cls._HDR_FMT.size + chunk_len
        if len(data) < end:
            raise ValueError(
                f"MIC_AUDIO payload truncated: have={len(data)} need={end}"
            )
        pcm = data[cls._HDR_FMT.size:end]
        return cls(chunk_seq=chunk_seq, chunk_len=chunk_len, flags=flags, pcm=pcm)


@dataclass(slots=True)
class FaceHeartbeatPayload:
    uptime_ms: int
    status_tx_count: int
    touch_tx_count: int
    mic_probe_seq: int
    mic_activity: int
    usb_tx_calls: int
    usb_tx_bytes_requested: int
    usb_tx_bytes_queued: int
    usb_tx_short_writes: int
    usb_tx_flush_ok: int
    usb_tx_flush_not_finished: int
    usb_tx_flush_timeout: int
    usb_tx_flush_error: int
    usb_rx_calls: int
    usb_rx_bytes: int
    usb_rx_errors: int
    usb_line_state_events: int
    usb_dtr: int
    usb_rts: int
    speaker_rx_chunks: int
    speaker_rx_drops: int
    speaker_rx_bytes: int
    speaker_play_chunks: int
    speaker_play_errors: int
    mic_capture_chunks: int
    mic_tx_chunks: int
    mic_tx_drops: int
    mic_overruns: int
    mic_queue_depth: int
    mic_stream_enabled: int
    audio_reserved: int

    _BASE_FMT = struct.Struct("<IIIIB")  # 17 bytes
    _USB_FMT = struct.Struct("<IIIIIIIIIIIIBB")  # 50 bytes
    _AUDIO_FMT = struct.Struct("<IIIIIIIIIIBB")  # 42 bytes

    @classmethod
    def unpack(cls, data: bytes) -> FaceHeartbeatPayload:
        if len(data) < cls._BASE_FMT.size:
            raise ValueError(f"HEARTBEAT payload too short: {len(data)}")
        base = cls._BASE_FMT.unpack_from(data)

        usb = (
            0,  # usb_tx_calls
            0,  # usb_tx_bytes_requested
            0,  # usb_tx_bytes_queued
            0,  # usb_tx_short_writes
            0,  # usb_tx_flush_ok
            0,  # usb_tx_flush_not_finished
            0,  # usb_tx_flush_timeout
            0,  # usb_tx_flush_error
            0,  # usb_rx_calls
            0,  # usb_rx_bytes
            0,  # usb_rx_errors
            0,  # usb_line_state_events
            0,  # usb_dtr
            0,  # usb_rts
        )
        if len(data) >= (cls._BASE_FMT.size + cls._USB_FMT.size):
            usb = cls._USB_FMT.unpack_from(data, cls._BASE_FMT.size)

        audio = (
            0,  # speaker_rx_chunks
            0,  # speaker_rx_drops
            0,  # speaker_rx_bytes
            0,  # speaker_play_chunks
            0,  # speaker_play_errors
            0,  # mic_capture_chunks
            0,  # mic_tx_chunks
            0,  # mic_tx_drops
            0,  # mic_overruns
            0,  # mic_queue_depth
            0,  # mic_stream_enabled
            0,  # audio_reserved
        )
        audio_off = cls._BASE_FMT.size + cls._USB_FMT.size
        if len(data) >= (audio_off + cls._AUDIO_FMT.size):
            audio = cls._AUDIO_FMT.unpack_from(data, audio_off)

        return cls(*base, *usb, *audio)


# -- Packet building --------------------------------------------------------

_TWIST_FMT = struct.Struct("<hh")
_STOP_FMT = struct.Struct("<B")
_CLEAR_FMT = struct.Struct("<H")
_CONFIG_FMT = struct.Struct("<B4s")  # param_id:u8, value:4 bytes


def build_packet(pkt_type: int, seq: int, payload: bytes = b"") -> bytes:
    """Build a wire-ready packet: COBS-encode(type|seq|payload|crc16-LE) + 0x00."""
    raw = bytes([pkt_type & 0xFF, seq & 0xFF]) + payload
    crc = crc16(raw)
    raw += struct.pack("<H", crc)
    return cobs_encode(raw) + b"\x00"


def build_set_twist(seq: int, v_mm_s: int, w_mrad_s: int) -> bytes:
    return build_packet(CmdType.SET_TWIST, seq, _TWIST_FMT.pack(v_mm_s, w_mrad_s))


def build_stop(seq: int, reason: int = 0) -> bytes:
    return build_packet(CmdType.STOP, seq, _STOP_FMT.pack(reason))


def build_estop(seq: int) -> bytes:
    return build_packet(CmdType.ESTOP, seq)


def build_clear_faults(seq: int, mask: int = 0xFFFF) -> bytes:
    return build_packet(CmdType.CLEAR_FAULTS, seq, _CLEAR_FMT.pack(mask))


def build_set_config(seq: int, param_id: int, value_bytes: bytes) -> bytes:
    """Build a SET_CONFIG packet. value_bytes must be exactly 4 bytes (LE)."""
    if len(value_bytes) != 4:
        raise ValueError(f"SET_CONFIG value must be 4 bytes, got {len(value_bytes)}")
    return build_packet(
        CmdType.SET_CONFIG, seq, _CONFIG_FMT.pack(param_id, value_bytes)
    )


# -- Face packet building ----------------------------------------------------

_FACE_SET_STATE_FMT = struct.Struct("<BBbbB")  # mood, intensity, gaze_x, gaze_y, brightness
_FACE_GESTURE_FMT = struct.Struct("<BH")  # gesture_id, duration_ms
_FACE_SET_SYSTEM_FMT = struct.Struct("<BBB")  # mode, phase, param
_FACE_SET_TALKING_FMT = struct.Struct("<BB")  # talking, energy
_FACE_AUDIO_DATA_HDR_FMT = struct.Struct("<H")  # chunk_len


def build_face_set_state(
    seq: int,
    mood_id: int,
    intensity: int = 255,
    gaze_x: int = 0,
    gaze_y: int = 0,
    brightness: int = 200,
) -> bytes:
    payload = _FACE_SET_STATE_FMT.pack(mood_id, intensity, gaze_x, gaze_y, brightness)
    return build_packet(FaceCmdType.SET_STATE, seq, payload)


def build_face_gesture(seq: int, gesture_id: int, duration_ms: int = 0) -> bytes:
    payload = _FACE_GESTURE_FMT.pack(gesture_id, duration_ms)
    return build_packet(FaceCmdType.GESTURE, seq, payload)


def build_face_set_system(
    seq: int, mode: int, phase: int = 0, param: int = 0
) -> bytes:
    payload = _FACE_SET_SYSTEM_FMT.pack(mode, phase, param)
    return build_packet(FaceCmdType.SET_SYSTEM, seq, payload)


def build_face_set_config(seq: int, param_id: int, value_u32: int) -> bytes:
    """Build a face SET_CONFIG packet using a 32-bit little-endian value."""
    value_bytes = struct.pack("<I", value_u32 & 0xFFFFFFFF)
    payload = _CONFIG_FMT.pack(param_id & 0xFF, value_bytes)
    return build_packet(FaceCmdType.SET_CONFIG, seq, payload)


def build_face_set_talking(seq: int, talking: bool, energy: int = 0) -> bytes:
    """Build a SET_TALKING packet (speaking animation state + energy)."""
    payload = _FACE_SET_TALKING_FMT.pack(1 if talking else 0, max(0, min(255, energy)))
    return build_packet(FaceCmdType.SET_TALKING, seq, payload)


def build_face_audio_data(seq: int, pcm_chunk: bytes) -> bytes:
    """Build an AUDIO_DATA packet with PCM audio chunk (16-bit, 16 kHz, mono)."""
    payload = _FACE_AUDIO_DATA_HDR_FMT.pack(len(pcm_chunk)) + pcm_chunk
    return build_packet(FaceCmdType.AUDIO_DATA, seq, payload)


# -- Packet parsing ----------------------------------------------------------


@dataclass(slots=True)
class ParsedPacket:
    pkt_type: int
    seq: int
    payload: bytes


def parse_frame(frame: bytes) -> ParsedPacket:
    """Parse a COBS-encoded frame (without the trailing 0x00 delimiter).

    Raises ValueError on CRC mismatch or truncated data.
    """
    raw = cobs_decode(frame)
    if len(raw) < 4:  # type + seq + crc16
        raise ValueError(f"packet too short: {len(raw)} bytes")

    body = raw[:-2]
    crc_recv = struct.unpack_from("<H", raw, len(raw) - 2)[0]
    crc_calc = crc16(body)
    if crc_recv != crc_calc:
        raise ValueError(f"CRC mismatch: recv=0x{crc_recv:04X} calc=0x{crc_calc:04X}")

    return ParsedPacket(
        pkt_type=body[0],
        seq=body[1],
        payload=body[2:],
    )
