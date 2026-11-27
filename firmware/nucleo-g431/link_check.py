"""Drive the Nucleo `link` firmware with the real supervisor code (no carrier, no Pi).

    cargo run --release --bin link          # in firmware/nucleo-g431, leave it running (RTT log)
    python3 firmware/nucleo-g431/link_check.py [/dev/ttyACM0]   # from the repo root

Uses supervisor.io.serial_transport.SerialTransport + supervisor.devices.reflex_client.ReflexClient
unchanged. Protocol v2 only (PROTOCOL.md 3.2, amended 2026-11-27): the transport negotiates by
itself after opening; checks time sync, twist -> STATE speeds + applied-seq echo, command
timeout, ESTOP, CLEAR_FAULTS, and recovery from a forced envelope desync. Prints PASS/FAIL per
check; exit code 1 on any failure.
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

    t_open = time.monotonic()
    await transport.start()
    if not await wait_for(lambda: transport.connected, 5.0):
        check("open port", False, port)
        return 1

    # 1. The transport negotiates v2 by itself once the port is open.
    ok = await wait_for(lambda: transport.protocol_version == 2, 4.0)
    check(
        "v2 negotiated after open", ok, f"{(time.monotonic() - t_open) * 1000:.0f} ms"
    )

    # 2. STATE at 20 Hz, all with the exact v2 length.
    states.clear()
    bad0 = client.debug_snapshot()["rx_bad_payload_packets"]
    await asyncio.sleep(1.0)
    bad = client.debug_snapshot()["rx_bad_payload_packets"] - bad0
    check(
        "STATE v2 ~20 Hz",
        15 <= len(states) <= 25 and bad == 0,
        f"{len(states)} in 1 s, {bad} bad",
    )

    # 3. Time sync round trip.
    ping = 0x1234
    t0 = time.monotonic()
    transport.write(build_time_sync_req(1, ping, protocol_version=2))
    await wait_for(lambda: bool(sync), 0.2)
    rtt_ms = (time.monotonic() - t0) * 1000
    ok = bool(sync) and struct.unpack_from("<I", sync[0].payload)[0] == ping
    t_mcu = struct.unpack_from("<Q", sync[0].payload, 4)[0] if sync else 0
    check("time sync", ok, f"rtt {rtt_ms:.1f} ms, mcu t {t_mcu} us")

    # 4. Twist -> rate-limited speeds and the applied-seq echo (full u32 under v2).
    client.send_clear_faults()
    for _ in range(15):
        client.send_twist(200, 0)
        await asyncio.sleep(0.1)
    t = client.telemetry
    check(
        "twist -> speeds",
        abs(t.speed_l_mm_s - 200) <= 2 and abs(t.speed_r_mm_s - 200) <= 2,
        f"L {t.speed_l_mm_s} R {t.speed_r_mm_s}",
    )
    check(
        "no faults while commanded", t.fault_flags == 0, f"flags {t.fault_flags:#06x}"
    )
    check(
        "seq echo (cmd_seq_last_applied)",
        t.cmd_seq_last_applied == client.last_cmd_seq,
        f"echo {t.cmd_seq_last_applied}, last tx seq {client.last_cmd_seq}",
    )

    # 5. Stop commanding: CMD_TIMEOUT after 400 ms, speeds ramp to 0.
    await asyncio.sleep(1.2)
    t = client.telemetry
    check(
        "command timeout fault",
        t.has_fault(Fault.CMD_TIMEOUT),
        f"flags {t.fault_flags:#06x}",
    )
    check(
        "stopped after timeout",
        t.speed_l_mm_s == 0 and t.speed_r_mm_s == 0,
        f"L {t.speed_l_mm_s}",
    )

    # 6. ESTOP latches; CLEAR_FAULTS clears it (CMD_TIMEOUT re-latches at once while no
    # command arrives, as safety.cpp does).
    client.send_estop()
    await asyncio.sleep(0.2)
    check("ESTOP latched", client.telemetry.has_fault(Fault.ESTOP))
    client.send_clear_faults()
    await asyncio.sleep(0.2)
    flags = client.telemetry.fault_flags
    check(
        "CLEAR_FAULTS",
        not flags & Fault.ESTOP and flags & ~Fault.CMD_TIMEOUT == 0,
        f"flags {flags:#06x}",
    )

    # 7. Forced desync (as after a lost ACK): wrong STATE lengths -> re-handshake -> v2.
    n0 = transport.negotiations
    transport.protocol_version = 1
    ok = await wait_for(
        lambda: transport.negotiations > n0 and transport.protocol_version == 2, 3.0
    )
    check("desync recovery", ok, f"negotiations {n0} -> {transport.negotiations}")

    await transport.stop()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0")))
