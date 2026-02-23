#!/usr/bin/env python3
"""Diagnostic script for robot-buddy serial ports.

Run on the Pi to characterize USB serial behavior before/after firmware changes.
Reports: kernel driver, read/write timing, raw data hex dump.

Usage:
    python3 tools/serial_diag.py /dev/ttyACM0
    python3 tools/serial_diag.py /dev/robot_reflex
    python3 tools/serial_diag.py --all   # scan all ttyACM devices
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time


def find_driver(dev: str) -> str:
    """Report the kernel driver for a tty device."""
    # Resolve symlinks (e.g. /dev/robot_reflex -> /dev/ttyACM0)
    real = os.path.realpath(dev)
    basename = os.path.basename(real)

    # Try /sys/class/tty/<name>/device/driver
    driver_link = f"/sys/class/tty/{basename}/device/driver"
    if os.path.islink(driver_link):
        return os.path.basename(os.readlink(driver_link))

    return "(unknown)"


def find_usb_info(dev: str) -> dict:
    """Report USB device info (VID, PID, serial, product) from sysfs."""
    real = os.path.realpath(dev)
    basename = os.path.basename(real)

    # Walk up sysfs tree to find the USB device node
    sys_path = f"/sys/class/tty/{basename}/device"
    if not os.path.exists(sys_path):
        return {}

    # Walk up to find idVendor/idProduct
    path = os.path.realpath(sys_path)
    for _ in range(10):
        vid_path = os.path.join(path, "idVendor")
        if os.path.exists(vid_path):
            info = {}
            for attr in ("idVendor", "idProduct", "serial", "product", "manufacturer"):
                attr_path = os.path.join(path, attr)
                if os.path.exists(attr_path):
                    with open(attr_path) as f:
                        info[attr] = f.read().strip()
            return info
        path = os.path.dirname(path)

    return {}


def find_by_id_path(dev: str) -> str:
    """Find the /dev/serial/by-id/ symlink for a device."""
    real = os.path.realpath(dev)
    by_id_dir = "/dev/serial/by-id"
    if os.path.isdir(by_id_dir):
        for entry in os.listdir(by_id_dir):
            full = os.path.join(by_id_dir, entry)
            if os.path.realpath(full) == real:
                return full
    return "(none)"


def find_by_path(dev: str) -> str:
    """Find the /dev/serial/by-path/ symlink for a device."""
    real = os.path.realpath(dev)
    by_path_dir = "/dev/serial/by-path"
    if os.path.isdir(by_path_dir):
        for entry in os.listdir(by_path_dir):
            full = os.path.join(by_path_dir, entry)
            if os.path.realpath(full) == real:
                return full
    return "(none)"


def find_kernels_path(dev: str) -> str:
    """Find the KERNELS value for udev matching (physical USB port path)."""
    real = os.path.realpath(dev)
    basename = os.path.basename(real)

    sys_path = f"/sys/class/tty/{basename}/device"
    if not os.path.exists(sys_path):
        return "(unknown)"

    path = os.path.realpath(sys_path)
    for _ in range(10):
        vid_path = os.path.join(path, "idVendor")
        if os.path.exists(vid_path):
            return os.path.basename(path)
        path = os.path.dirname(path)

    return "(unknown)"


def test_device(dev: str, duration_s: float = 5.0) -> None:
    """Run diagnostics on a single serial device."""
    import serial

    real = os.path.realpath(dev)
    print(f"\n{'=' * 60}")
    print(f"Device:       {dev}")
    if dev != real:
        print(f"Resolves to:  {real}")
    print(f"Driver:       {find_driver(dev)}")
    print(f"by-id:        {find_by_id_path(dev)}")
    print(f"by-path:      {find_by_path(dev)}")
    print(f"KERNELS:      {find_kernels_path(dev)}")

    usb_info = find_usb_info(dev)
    if usb_info:
        print(
            f"USB VID:PID:  {usb_info.get('idVendor', '?')}:{usb_info.get('idProduct', '?')}"
        )
        print(f"USB Product:  {usb_info.get('product', '?')}")
        print(f"USB Manufact: {usb_info.get('manufacturer', '?')}")
        print(f"USB Serial:   {usb_info.get('serial', '?')}")
    print(f"{'=' * 60}")

    # Test open
    print("\n--- Open test ---")
    t0 = time.monotonic()
    try:
        ser = serial.Serial(real, 115200, timeout=0.05, write_timeout=0)
    except Exception as e:
        print(f"FAILED to open: {e}")
        return
    t1 = time.monotonic()
    print(f"Open took: {(t1 - t0) * 1000:.1f} ms")

    # Test write timing (non-blocking)
    print("\n--- Write test (write_timeout=0) ---")
    test_data = b"\x00"  # single COBS delimiter
    times = []
    for i in range(10):
        t0 = time.monotonic()
        try:
            ser.write(test_data)
        except Exception as e:
            print(f"  Write {i} FAILED: {e}")
            break
        t1 = time.monotonic()
        times.append((t1 - t0) * 1000)
    if times:
        print(
            f"  10 writes: min={min(times):.3f}ms  max={max(times):.3f}ms  avg={sum(times) / len(times):.3f}ms"
        )
        if max(times) > 5.0:
            print(
                f"  WARNING: max write time {max(times):.1f}ms > 5ms — writes may be blocking!"
            )
        else:
            print("  OK: writes are non-blocking")

    # Test write timing with write_timeout=0.1
    print("\n--- Write test (write_timeout=0.1) ---")
    ser.write_timeout = 0.1
    times = []
    for i in range(10):
        t0 = time.monotonic()
        try:
            ser.write(test_data)
        except Exception as e:
            print(f"  Write {i} FAILED: {e}")
            break
        t1 = time.monotonic()
        times.append((t1 - t0) * 1000)
    if times:
        print(
            f"  10 writes: min={min(times):.3f}ms  max={max(times):.3f}ms  avg={sum(times) / len(times):.3f}ms"
        )
        if max(times) > 50.0:
            print(
                f"  WARNING: max write time {max(times):.1f}ms > 50ms — writes blocking significantly!"
            )

    # Test read + hex dump
    print(f"\n--- Read test ({duration_s}s hex dump, timeout=0.05) ---")
    ser.timeout = 0.05
    ser.write_timeout = 0
    total_bytes = 0
    total_reads = 0
    empty_reads = 0
    start = time.monotonic()

    # Collect first N bytes for hex dump
    hex_buf = bytearray()
    hex_limit = 256

    while time.monotonic() - start < duration_s:
        t0 = time.monotonic()
        data = ser.read(256)
        t1 = time.monotonic()
        total_reads += 1

        if data:
            total_bytes += len(data)
            if len(hex_buf) < hex_limit:
                hex_buf.extend(data[: hex_limit - len(hex_buf)])
        else:
            empty_reads += 1

        # Check if read blocked longer than timeout
        read_ms = (t1 - t0) * 1000
        if read_ms > 100:
            print(f"  WARNING: read blocked for {read_ms:.1f}ms (expected ≤50ms)")

    elapsed = time.monotonic() - start
    print(f"  Duration:    {elapsed:.1f}s")
    print(f"  Total bytes: {total_bytes}")
    print(f"  Total reads: {total_reads} ({empty_reads} empty)")
    print(f"  Throughput:  {total_bytes / elapsed:.0f} bytes/s")

    if hex_buf:
        print(f"\n  First {len(hex_buf)} bytes (hex):")
        for offset in range(0, len(hex_buf), 16):
            chunk = hex_buf[offset : offset + 16]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print(f"    {offset:04x}: {hex_str:<48s} {ascii_str}")

        # Check for text in data (sign of console leaking into protocol)
        text_bytes = sum(1 for b in hex_buf if 32 <= b < 127)
        text_pct = text_bytes / len(hex_buf) * 100
        if text_pct > 50:
            print(
                f"\n  WARNING: {text_pct:.0f}% printable ASCII — console text may be leaking into protocol!"
            )
    else:
        print("  No data received!")

    ser.close()
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Robot Buddy serial port diagnostics")
    parser.add_argument(
        "device",
        nargs="?",
        default=None,
        help="Serial device path (e.g. /dev/ttyACM0, /dev/robot_reflex)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan all ttyACM devices",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Read test duration in seconds (default: 5)",
    )
    args = parser.parse_args()

    try:
        import serial  # noqa: F401
    except ImportError:
        print("ERROR: pyserial not installed. Run: pip install pyserial")
        sys.exit(1)

    if args.all:
        devices = sorted(glob.glob("/dev/ttyACM*"))
        if not devices:
            print("No /dev/ttyACM* devices found.")
            sys.exit(1)
        for dev in devices:
            test_device(dev, args.duration)
    elif args.device:
        if not os.path.exists(args.device):
            print(f"ERROR: {args.device} does not exist")
            sys.exit(1)
        test_device(args.device, args.duration)
    else:
        # Try default robot devices, fall back to scanning
        for default in ("/dev/robot_reflex", "/dev/robot_face"):
            if os.path.exists(default):
                test_device(default, args.duration)
        else:
            devices = sorted(glob.glob("/dev/ttyACM*"))
            if devices:
                print(
                    f"No default devices found. Scanning {len(devices)} ttyACM device(s)..."
                )
                for dev in devices:
                    test_device(dev, args.duration)
            else:
                print("No serial devices found. Is an MCU plugged in?")
                sys.exit(1)


if __name__ == "__main__":
    main()
