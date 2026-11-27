"""Drive the Nucleo `link` firmware with the real supervisor code (no carrier, no Pi).

    cargo run --release --bin link          # in firmware/nucleo-g431, leave it running (RTT log)
    python3 firmware/nucleo-g431/link_check.py [/dev/ttyACM0]   # from the repo root

Uses supervisor.io.serial_transport.SerialTransport + supervisor.devices.reflex_client.ReflexClient
unchanged: v1 telemetry, the v2 handshake, time sync, twist -> STATE speeds + seq echo, command
timeout, ESTOP, CLEAR_FAULTS. Prints PASS/FAIL per check; exit code 1 on any failure.
"""

from __future__ import annotations

import asyncio
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from supervisor.devices.protocol import (  # noqa: E402
    COMMON_TIME_SYNC_RESP,
    Fault,
    ParsedPacket,
    TelType,
    build_time_sync_req,
)
from supervisor.devices.reflex_client import ReflexClient  # noqa: E402
from supervisor.io.serial_transport import SerialTransport  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


async def main(port: str, v1_only: bool) -> int:
    transport = SerialTransport(port, label="reflex")
    client = ReflexClient(transport)
    states: list[float] = []
    client.on_telemetry(lambda t: states.append(time.monotonic()))
    sync: list[ParsedPacket] = []
    transport.on_packet(
        lambda p: sync.append(p) if p.pkt_type == COMMON_TIME_SYNC_RESP else None
    )
    # ReflexTelemetry drops the v2 STATE tail; keep the raw payload to check the seq echo.
    raw_state: list[bytes] = []
    transport.on_packet(
        lambda p: raw_state.append(p.payload) if p.pkt_type == TelType.STATE else None
    )

    await transport.start()
    for _ in range(50):
        if transport.connected:
            break
        await asyncio.sleep(0.1)
    if not transport.connected:
        check("open port", False, port)
        return 1

    # 1. v1 STATE at 20 Hz before any handshake.
    states.clear()
    await asyncio.sleep(1.0)
    check("STATE v1 ~20 Hz", 15 <= len(states) <= 25, f"{len(states)} in 1 s")

    # 2. v2 handshake. --v1 skips it: that is how the robot runs today, because main.py calls
    # negotiate_v2() before the port is open, and the ACK (sent in a v2 envelope by both ESP32s
    # and this port) is parsed as v1 by the supervisor anyway. See docs/TODO.md.
    if not v1_only:
        check("v2 handshake", await transport.negotiate_v2(timeout_s=0.5))

    # 3. Time sync round trip.
    ping = 0x1234
    t0 = time.monotonic()
    transport.write(
        build_time_sync_req(1, ping, protocol_version=transport.protocol_version)
    )
    for _ in range(20):
        if sync:
            break
        await asyncio.sleep(0.01)
    rtt_ms = (time.monotonic() - t0) * 1000
    ok = bool(sync) and struct.unpack_from("<I", sync[0].payload)[0] == ping
    t_mcu = struct.unpack_from("<Q", sync[0].payload, 4)[0] if sync else 0
    check("time sync", ok, f"rtt {rtt_ms:.1f} ms, mcu t {t_mcu} us")

    # 4. Twist -> rate-limited speeds and seq echo.
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
    # Commands go out in v1 envelopes (u8 seq), so the MCU echoes the low byte. v2 only.
    if not v1_only:
        echo = (
            struct.unpack_from("<I", raw_state[-1], 17)[0]
            if len(raw_state[-1]) >= 25
            else -1
        )
        check(
            "seq echo (v2 cmd_seq_last_applied)",
            echo == client.last_cmd_seq & 0xFF,
            f"echo {echo}, last tx seq {client.last_cmd_seq}",
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

    # 6. ESTOP latches; CLEAR_FAULTS clears.
    client.send_estop()
    await asyncio.sleep(0.2)
    check("ESTOP latched", client.telemetry.has_fault(Fault.ESTOP))
    client.send_clear_faults()
    await asyncio.sleep(0.2)
    # CMD_TIMEOUT re-latches at once while no command arrives (as safety.cpp does); ESTOP must go.
    flags = client.telemetry.fault_flags
    check(
        "CLEAR_FAULTS",
        not flags & Fault.ESTOP and flags & ~Fault.CMD_TIMEOUT == 0,
        f"flags {flags:#06x}",
    )

    await transport.stop()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(asyncio.run(main(args[0] if args else "/dev/ttyACM0", "--v1" in sys.argv)))
