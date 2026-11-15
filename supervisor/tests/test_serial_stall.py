"""SerialTransport link-health checks for links whose port never disappears.

On the face's GPIO UART link a face reboot or a wedged face doesn't remove the
port, so the transport must notice from the bytes: the ESP32 ROM reset banner,
and no valid frame (not merely no bytes) within the stall timeout.
"""

from __future__ import annotations

import time

from supervisor.devices.protocol import build_packet
from supervisor.io import serial_transport as st


def _connected_transport(age_ms: float) -> st.SerialTransport:
    """A transport that 'connected' age_ms ago, with no frames since."""
    t = st.SerialTransport("/dev/null", label="face")
    t._connected = True
    t._connect_mono = time.monotonic() - age_ms / 1000.0
    t._last_rx_mono_ms = t._connect_mono * 1000.0
    t._last_good_mono_ms = t._connect_mono * 1000.0
    return t


STALE_MS = st._RX_STALL_TIMEOUT_MS + 500.0


def test_quiet_link_past_timeout_disconnects() -> None:
    t = _connected_transport(STALE_MS)
    t._check_rx_stall()
    assert not t.connected
    assert t._disconnect_count == 1
    assert t._last_error.startswith("rx stalled")


def test_garbage_flowing_still_disconnects() -> None:
    """Bytes keep arriving but none parse (noise, wrong baud): not a healthy link."""
    t = _connected_transport(STALE_MS)
    t._feed(b"\x55\xaa\x13\x37\x00")  # one bad-CRC frame
    assert t._frames_bad == 1 and t._frames_ok == 0
    t._check_rx_stall()
    assert not t.connected
    assert t._last_error.startswith("no valid frame")


def test_valid_frame_keeps_link_up() -> None:
    t = _connected_transport(STALE_MS)
    t._feed(build_packet(0x86, 1, b"\x00" * 12))
    assert t._frames_ok == 1
    t._check_rx_stall()
    assert t.connected
    assert t._disconnect_count == 0


def test_rom_banner_is_a_reset() -> None:
    t = _connected_transport(1000.0)
    t._feed(b"\r\nESP-ROM:esp32s3-20210327\r\nBuild:Mar 27 2021\r\n")
    assert not t.connected
    assert t._mcu_resets_seen == 1
    assert t._disconnect_count == 1


def test_rom_banner_split_across_reads() -> None:
    t = _connected_transport(1000.0)
    t._feed(b"junk ESP-R")
    assert t.connected
    t._feed(b"OM:esp32s3")
    assert not t.connected
    assert t._mcu_resets_seen == 1


def test_fresh_connect_is_not_a_stall() -> None:
    t = _connected_transport(100.0)
    t._check_rx_stall()
    assert t.connected
