"""On-demand protocol packet capture for commissioning/debugging.

Only captures when at least one WS client is subscribed — zero overhead
in production.  Follows the WebSocketLogBroadcaster per-client queue pattern.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger(__name__)

# -- Packet type name lookup tables (mirrors protocol.py enums) ---------------

_REFLEX_CMD_NAMES: dict[int, str] = {
    0x10: "SET_TWIST",
    0x11: "STOP",
    0x12: "ESTOP",
    0x13: "SET_LIMITS",
    0x14: "CLEAR_FAULTS",
    0x15: "SET_CONFIG",
}

_REFLEX_TEL_NAMES: dict[int, str] = {
    0x80: "STATE",
}

_FACE_CMD_NAMES: dict[int, str] = {
    0x20: "SET_STATE",
    0x21: "GESTURE",
    0x22: "SET_SYSTEM",
    0x23: "SET_TALKING",
    0x24: "SET_FLAGS",
}

_FACE_TEL_NAMES: dict[int, str] = {
    0x90: "FACE_STATUS",
    0x91: "TOUCH_EVENT",
    0x92: "BUTTON_EVENT",
    0x93: "HEARTBEAT",
}

ALL_TYPE_NAMES: dict[int, str] = {
    **_REFLEX_CMD_NAMES,
    **_REFLEX_TEL_NAMES,
    **_FACE_CMD_NAMES,
    **_FACE_TEL_NAMES,
}


@dataclass(slots=True)
class CapturedPacket:
    ts_mono_ms: float
    direction: str  # "TX" or "RX"
    device: str  # "reflex" or "face"
    pkt_type: int
    type_name: str
    seq: int
    fields: dict[str, Any]
    raw_hex: str
    size: int
    t_src_us: int = 0  # v2: MCU source timestamp (µs since boot)


class ProtocolCapture:
    """Manages per-client queues for the /ws/protocol endpoint."""

    def __init__(self, maxsize: int = 512) -> None:
        self._clients: set[asyncio.Queue[str]] = set()
        self._maxsize = maxsize

    @property
    def active(self) -> bool:
        return len(self._clients) > 0

    def add_client(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._maxsize)
        self._clients.add(q)
        log.info("protocol capture: client connected (%d total)", len(self._clients))
        return q

    def remove_client(self, q: asyncio.Queue[str]) -> None:
        self._clients.discard(q)
        log.info("protocol capture: client disconnected (%d total)", len(self._clients))

    def capture_rx(
        self,
        device: str,
        pkt_type: int,
        seq: int,
        payload: bytes,
        t_src_us: int = 0,
    ) -> None:
        if not self._clients:
            return
        self._emit(
            direction="RX",
            device=device,
            pkt_type=pkt_type,
            seq=seq,
            payload=payload,
            t_src_us=t_src_us,
        )

    def capture_tx(
        self,
        device: str,
        pkt_type: int,
        seq: int,
        payload: bytes,
    ) -> None:
        if not self._clients:
            return
        self._emit(
            direction="TX", device=device, pkt_type=pkt_type, seq=seq, payload=payload
        )

    def _emit(
        self,
        *,
        direction: str,
        device: str,
        pkt_type: int,
        seq: int,
        payload: bytes,
        t_src_us: int = 0,
    ) -> None:
        type_name = ALL_TYPE_NAMES.get(pkt_type, f"0x{pkt_type:02X}")
        fields = _decode_fields(pkt_type, payload)
        raw_hex = bytes([pkt_type, seq & 0xFF]).hex() + payload.hex()

        pkt = CapturedPacket(
            ts_mono_ms=round(time.monotonic() * 1000.0, 1),
            direction=direction,
            device=device,
            pkt_type=pkt_type,
            type_name=type_name,
            seq=seq,
            fields=fields,
            raw_hex=raw_hex,
            size=len(payload) + 2,  # type + seq + payload
            t_src_us=t_src_us,
        )

        entry = json.dumps(asdict(pkt))
        for q in list(self._clients):
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(entry)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


def _decode_fields(pkt_type: int, payload: bytes) -> dict[str, Any]:
    """Best-effort payload decode into human-readable fields."""
    try:
        # -- Reflex commands -----------------------------------------------
        if pkt_type == 0x10 and len(payload) >= 4:  # SET_TWIST
            v, w = struct.unpack_from("<hh", payload)
            return {"v_mm_s": v, "w_mrad_s": w}
        if pkt_type == 0x11 and len(payload) >= 1:  # STOP
            return {"reason": payload[0]}
        if pkt_type == 0x12:  # ESTOP
            return {}
        if pkt_type == 0x14 and len(payload) >= 2:  # CLEAR_FAULTS
            (mask,) = struct.unpack_from("<H", payload)
            return {"mask": f"0x{mask:04X}"}
        if pkt_type == 0x15 and len(payload) >= 5:  # SET_CONFIG
            param_id = payload[0]
            value_hex = payload[1:5].hex()
            return {"param_id": f"0x{param_id:02X}", "value_hex": value_hex}

        # -- Reflex telemetry ----------------------------------------------
        if pkt_type == 0x80 and len(payload) >= 19:  # STATE
            sl, sr, gz, ax, ay, az, bat, faults, rng, rs = struct.unpack_from(
                "<hhhhhhHHHB", payload
            )
            return {
                "speed_l": sl,
                "speed_r": sr,
                "gyro_z": gz,
                "accel_x": ax,
                "accel_y": ay,
                "accel_z": az,
                "battery_mv": bat,
                "faults": f"0x{faults:04X}",
                "range_mm": rng,
                "range_status": rs,
            }

        # -- Face commands -------------------------------------------------
        if pkt_type == 0x20 and len(payload) >= 5:  # SET_STATE
            mood, intensity, gx, gy, bright = struct.unpack_from("<BBbbB", payload)
            return {
                "mood": mood,
                "intensity": intensity,
                "gaze_x": gx,
                "gaze_y": gy,
                "brightness": bright,
            }
        if pkt_type == 0x21 and len(payload) >= 3:  # GESTURE
            gid, dur = struct.unpack_from("<BH", payload)
            return {"gesture_id": gid, "duration_ms": dur}
        if pkt_type == 0x22 and len(payload) >= 3:  # SET_SYSTEM
            mode, phase, param = struct.unpack_from("<BBB", payload)
            return {"mode": mode, "phase": phase, "param": param}
        if pkt_type == 0x23 and len(payload) >= 2:  # SET_TALKING
            talking, energy = struct.unpack_from("<BB", payload)
            return {"talking": bool(talking), "energy": energy}
        if pkt_type == 0x24 and len(payload) >= 1:  # SET_FLAGS
            return {"flags": f"0x{payload[0]:02X}"}

        # -- Face telemetry ------------------------------------------------
        if pkt_type == 0x90 and len(payload) >= 4:  # FACE_STATUS
            mood, gesture, sysmode, flags = struct.unpack_from("<BBBB", payload)
            return {
                "mood": mood,
                "gesture": gesture,
                "system_mode": sysmode,
                "flags": f"0x{flags:02X}",
            }
        if pkt_type == 0x91 and len(payload) >= 5:  # TOUCH_EVENT
            evt, x, y = struct.unpack_from("<BHH", payload)
            return {"event_type": evt, "x": x, "y": y}
        if pkt_type == 0x92 and len(payload) >= 4:  # BUTTON_EVENT
            bid, etype, state, _ = struct.unpack_from("<BBBB", payload)
            return {"button_id": bid, "event_type": etype, "state": state}
        if pkt_type == 0x93 and len(payload) >= 16:  # HEARTBEAT
            up, stx, ttx, btx = struct.unpack_from("<IIII", payload)
            return {
                "uptime_ms": up,
                "status_tx": stx,
                "touch_tx": ttx,
                "button_tx": btx,
            }
    except (struct.error, IndexError):
        pass

    return {"raw": payload.hex()} if payload else {}
