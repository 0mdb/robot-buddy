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
    SET_CONFIG = 0x25


class FaceTelType(IntEnum):
    FACE_STATUS = 0x90
    TOUCH_EVENT = 0x91


class FaceMood(IntEnum):
    DEFAULT = 0
    TIRED = 1
    ANGRY = 2
    HAPPY = 3


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
