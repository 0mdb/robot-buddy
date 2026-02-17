#!/usr/bin/env python3
"""Send audio diagnostic commands to esp32-face-display over CDC serial.

Protocol:
  type=0x25 (SET_CONFIG)
  payload = param_id:u8 + value:u32 (little-endian)
"""

from __future__ import annotations

import argparse
import struct
import time

try:
    import serial
except ImportError as exc:  # pragma: no cover - runtime environment dependent
    raise SystemExit(
        "pyserial is required. Install it with: pip install pyserial"
    ) from exc


FACE_CMD_SET_CONFIG = 0x25
CFG_AUDIO_TONE_MS = 0xA0
CFG_AUDIO_MIC_MS = 0xA1
CFG_AUDIO_REG_DUMP = 0xA2


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def cobs_encode(src: bytes) -> bytes:
    out = bytearray()
    code_pos = 0
    out.append(0)  # placeholder for first code byte
    code = 1
    for b in src:
        if b == 0:
            out[code_pos] = code
            code_pos = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_pos] = code
                code_pos = len(out)
                out.append(0)
                code = 1
    out[code_pos] = code
    return bytes(out)


def build_set_config(seq: int, param_id: int, value: int) -> bytes:
    payload = struct.pack("<BI", param_id & 0xFF, value & 0xFFFFFFFF)
    raw = bytes([FACE_CMD_SET_CONFIG, seq & 0xFF]) + payload
    raw += struct.pack("<H", crc16_ccitt(raw))
    return cobs_encode(raw) + b"\x00"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Face audio diagnostics sender")
    p.add_argument("--port", required=True, help="Serial device path")
    p.add_argument("--baud", type=int, default=115200, help="Serial baudrate")
    p.add_argument("--seq", type=int, default=0, help="Packet sequence number")

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tone-ms", type=int, help="Play 1kHz tone for this duration")
    g.add_argument("--mic-ms", type=int, help="Run mic probe for this duration")
    g.add_argument("--reg-dump", action="store_true", help="Dump ES8311 registers to firmware log")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.tone_ms is not None:
        param_id = CFG_AUDIO_TONE_MS
        value = max(1, args.tone_ms)
        label = f"tone {value}ms"
    elif args.mic_ms is not None:
        param_id = CFG_AUDIO_MIC_MS
        value = max(1, args.mic_ms)
        label = f"mic probe {value}ms"
    else:
        param_id = CFG_AUDIO_REG_DUMP
        value = 0
        label = "register dump"

    pkt = build_set_config(args.seq, param_id, value)
    print(f"sending {label} to {args.port} ({len(pkt)} bytes)")

    with serial.Serial(args.port, args.baud, timeout=0.2) as ser:
        ser.write(pkt)
        ser.flush()
        time.sleep(0.05)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
