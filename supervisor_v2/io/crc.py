"""CRC16-CCITT matching esp32-reflex/main/protocol.cpp.

Polynomial: 0x1021, initial value: 0xFFFF.
"""

from __future__ import annotations


def crc16(data: bytes) -> int:
    """Compute CRC16-CCITT over data, returning a 16-bit integer."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
