"""Fast tier: Buddy's real supervisor tick, in process, on a virtual clock.

Vantage's SIM-AUTONOMY.md, proposal 3. One Python object holds everything one full-tier sim run
spreads over three processes and a PTY:

    MuJoCo house + Buddy        ~/vantage/sim (drive.make)            the world
    reflex firmware model       ~/vantage/sim/reflex_emu.Reflex        firmware behaviour
         ⇅ COBS bytes, in memory (no PTY), both sides' real encoders and decoders
    ReflexClient → TickLoop._tick()   this repo's supervisor, imported, never copied

Nothing here re-implements the supervisor. Time is virtual: physics at the model timestep, the
firmware's tasks at their own rates, and a supervisor tick every 20 ms, all run to completion as
fast as the CPU allows. There are no sleeps, sockets, or workers.

Clocks. The tick takes its time from `robot.tick_mono_ms`, which this tier sets. One module on
the tick path reads the wall clock itself: `behavior_engine` (the teleop TTL). Its `time` is
pointed at the virtual clock here (`_VirtualTime`), so the 0.5 s TTL lasts 0.5 virtual seconds. That is a
harness seam, not a robot change. Changing how the TTL reads its clock on hardware, for the sake of
a simulator, is the wrong trade. `state.vision_age_ms` also reads the wall clock and is inert while
`clear_confidence` is -1.

What is *not* here, by design: workers (vision, planner, personality, audio), the face, HTTP.
The vision worker reports no camera in the full tier too, so `clear_confidence` stays -1 in both
tiers alike. The full tier (`just sim buddy` in Vantage) remains the proof.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# The supervisor package is robot-buddy's `supervisor/` directory and is imported from the repo
# root, exactly as `python -m supervisor` runs it on the robot.
REPO = Path(__file__).resolve().parents[2]
SIM_DIR = Path(os.environ.get("VANTAGE_SIM", Path.home() / "vantage" / "sim"))
for _p in (REPO, SIM_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import drive  # noqa: E402  (Vantage sim)
import reflex_emu  # noqa: E402
import reflex_fw  # noqa: E402

from supervisor.core import behavior_engine as _behavior_engine  # noqa: E402
from supervisor.core.skill_executor import SkillExecutor  # noqa: E402
from supervisor.core.tick_loop import TickLoop  # noqa: E402
from supervisor.devices.protocol import ParsedPacket, parse_frame  # noqa: E402
from supervisor.devices.reflex_client import ReflexClient  # noqa: E402

TICK_US = 20_000  # supervisor, 50 Hz (tick_loop.TICK_HZ)
# Firmware task periods, as reflex_emu.run schedules them (and the firmware does).
CTRL_US, SAFETY_US, RANGE_US, TEL_US = 10_000, 20_000, 50_000, 50_000
T0_US = 10_000_000  # start the virtual clock off zero: nothing should mistake it for "unset"


class _Pipe:
    """The serial line, in memory. `sup` is what ReflexClient sees (SerialTransport's surface);
    `emu` is what reflex_emu.Reflex sees (its Link protocol)."""

    def __init__(self) -> None:
        self._to_emu = bytearray()
        self._handlers: list[Callable[[ParsedPacket], None]] = []
        self.bad_frames = 0
        pipe = self

        class Sup:
            connected = True
            protocol_version = (
                1  # the real link never leaves v1 (Vantage SIM.md finding 4)
            )

            def on_packet(self, cb: Callable[[ParsedPacket], None]) -> None:
                pipe._handlers.append(cb)

            def write(self, data: bytes) -> bool:
                pipe._to_emu += data
                return True

            def debug_snapshot(self) -> dict:
                return {"fast_tier": True}

        class Emu:
            def frames(self) -> list[bytes]:
                buf = pipe._to_emu
                out = []
                while (i := buf.find(0)) >= 0:
                    out.append(bytes(buf[:i]))
                    del buf[: i + 1]
                return out

            def write(self, data: bytes) -> None:
                for frame in data.split(b"\x00"):
                    if not frame:
                        continue
                    try:
                        pkt = parse_frame(frame, protocol_version=Sup.protocol_version)
                    except ValueError:
                        pipe.bad_frames += 1
                        continue
                    # Wall-clock receive stamp: the supervisor's reflex-staleness check compares
                    # against time.monotonic(), and in this tier telemetry is always fresh.
                    pkt.t_pi_rx_ns = time.monotonic_ns()
                    for h in pipe._handlers:
                        h(pkt)

        self.sup = Sup()
        self.emu = Emu()


class _VirtualTime:
    """Stands in for the `time` module inside behavior_engine. Every FastBuddy sets `now_s`
    before it ticks, so several instances can share one process (they never interleave a tick)."""

    now_s = 0.0

    def monotonic(self) -> float:
        return self.now_s


_VTIME = _VirtualTime()
_behavior_engine.time = _VTIME  # type: ignore[assignment]


class _NoWorkers:
    def __getattr__(self, name: str) -> Any:
        async def _none(*a: Any, **k: Any) -> bool:
            return False

        return _none


class FastBuddy:
    """One simulated Buddy. `step(seconds)` advances virtual time; observe through `.tick.robot`
    (what the supervisor believes) and `.b` (MuJoCo truth)."""

    def __init__(
        self,
        room: str,
        yaw_deg: float = 0.0,
        *,
        open_doors: frozenset[str] = frozenset(),
        skill_params: dict[str, Any] | None = None,
        on_tick: Callable[[FastBuddy], None] | None = None,
    ) -> None:
        with contextlib.redirect_stdout(
            io.StringIO()
        ):  # drive.make prints the world summary
            self.b = drive.make(room, yaw_deg, open_doors)
        self.room, self.yaw_deg = room, yaw_deg
        self.vt_us = T0_US
        self.pipe = _Pipe()
        self.emu = reflex_emu.Reflex(
            self.b,
            reflex_fw.load(),
            self.pipe.emu,
            clock=lambda: self.vt_us,
            quiet=True,
        )
        self.client = ReflexClient(self.pipe.sup)  # type: ignore[arg-type]
        self.tick = TickLoop(reflex=self.client, face=None, workers=_NoWorkers())  # type: ignore[arg-type]
        if skill_params:
            # TickLoop builds SkillExecutor with defaults; the tunables are not in the param
            # registry yet (SIM-AUTONOMY.md stage "tune").
            self.tick._skill = SkillExecutor(**skill_params)
            self.tick._behavior._skill = self.tick._skill
        self.on_tick = on_tick
        self._loop = asyncio.new_event_loop()
        self._dt_us = int(round(self.b.model.opt.timestep * 1e6))
        self._next = {
            "ctrl": self.vt_us,
            "safety": self.vt_us,
            "range": self.vt_us,
            "tel": self.vt_us,
            "tick": self.vt_us,
        }
        self.ticks = 0

    # ---- time ------------------------------------------------------------------------------

    @property
    def t_s(self) -> float:
        return (self.vt_us - T0_US) / 1e6

    def step(self, seconds: float) -> None:
        end = self.vt_us + int(seconds * 1e6)
        n, emu = self._next, self.emu
        while self.vt_us < end:
            now = self.vt_us
            emu.service_rx()
            if now >= n["ctrl"]:
                emu.control(now)
                n["ctrl"] += CTRL_US
            if now >= n["safety"]:
                emu.safety(now)
                n["safety"] += SAFETY_US
            if now >= n["range"]:
                emu.ranging()
                n["range"] += RANGE_US
            if now >= n["tel"]:
                emu.telemetry(now)
                n["tel"] += TEL_US
            if now >= n["tick"]:
                self._supervisor_tick(now)
                n["tick"] += TICK_US
            self.b.physics_step()
            self.vt_us += self._dt_us

    def _supervisor_tick(self, now_us: int) -> None:
        _VTIME.now_s = now_us / 1e6
        r = self.tick.robot
        prev = r.tick_mono_ms
        r.tick_mono_ms = now_us / 1000.0
        r.tick_dt_ms = (r.tick_mono_ms - prev) if prev else TICK_US / 1000.0
        self._loop.run_until_complete(self.tick._tick())
        self.ticks += 1
        if self.on_tick is not None:
            self.on_tick(self)

    def run_until(self, pred: Callable[[FastBuddy], bool], timeout_s: float) -> bool:
        end = self.t_s + timeout_s
        while self.t_s < end:
            self.step(TICK_US / 1e6)
            if pred(self):
                return True
        return False

    # ---- operator actions (the same calls the HTTP API and the Vantage adapter make) -------

    def request_mode(self, mode: str) -> tuple[bool, str]:
        return self.tick.request_mode(mode)

    def set_teleop_twist(self, v_mm_s: int, w_mrad_s: int) -> None:
        _VTIME.now_s = self.vt_us / 1e6
        self.tick.set_teleop_twist(v_mm_s, w_mrad_s)

    def estop(self) -> bool:
        return self.tick.estop()

    @property
    def mode(self) -> str:
        return self.tick.robot.mode.value

    def close(self) -> None:
        self._loop.close()
