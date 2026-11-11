"""Buddy's Vantage adapter — maps this robot onto the wire.

Everything vehicle-specific about serving Buddy to a Vantage client lives here. The bridge
(`~/vantage/supervisor/bridge.py`) owns sockets, framing and cadence and knows nothing about
`RobotState`, faces or voices. Scout has its own adapter; the two share the bridge and the wire,
and the difference between the robots costs the client nothing.

Buddy differs from Scout in ways this file absorbs:

* **Measured wheel speeds exist.** The reflex MCU reports per-wheel speed, so the ghost reticle
  compares real commanded and measured track speeds — the per-wheel command is split from the
  capped twist exactly as the MCU does it (`control.cpp`), using the live `reflex.wheelbase_mm`.
* **Caps are runtime-tunable.** `reflex.max_v_mm_s` / `reflex.max_w_mrad_s` live in the param
  registry and are pushed to the MCU, so axes map against the *live* values, never a copy.
* **Governor reasons are strings.** `apply_safety` records `SpeedCap(scale, "range=280mm<300")`
  and so on; `_limit_from_caps` maps the prefixes onto the fleet-wide enum. Tests drive the real
  `apply_safety` for every gate, so a reworded reason fails a test instead of silently showing
  no reason on the HUD.

Honest gaps — the alternative is a HUD that looks confident and is wrong:

* **No attitude.** Only accelerometer tilt exists, with unverified axis signs; a level horizon
  known to be unmeasured beats a tilted one guessed. Identity quaternion until bench-verified.
* **Pack voltage only from the UPS monitor.** `PowerState.voltage_mv` is the pack only when the
  source is `battery` / `ac_charging`; under the PMIC-only monitor it is a Pi 3V3 rail. Anything
  else is sent as `Sentinel.NO_READING_U16`, and an unknown SoC as `Sentinel.SOC_UNKNOWN`.
* **No per-cell sense** (the cells are inside the UPS HAT) and **no temperature sensor**. Cell
  is the sentinel, and `temp_max_c` is `Sentinel.NO_READING_I8` (added 2026-11-11, with
  `NO_READING_I16` for current off the pack).

Control goes to `TickLoop.set_teleop_twist`, never to an MCU, so every gate in
`core/safety.py` still applies. See `~/vantage/docs/CONTROL.md`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import vantage_frame as vf
import vantage_wire as w
from bridge import axes_to_twist

from supervisor.core.state import MOTION_MODES, Mode, SpeedCap
from supervisor.devices.protocol import Fault

if TYPE_CHECKING:
    from supervisor.core.tick_loop import TickLoop

log = logging.getLogger(__name__)

# Wire value per mode: declaration order, exactly as tools/emit_manifest.py enumerates it.
_MODE_VALUES = {m: i for i, m in enumerate(Mode)}
_MODES_BY_VALUE = list(Mode)

# E-STOP arrives level-encoded at up to 100 Hz; the MCU latch makes repeats harmless, but there
# is no reason to put 100 commands/s on the USB link. Same refire as Scout.
ESTOP_REFIRE_S = 0.05

# Reflex faults -> fleet-wide warn bits. Faults with no wire equivalent are simply not mapped.
_FAULT_TO_WARN = [
    (Fault.ESTOP, w.Warn.FAILSAFE_ACTIVE),
    (Fault.BROWNOUT, w.Warn.BATT_CRITICAL),
    (Fault.TILT, w.Warn.ATTITUDE_LIMIT),
    (Fault.STALL, w.Warn.OVERCURRENT),
]

# SpeedCap.reason prefix -> wire enum. Order matters only for "range_stale=" vs "range=".
_REASON_PREFIX = [
    ("mode=", w.Limit.MODE_GATE),
    ("fault=", w.Limit.FAULT_GATE),
    ("reflex_disconnected", w.Limit.DISCONNECT_GATE),
    ("soc_critical=", w.Limit.SOC_CRITICAL),
    ("range_stale=", w.Limit.STALE_RANGE),
    ("range=", w.Limit.RANGE_SCALING),
    ("vision_stale", w.Limit.STALE_VISION),
    ("clear_conf=", w.Limit.VISION_SCALING),
    ("nearby=", w.Limit.NEARBY),
]

_PACK_SOURCES = ("battery", "ac_charging")


def _limit_from_caps(caps: list[SpeedCap]) -> tuple[int, int]:
    """(limit_reason, authority_scale) from the governor's own record of what it did.

    The binding reason is the most restrictive cap; authority is the product of every scale,
    because Buddy's gates compound (range 0.5 × stale vision 0.5 = 0.25). An unrecognised
    reason still reduces authority honestly and is logged, but reports NONE rather than a guess.
    """
    if not caps:
        return w.Limit.NONE, 255
    scale = 1.0
    for c in caps:
        scale *= max(0.0, min(1.0, c.scale))
    binding = min(caps, key=lambda c: c.scale)
    reason = next(
        (code for prefix, code in _REASON_PREFIX if binding.reason.startswith(prefix)),
        None,
    )
    if reason is None:
        log.warning("unmapped speed cap reason %r — reporting NONE", binding.reason)
        reason = w.Limit.NONE
    return reason, round(scale * 255)


def _norm(mm_s: float, cap: int) -> int:
    """Track speed as the ±10000 the ghost reticle expects, against the vehicle's own cap."""
    return max(-10_000, min(10_000, round(mm_s * 10_000 / max(1, cap))))


class BuddyAdapter:
    """Implements `bridge.VehicleAdapter` for Buddy."""

    def __init__(
        self,
        tick: TickLoop,
        registry: Any,
        manifest_path: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tick = tick
        self._registry = registry
        self._clock = clock
        self._estop_last_s: float | None = None
        self._estop_held = False
        with open(manifest_path, "rb") as f:
            self._manifest = f.read()
        # The client compares this against the manifest it was served. A mismatch means the HUD
        # may be showing limits this robot does not enforce — a fault, not a note.
        self._manifest_crc = vf.crc16_ccitt(self._manifest)
        log.info(
            "vantage adapter: manifest %d B, crc 0x%04X",
            len(self._manifest),
            self._manifest_crc,
        )

    def _param(self, name: str, default: int) -> int:
        return (
            int(self._registry.get_value(name, default)) if self._registry else default
        )

    @property
    def _max_v(self) -> int:
        return self._param("reflex.max_v_mm_s", 500)

    @property
    def _max_w(self) -> int:
        return self._param("reflex.max_w_mrad_s", 2000)

    # ── bridge.VehicleAdapter ────────────────────────────

    def manifest_json(self) -> bytes:
        return self._manifest

    def manifest_crc(self) -> int:
        return self._manifest_crc

    def class_kind(self) -> str:
        return "ground"

    def core_fields(self) -> tuple:
        r = self._tick.robot
        v = {n: 0 for n in w.TELEMETRY_CORE_FIELDS}
        v["t_send_us"] = int(r.tick_mono_ms * 1000)
        v["quat_0"] = 16384  # identity: see "No attitude" in the module docstring
        v["mode"] = _MODE_VALUES.get(r.mode, 0)
        v["arm_state"] = 1 if r.mode in MOTION_MODES else 0
        v["vel_fwd_mms"] = max(-32768, min(32767, round(r.v_meas_mm_s)))
        # Gyro yaw rate (channels.yaw_rate): 0.01 rad/s, CCW (left) positive, as gyro_z is.
        v["rate_body_2"] = max(-32768, min(32767, round(r.gyro_z_mrad_s / 10)))
        # Relative heading (channels.heading = "relative"), 0.01 deg clockwise from boot.
        v["hdg_cdeg"] = round(r.heading_rel_deg * 100) % 36000

        p = r.power
        on_pack = p.source in _PACK_SOURCES and p.voltage_mv > 0
        v["pack_mv"] = (
            min(0xFFFE, p.voltage_mv) if on_pack else w.Sentinel.NO_READING_U16
        )
        v["cell_min_mv"] = w.Sentinel.NO_READING_U16
        v["current_ca"] = (
            max(-32767, min(32767, p.current_ma // 10))
            if on_pack
            else w.Sentinel.NO_READING_I16
        )
        v["temp_max_c"] = w.Sentinel.NO_READING_I8  # no temperature sensor on Buddy
        v["soc_pct"] = p.soc_pct if 0 <= p.soc_pct <= 100 else w.Sentinel.SOC_UNKNOWN

        warn = 0
        for fault, bit in _FAULT_TO_WARN:
            if r.fault_flags & fault:
                warn |= bit
        if p.pmic_undervoltage:
            warn |= w.Warn.BATT_CRITICAL
        # The same thresholds the supervisor's own SoC gate and speech policy use.
        if 0 <= p.soc_pct <= self._param("power.soc_critical_pct", 10):
            warn |= w.Warn.BATT_CRITICAL
        elif 0 <= p.soc_pct <= self._param("power.soc_warn_pct", 25):
            warn |= w.Warn.BATT_LOW
        v["warn_bits"] = warn
        # Buddy has no radio metric of its own; the client measures the WiFi link itself.
        v["link_quality"] = 255
        return tuple(v[n] for n in w.TELEMETRY_CORE_FIELDS)

    def class_fields(self) -> tuple:
        r = self._tick.robot
        g = {n: 0 for n in w.GROUND_CLASS_FIELDS}
        g["clearance_arc"] = bytes(8)
        g["reserved"] = bytes(34)

        # Per-wheel command, split from the capped twist exactly as the MCU does (control.cpp).
        half_wb = self._param("reflex.wheelbase_mm", 150) / 2.0
        w_rad = r.twist_capped.w_mrad_s / 1000.0
        cap = self._max_v
        g["track_left_cmd"] = _norm(r.twist_capped.v_mm_s - w_rad * half_wb, cap)
        g["track_right_cmd"] = _norm(r.twist_capped.v_mm_s + w_rad * half_wb, cap)
        g["track_left_meas"] = _norm(r.speed_l_mm_s, cap)
        g["track_right_meas"] = _norm(r.speed_r_mm_s, cap)
        # How far measured falls short of commanded (the HUD warns past 25 %), on the mean of the
        # two sides. 0 near a standstill, where the ratio is noise rather than traction loss.
        cmd = (g["track_left_cmd"] + g["track_right_cmd"]) / 2
        meas = (g["track_left_meas"] + g["track_right_meas"]) / 2
        g["slip_pct"] = (
            0
            if abs(cmd) < 500
            else max(-100, min(100, round((cmd - meas) * 100 / cmd)))
        )

        # RangeStatus.OK == 0; anything else is no reading, not a distance of zero.
        ok = r.range_status == 0 and r.range_mm > 0
        g["range_fwd_mm"] = min(0xFFFE, r.range_mm) if ok else w.Sentinel.NO_READING_U16

        g["limit_reason"], g["authority_scale"] = _limit_from_caps(r.speed_caps)
        return tuple(g[n] for n in w.GROUND_CLASS_FIELDS)

    def apply_control(self, frame: vf.Control) -> None:
        """Into the tick loop as a teleop twist source. Never to an MCU.

        **E-STOP first**, before the arm filter: a watching client is exactly the one that needs
        to stop a robot someone else is driving. Then **a disarmed client does not drive** — it
        streams keepalives the TTL watches, and applying them would stomp the dashboard's own
        teleop at 100 Hz. `arm_state` maps to the mode gate; that is what it is for.
        """
        if frame.buttons & w.Button.ESTOP:
            self.estop()
            return
        self._estop_held = False

        if frame.arm_state == 0:
            return

        v, wz = axes_to_twist(
            frame, speed_max_mms=self._max_v, yaw_rate_max_mrads=self._max_w
        )
        self._tick.set_teleop_twist(v, wz)

    def request_mode(self, mode: int, armed: bool) -> None:
        """A client's mode request, once per request (Vantage `CONTROL.md` §8a).

        Through the robot's own state machine, which may refuse — the HTTP API's path. Entering
        a motion mode needs an armed frame; asking for IDLE (stopping) does not. Out of ERROR,
        IDLE means `clear_error()`, the same recovery the dashboard's clear button runs, so
        leaving a fault is always an explicit operator request.
        """
        if not 0 <= mode < len(_MODES_BY_VALUE):
            log.warning("vantage: request for unknown mode value %d ignored", mode)
            return
        target = _MODES_BY_VALUE[mode]
        if target in MOTION_MODES and not armed:
            log.info(
                "vantage: %s refused — request came from a disarmed client",
                target.value,
            )
            return
        current = self._tick.robot.mode
        if current == Mode.ERROR and target == Mode.IDLE:
            ok, reason = self._tick.clear_error()
        else:
            ok, reason = self._tick.request_mode(target.value)
        log.info(
            "vantage: request %s from %s: %s",
            target.value,
            current.value,
            "ok" if ok else f"refused ({reason})",
        )

    def estop(self) -> None:
        """Fire Buddy's E-STOP. Also called directly by the bridge for a valid frame holding
        ESTOP that it discarded as late or duplicate — ordering never blocks a stop. Throttled
        to one MCU command per `ESTOP_REFIRE_S`; the teleop latch is zeroed on every call."""
        if not self._estop_held:
            log.warning("E-STOP from Vantage client")
            self._estop_held = True
        self._tick.set_teleop_twist(0, 0)
        now = self._clock()
        if self._estop_last_s is not None and now - self._estop_last_s < ESTOP_REFIRE_S:
            return
        self._estop_last_s = now
        self._tick.estop()
