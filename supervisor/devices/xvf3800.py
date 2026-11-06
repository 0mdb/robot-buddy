"""XMOS XVF3800 (Seeed reSpeaker Flex / 4-Mic Array) control over USB.

The USB firmware shows up as two things on one cable: a UAC 2.0 sound card
(audio, handled by ALSA: arecord / aplay) and a vendor control interface on
endpoint 0 (this module). Control is a flat set of named parameters, each
addressed by a resource id and a command id:

    read : bmRequestType 0xC0, bRequest 0, wValue 0x80 | cmdid, wIndex resid
           reply = 1 status byte + count values (little-endian)
    write: bmRequestType 0x40, bRequest 0, wValue cmdid, wIndex resid
           payload = count values (little-endian)

Status 0 = ok, 64 = busy (retry), anything else = error. Ids and the protocol
are taken from Seeed's ``python_control/xvf_host.py``
(github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY). ``xvf_host.py -l`` on
the real board lists every parameter; check a new firmware against PARAMS.

pyusb is blocking: call from a thread (``asyncio.to_thread``).
"""

from __future__ import annotations

import logging
import math
import struct
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

log = logging.getLogger(__name__)

VID = 0x2886  # Seeed
PID = 0x001A  # reSpeaker XVF3800 USB firmware (Flex and 4-Mic Array)

STATUS_OK = 0
STATUS_RETRY = 64
_MAX_RETRIES = 100
_RETRY_SLEEP_S = 0.002
_TIMEOUT_MS = 1000

_FMT = {
    "uint8": "B",
    "uint16": "H",
    "uint32": "I",
    "int32": "i",
    "float": "f",
    "radians": "f",
}
_SIZE = {
    "uint8": 1,
    "char": 1,
    "uint16": 2,
    "uint32": 4,
    "int32": 4,
    "float": 4,
    "radians": 4,
}


@dataclass(frozen=True)
class Param:
    resid: int
    cmdid: int
    count: int
    type: str  # uint8 | uint16 | uint32 | int32 | float | radians | char
    access: str  # ro | wo | rw


# The subset the supervisor uses (ids from Seeed's xvf_host.py).
PARAMS: dict[str, Param] = {
    # application
    "VERSION": Param(48, 0, 3, "uint8", "ro"),
    "REBOOT": Param(48, 7, 1, "uint8", "wo"),
    "SAVE_CONFIGURATION": Param(48, 9, 1, "uint8", "wo"),
    "CLEAR_CONFIGURATION": Param(48, 10, 1, "uint8", "wo"),
    # AEC / beamformer: beams 0, 1 = focused, 2 = free-running, 3 = auto-select
    "AEC_AZIMUTH_VALUES": Param(33, 75, 4, "radians", "ro"),
    "AEC_SPENERGY_VALUES": Param(33, 80, 4, "float", "ro"),
    "AEC_FIXEDBEAMSONOFF": Param(33, 37, 1, "int32", "rw"),
    "AEC_FIXEDBEAMSAZIMUTH_VALUES": Param(33, 81, 2, "radians", "rw"),
    "AEC_FIXEDBEAMSGATING": Param(33, 83, 1, "uint8", "rw"),
    # audio manager
    "AUDIO_MGR_MIC_GAIN": Param(35, 0, 1, "float", "rw"),
    "AUDIO_MGR_REF_GAIN": Param(35, 1, 1, "float", "rw"),
    # [0] processed DoA (NaN when neither fixed beam has speech), [1] auto-select beam DoA.
    # Firmware <= 2.0.0 returned something else here.
    "AUDIO_MGR_SELECTED_AZIMUTHS": Param(35, 11, 2, "radians", "ro"),
    "AUDIO_MGR_OP_L": Param(35, 15, 2, "uint8", "rw"),  # category, source
    "AUDIO_MGR_OP_R": Param(35, 19, 2, "uint8", "rw"),
    # Seeed board firmware: [0] DoA 0..359 deg, [1] 1 when speech is detected
    "DOA_VALUE": Param(20, 18, 2, "uint16", "ro"),
    "GPO_READ_VALUES": Param(20, 0, 5, "uint8", "ro"),
    "GPO_WRITE_VALUE": Param(20, 1, 2, "uint8", "wo"),
    # post-processing
    "PP_AGCONOFF": Param(17, 10, 1, "int32", "rw"),
    "PP_AGCMAXGAIN": Param(17, 11, 1, "float", "rw"),
    "PP_AGCDESIREDLEVEL": Param(17, 12, 1, "float", "rw"),
    "PP_AGCGAIN": Param(17, 13, 1, "float", "rw"),
    "PP_MIN_NS": Param(17, 21, 1, "float", "rw"),
    "PP_MIN_NN": Param(17, 22, 1, "float", "rw"),
}


class XvfError(RuntimeError):
    pass


class Transport(Protocol):
    def ctrl_in(self, wvalue: int, windex: int, length: int) -> bytes: ...

    def ctrl_out(self, wvalue: int, windex: int, data: bytes) -> None: ...

    def close(self) -> None: ...


# ── encoding ──────────────────────────────────────────────────────────


def reply_length(p: Param) -> int:
    """Bytes in a read reply, status byte included."""
    return 1 + p.count * _SIZE[p.type]


def encode(p: Param, values: Sequence[float | int] | str) -> bytes:
    if p.type == "char":
        data = str(values).encode("utf-8")
        if len(data) > p.count:
            raise XvfError(f"string longer than {p.count} bytes")
        return data
    if isinstance(values, str) or len(values) != p.count:
        raise XvfError(f"expected {p.count} value(s)")
    fmt = _FMT[p.type]
    vals = [float(v) if fmt == "f" else int(v) for v in values]
    return struct.pack("<" + fmt * p.count, *vals)


def decode(p: Param, payload: bytes) -> tuple[float | int, ...] | str:
    """Decode the values after the status byte."""
    if p.type == "char":
        return payload.rstrip(b"\x00").decode("utf-8", errors="ignore")
    need = p.count * _SIZE[p.type]
    if len(payload) < need:
        raise XvfError(f"short reply: {len(payload)} < {need} bytes")
    return struct.unpack("<" + _FMT[p.type] * p.count, payload[:need])


# ── transports ────────────────────────────────────────────────────────


class UsbTransport:
    """pyusb on libusb. Needs read/write access to the device (udev rule)."""

    def __init__(self, vid: int = VID, pid: int = PID) -> None:
        try:
            import usb.core  # type: ignore[import-untyped]
        except ImportError as e:  # pragma: no cover - depends on install
            raise XvfError("pyusb not installed (supervisor[ear] extra)") from e
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            raise XvfError(f"no USB device {vid:04x}:{pid:04x}")
        self._dev = dev

    def ctrl_in(self, wvalue: int, windex: int, length: int) -> bytes:
        return bytes(
            self._dev.ctrl_transfer(0xC0, 0, wvalue, windex, length, _TIMEOUT_MS)
        )

    def ctrl_out(self, wvalue: int, windex: int, data: bytes) -> None:
        self._dev.ctrl_transfer(0x40, 0, wvalue, windex, data, _TIMEOUT_MS)

    def close(self) -> None:
        try:
            import usb.util  # type: ignore[import-untyped]

            usb.util.dispose_resources(self._dev)
        except Exception:  # pragma: no cover
            pass


class FakeTransport:
    """In-memory device for tests and running without the board.

    ``values`` maps a parameter name to its current values; ``busy`` makes the
    next N reads answer STATUS_RETRY first.
    """

    def __init__(self, values: dict[str, Sequence[float | int]] | None = None) -> None:
        self.values: dict[str, Sequence[float | int]] = dict(values or {})
        self.busy = 0
        self.status = STATUS_OK
        self.writes: list[tuple[str, tuple[float | int, ...] | str]] = []
        self._by_id = {(p.resid, p.cmdid): (n, p) for n, p in PARAMS.items()}

    def ctrl_in(self, wvalue: int, windex: int, length: int) -> bytes:
        if self.busy > 0:
            self.busy -= 1
            return bytes([STATUS_RETRY]) + bytes(length - 1)
        name, p = self._by_id[(windex, wvalue & 0x7F)]
        vals = self.values.get(name, [0] * p.count)
        return bytes([self.status]) + encode(p, vals)

    def ctrl_out(self, wvalue: int, windex: int, data: bytes) -> None:
        name, p = self._by_id[(windex, wvalue)]
        vals = decode(p, data)
        self.writes.append((name, vals))
        if p.access == "rw":
            self.values[name] = list(vals) if not isinstance(vals, str) else vals  # type: ignore[assignment]


# ── device ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VoiceDirection:
    """One DoA sample. ``azimuth_deg`` is in the array's own frame (0..360),
    None when no beam holds speech."""

    azimuth_deg: float | None
    speech: bool
    energy: float  # the auto-select beam's speech energy (>0 = speech)
    beam_energy: tuple[float, ...]  # beams 0, 1, free-running, auto-select


class Xvf3800:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    @classmethod
    def open_usb(cls, vid: int = VID, pid: int = PID) -> Xvf3800:
        return cls(UsbTransport(vid, pid))

    def close(self) -> None:
        self._t.close()

    def read(self, name: str) -> tuple[float | int, ...] | str:
        p = _param(name)
        if p.access == "wo":
            raise XvfError(f"{name} is write-only")
        for _ in range(_MAX_RETRIES):
            reply = self._t.ctrl_in(0x80 | p.cmdid, p.resid, reply_length(p))
            if not reply:
                raise XvfError(f"{name}: empty reply")
            status = reply[0]
            if status == STATUS_OK:
                return decode(p, reply[1:])
            if status != STATUS_RETRY:
                raise XvfError(f"{name}: status {status}")
            time.sleep(_RETRY_SLEEP_S)
        raise XvfError(f"{name}: device busy after {_MAX_RETRIES} retries")

    def write(self, name: str, values: Sequence[float | int] | str) -> None:
        p = _param(name)
        if p.access == "ro":
            raise XvfError(f"{name} is read-only")
        self._t.ctrl_out(p.cmdid, p.resid, encode(p, values))

    # convenience

    def version(self) -> str:
        v = self.read("VERSION")
        return ".".join(str(x) for x in v)

    def voice_direction(self) -> VoiceDirection:
        az = self.read("AUDIO_MGR_SELECTED_AZIMUTHS")
        en = tuple(float(x) for x in self.read("AEC_SPENERGY_VALUES"))
        a0 = float(az[0])  # type: ignore[index]
        speech = not math.isnan(a0)
        deg = (math.degrees(a0) % 360.0) if speech else None
        return VoiceDirection(
            azimuth_deg=deg, speech=speech, energy=en[3], beam_energy=en
        )

    def save_configuration(self) -> None:
        self.write("SAVE_CONFIGURATION", [1])


def _param(name: str) -> Param:
    try:
        return PARAMS[name]
    except KeyError:
        raise XvfError(f"unknown parameter {name}") from None


def to_robot_deg(array_deg: float, offset_deg: float = 0.0, sign: int = 1) -> float:
    """Array-frame azimuth -> robot frame (0 = forward, +ve = CCW from above,
    i.e. toward +Y). ``offset_deg`` / ``sign`` come from a bench calibration
    (a voice straight ahead, then from the left)."""
    return (offset_deg + sign * array_deg) % 360.0


def signed_deg(deg: float) -> float:
    """0..360 -> -180..180."""
    return (deg + 180.0) % 360.0 - 180.0
