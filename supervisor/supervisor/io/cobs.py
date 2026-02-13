"""COBS (Consistent Overhead Byte Stuffing) encode/decode.

Matches the framing used by esp32-reflex/main/protocol.cpp.
Wire format: [COBS-encoded payload] [0x00 delimiter]
"""

from __future__ import annotations


def encode(data: bytes) -> bytes:
    """COBS-encode data. Does NOT append the 0x00 delimiter."""
    out = bytearray()
    code_idx = 0
    out.append(0)  # placeholder for first code byte
    code = 1

    for b in data:
        if b == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)  # placeholder for next code byte
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1

    out[code_idx] = code
    return bytes(out)


def decode(data: bytes) -> bytes:
    """COBS-decode data. Input must NOT include the 0x00 delimiter."""
    if not data:
        return b""

    out = bytearray()
    idx = 0

    while idx < len(data):
        code = data[idx]
        if code == 0:
            raise ValueError("unexpected zero byte in COBS stream")
        idx += 1

        for _ in range(code - 1):
            if idx >= len(data):
                raise ValueError("COBS truncated")
            out.append(data[idx])
            idx += 1

        if code < 0xFF and idx < len(data):
            out.append(0)

    return bytes(out)
