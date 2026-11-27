"""Bench check of the reflex-g431 firmware on a bare NUCLEO-G431RB (no motors, IMU or sonar),
driven by the real supervisor code (SerialTransport + ReflexClient, protocol v2).

    cargo run --release --features no-imu-fault     # in firmware/reflex-g431, leave it running
    python3 firmware/reflex-g431/bench_check.py [/dev/ttyACM0]   # from the repo root

With nothing attached, the expected behaviour is the safety logic reacting to absent hardware:
a twist with no encoder motion must end in STALL and a hard stop; ESTOP latches; CLEAR_FAULTS
recovers; no command for 400 ms raises CMD_TIMEOUT. Prints PASS/FAIL; exit 1 on any failure.
"""

from __future__ import annotations

import asyncio
import struct
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from supervisor.devices.protocol import (  # noqa: E402
    COMMON_TIME_SYNC_RESP,
    Fault,
    ParsedPacket,
    RangeStatus,
    build_time_sync_req,
)
from supervisor.devices.reflex_client import ReflexClient  # noqa: E402
from supervisor.io.serial_transport import SerialTransport  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


async def wait_for(cond: Callable[[], bool], timeout_s: float) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return cond()


async def main(port: str) -> int:
    transport = SerialTransport(port, label="reflex")
    client = ReflexClient(transport)
    states: list[float] = []
    client.on_telemetry(lambda t: states.append(time.monotonic()))
    sync: list[ParsedPacket] = []
    transport.on_packet(
        lambda p: sync.append(p) if p.pkt_type == COMMON_TIME_SYNC_RESP else None
    )
    await transport.start()
    if not await wait_for(lambda: transport.connected, 5.0):
        check("open port", False, port)
        return 1

    check("v2 negotiated", await wait_for(lambda: transport.protocol_version == 2, 4.0))
    states.clear()
    await asyncio.sleep(1.0)
    t = client.telemetry
    check("STATE ~20 Hz", 15 <= len(states) <= 25, f"{len(states)} in 1 s")
    check(
        "no faults at boot (no-imu-fault build)",
        t.fault_flags == 0,
        f"flags {t.fault_flags:#06x}",
    )
    check(
        "front sonar absent -> TIMEOUT",
        t.range_status == RangeStatus.TIMEOUT,
        f"status {t.range_status} range {t.range_mm}",
    )
    check("accel 0 without IMU", (t.accel_x_mg, t.accel_z_mg) == (0, 0))

    transport.write(build_time_sync_req(1, 0x55, protocol_version=2))
    await wait_for(lambda: bool(sync), 0.3)
    ok = bool(sync) and struct.unpack_from("<I", sync[0].payload)[0] == 0x55
    check("time sync", ok)

    # Twist with no wheels: targets ramp, encoders read 0 -> STALL after stall_thresh_ms.
    t0 = time.monotonic()
    stalled_at = None
    while time.monotonic() - t0 < 2.0:
        client.send_twist(200, 0)
        await asyncio.sleep(0.05)
        if client.telemetry.has_fault(Fault.STALL):
            stalled_at = time.monotonic() - t0
            break
    check(
        "twist without wheels -> STALL",
        stalled_at is not None and 0.5 <= stalled_at <= 1.2,
        f"after {stalled_at if stalled_at is None else round(stalled_at, 2)} s",
    )
    t = client.telemetry
    check(
        "seq echo",
        t.cmd_seq_last_applied == client.last_cmd_seq,
        f"{t.cmd_seq_last_applied} vs {client.last_cmd_seq}",
    )
    check("speeds 0 (no encoders)", (t.speed_l_mm_s, t.speed_r_mm_s) == (0, 0))

    # Keep commanding zero so CMD_TIMEOUT stays off; clear STALL.
    client.send_stop()
    client.send_clear_faults()
    await asyncio.sleep(0.2)
    client.send_stop()
    await asyncio.sleep(0.1)
    check(
        "CLEAR_FAULTS recovers",
        client.telemetry.fault_flags == 0,
        f"flags {client.telemetry.fault_flags:#06x}",
    )

    client.send_estop()
    await asyncio.sleep(0.2)
    check("ESTOP latched", client.telemetry.has_fault(Fault.ESTOP))
    client.send_stop()
    client.send_clear_faults()
    await asyncio.sleep(0.1)
    check("ESTOP cleared", not client.telemetry.has_fault(Fault.ESTOP))

    await asyncio.sleep(0.8)  # no commands
    check("command timeout", client.telemetry.has_fault(Fault.CMD_TIMEOUT))

    await transport.stop()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0")))
