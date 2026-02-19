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
    SET_FLAGS = 0x24


class FaceTelType(IntEnum):
    FACE_STATUS = 0x90
    TOUCH_EVENT = 0x91
    BUTTON_EVENT = 0x92
    HEARTBEAT = 0x93


class FaceButtonId(IntEnum):
    PTT = 0
    ACTION = 1


class FaceButtonEventType(IntEnum):
    PRESS = 0
    RELEASE = 1
    TOGGLE = 2
    CLICK = 3


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


FACE_FLAG_IDLE_WANDER = 1 << 0
FACE_FLAG_AUTOBLINK = 1 << 1
FACE_FLAG_SOLID_EYE = 1 << 2
FACE_FLAG_SHOW_MOUTH = 1 << 3
FACE_FLAG_EDGE_GLOW = 1 << 4
FACE_FLAG_SPARKLE = 1 << 5
FACE_FLAG_AFTERGLOW = 1 << 6
FACE_FLAGS_ALL = (
    FACE_FLAG_IDLE_WANDER
    | FACE_FLAG_AUTOBLINK
    | FACE_FLAG_SOLID_EYE
    | FACE_FLAG_SHOW_MOUTH
    | FACE_FLAG_EDGE_GLOW
    | FACE_FLAG_SPARKLE
    | FACE_FLAG_AFTERGLOW
)


def pack_face_flags(
    *,
    idle_wander: bool = True,
    autoblink: bool = True,
    solid_eye: bool = True,
    show_mouth: bool = True,
    edge_glow: bool = True,
    sparkle: bool = True,
    afterglow: bool = True,
) -> int:
    flags = 0
    if idle_wander:
        flags |= FACE_FLAG_IDLE_WANDER
    if autoblink:
        flags |= FACE_FLAG_AUTOBLINK
    if solid_eye:
        flags |= FACE_FLAG_SOLID_EYE
    if show_mouth:
        flags |= FACE_FLAG_SHOW_MOUTH
    if edge_glow:
        flags |= FACE_FLAG_EDGE_GLOW
    if sparkle:
        flags |= FACE_FLAG_SPARKLE
    if afterglow:
        flags |= FACE_FLAG_AFTERGLOW
    return flags


VALID_FACE_MOOD_IDS = frozenset(m.value for m in FaceMood)
VALID_FACE_GESTURE_IDS = frozenset(g.value for g in FaceGesture)


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
class FaceButtonEventPayload:
    button_id: int
    event_type: int
    state: int
    reserved: int

    _FMT = struct.Struct("<BBBB")

    @classmethod
    def unpack(cls, data: bytes) -> FaceButtonEventPayload:
        if len(data) < cls._FMT.size:
            raise ValueError(f"BUTTON_EVENT payload too short: {len(data)}")
        return cls(*cls._FMT.unpack_from(data))


@dataclass(slots=True)
class FaceHeartbeatPayload:
    uptime_ms: int
    status_tx_count: int
    touch_tx_count: int
    button_tx_count: int
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
    ptt_listening: int
    reserved: int

    _BASE_FMT = struct.Struct("<IIII")  # 16 bytes
    _USB_FMT = struct.Struct("<IIIIIIIIIIII")  # 48 bytes
    _TAIL_FMT = struct.Struct("<BBBB")  # dtr, rts, ptt_listening, reserved

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
        )
        if len(data) >= (cls._BASE_FMT.size + cls._USB_FMT.size):
            usb = cls._USB_FMT.unpack_from(data, cls._BASE_FMT.size)

        tail = (
            0,  # usb_dtr
            0,  # usb_rts
            0,  # ptt_listening
            0,  # reserved
        )
        tail_off = cls._BASE_FMT.size + cls._USB_FMT.size
        if len(data) >= (tail_off + cls._TAIL_FMT.size):
            tail = cls._TAIL_FMT.unpack_from(data, tail_off)

        return cls(
            uptime_ms=base[0],
            status_tx_count=base[1],
            touch_tx_count=base[2],
            button_tx_count=base[3],
            usb_tx_calls=usb[0],
            usb_tx_bytes_requested=usb[1],
            usb_tx_bytes_queued=usb[2],
            usb_tx_short_writes=usb[3],
            usb_tx_flush_ok=usb[4],
            usb_tx_flush_not_finished=usb[5],
            usb_tx_flush_timeout=usb[6],
            usb_tx_flush_error=usb[7],
            usb_rx_calls=usb[8],
            usb_rx_bytes=usb[9],
            usb_rx_errors=usb[10],
            usb_line_state_events=usb[11],
            usb_dtr=tail[0],
            usb_rts=tail[1],
            ptt_listening=tail[2],
            reserved=tail[3],
        )


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
_FACE_SET_FLAGS_FMT = struct.Struct("<B")  # renderer/animation feature flags


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

def build_face_set_talking(seq: int, talking: bool, energy: int = 0) -> bytes:
    """Build a SET_TALKING packet (speaking animation state + energy)."""
    payload = _FACE_SET_TALKING_FMT.pack(1 if talking else 0, max(0, min(255, energy)))
    return build_packet(FaceCmdType.SET_TALKING, seq, payload)


def build_face_set_flags(seq: int, flags: int) -> bytes:
    """Build a SET_FLAGS packet (renderer/animation feature toggles)."""
    payload = _FACE_SET_FLAGS_FMT.pack(flags & FACE_FLAGS_ALL)
    return build_packet(FaceCmdType.SET_FLAGS, seq, payload)


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
