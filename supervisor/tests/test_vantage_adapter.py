"""BuddyAdapter — the Vantage seam on Buddy.

Covers the control contract shared with Scout (~/vantage/docs/CONTROL.md): E-STOP before the
arm filter, a disarmed client never drives, axes map against Buddy's *live* caps, stick right
turns right. Plus Buddy's own telemetry mapping, including every governor gate driven through
the real `apply_safety` — so a reworded `SpeedCap.reason` fails here rather than silently
showing no reason on the HUD.

The adapter imports Vantage's wire modules from ~/vantage/supervisor, exactly as main.py does
under `--vantage`. Without that checkout these tests skip: Vantage is an optional client.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

VANTAGE = Path.home() / "vantage"
sys.path.insert(0, str(VANTAGE / "supervisor"))
vf = pytest.importorskip("vantage_frame")
w = pytest.importorskip("vantage_wire")

from supervisor.core.safety import apply_safety  # noqa: E402
from supervisor.core.state import (  # noqa: E402
    DesiredTwist,
    Mode,
    RobotState,
    WorldState,
)
from supervisor.devices.protocol import Fault, RangeStatus  # noqa: E402
from supervisor.devices.vantage_adapter import (  # noqa: E402
    ESTOP_REFIRE_S,
    BuddyAdapter,
    _limit_from_caps,
)

FIXTURES = VANTAGE / "crates/vantage-proto/tests/fixtures"


class FakeTick:
    def __init__(self) -> None:
        self.robot = RobotState()
        self.twists: list[tuple[int, int]] = []
        self.estops = 0
        self.requests: list[str] = []
        self.clears = 0

    def set_teleop_twist(self, v_mm_s: int, w_mrad_s: int) -> None:
        self.twists.append((v_mm_s, w_mrad_s))

    def estop(self) -> bool:
        self.estops += 1
        return True

    # The state machine itself, so the adapter is tested against Buddy's real transition table.
    def request_mode(self, target: str) -> tuple[bool, str]:
        from supervisor.core.state_machine import SupervisorSM

        sm = SupervisorSM()
        sm._mode = self.robot.mode
        ok, why = sm.request_mode(Mode(target), True, self.robot.fault_flags)
        self.robot.mode = sm.mode
        self.requests.append(target)
        return ok, why

    def clear_error(self) -> tuple[bool, str]:
        self.clears += 1
        if self.robot.mode != Mode.ERROR:
            return False, "not in ERROR mode"
        self.robot.mode = Mode.IDLE
        return True, "ok"


class Registry:
    def __init__(self, **values: int) -> None:
        self.values = {
            "reflex.max_v_mm_s": 500,
            "reflex.max_w_mrad_s": 2000,
            "reflex.wheelbase_mm": 150,
            "power.soc_critical_pct": 10,
            "power.soc_warn_pct": 25,
        }
        self.values.update({k.replace("__", "."): v for k, v in values.items()})

    def get_value(self, name: str, default=None):
        return self.values.get(name, default)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def rig(tmp_path: Path) -> tuple[BuddyAdapter, FakeTick, Registry, Clock]:
    manifest = tmp_path / "buddy.vehicle.toml"
    manifest.write_bytes(b'[robot]\nid = "buddy"\n')
    tick, reg, clock = FakeTick(), Registry(), Clock()
    adapter = BuddyAdapter(tick, reg, str(manifest), clock=clock)  # type: ignore[arg-type]
    return adapter, tick, reg, clock


def frame(seq: int = 1, **fields: int):
    vals = {n: 0 for n in w.CONTROL_FIELDS}
    vals.update(magic=w.MAGIC, version=w.VERSION, msg_type=w.MsgType.CONTROL, seq=seq)
    vals.update(fields)
    buf = bytearray(w.CONTROL.pack(*(vals[n] for n in w.CONTROL_FIELDS)))
    buf[-2:] = vf.crc16_ccitt(bytes(buf[:-2])).to_bytes(2, "little")
    return vf.decode_control(bytes(buf))


def core(adapter: BuddyAdapter) -> dict:
    vals = adapter.core_fields()
    w.TELEMETRY_CORE.pack(*vals)  # every value must be in wire range
    return dict(zip(w.TELEMETRY_CORE_FIELDS, vals))


def ground(adapter: BuddyAdapter) -> dict:
    vals = adapter.class_fields()
    w.GROUND_CLASS.pack(*vals)
    return dict(zip(w.GROUND_CLASS_FIELDS, vals))


# ── Control ──────────────────────────────────────────────────────


def test_estop_fixture_fires_while_disarmed(rig) -> None:
    adapter, tick, _, _ = rig
    path = FIXTURES / "control_estop.bin"
    if not path.is_file():
        pytest.skip("vantage fixtures not present")
    f = vf.decode_control(path.read_bytes())
    assert f.arm_state == 0 and f.buttons & w.Button.ESTOP
    adapter.apply_control(f)
    assert tick.estops == 1
    assert tick.twists == [(0, 0)]


def test_disarmed_client_never_drives(rig) -> None:
    adapter, tick, _, _ = rig
    adapter.apply_control(frame(arm_state=0, axis_drive_y=32_767))
    assert (tick.estops, tick.twists) == (0, [])


def test_axes_map_against_live_caps_not_the_manifest(rig) -> None:
    """Buddy's caps are runtime-tunable; the adapter must follow the registry."""
    adapter, tick, reg, _ = rig
    adapter.apply_control(frame(seq=1, arm_state=1, axis_drive_y=32_767))
    reg.values["reflex.max_v_mm_s"] = 300
    adapter.apply_control(frame(seq=2, arm_state=1, axis_drive_y=32_767))
    assert [t[0] for t in tick.twists] == [500, 300]


def test_stick_right_turns_right(rig) -> None:
    adapter, tick, _, _ = rig
    adapter.apply_control(frame(seq=1, arm_state=1, axis_drive_x=32_767))
    adapter.apply_control(frame(seq=2, arm_state=1, axis_drive_x=-32_767))
    assert tick.twists == [(0, -2000), (0, 2000)], "CW negative, CCW positive"


def test_held_estop_is_throttled_and_shares_the_bridge_path(rig) -> None:
    adapter, tick, _, clock = rig
    for i in range(20):  # 200 ms of held E-STOP at 100 Hz
        clock.t += 0.01
        adapter.apply_control(frame(seq=i + 1, buttons=w.Button.ESTOP))
    assert tick.estops == round(0.2 / ESTOP_REFIRE_S)
    before = tick.estops
    adapter.estop()  # the bridge, for a late frame, at the same instant as the last one
    assert tick.estops == before, "direct calls share the throttle"


def test_reserved_bits_are_not_estop(rig) -> None:
    adapter, tick, _, _ = rig
    adapter.apply_control(frame(arm_state=0, buttons=w.Button.RESERVED_MASK))
    assert tick.estops == 0


# ── Telemetry ────────────────────────────────────────────────────


def test_pmic_rail_is_never_reported_as_pack_voltage(rig) -> None:
    adapter, tick, _, _ = rig
    p = tick.robot.power
    p.source, p.voltage_mv, p.soc_pct = "usb", 3300, -1  # PMIC-only: a 3V3 rail
    c = core(adapter)
    assert c["pack_mv"] == w.Sentinel.NO_READING_U16
    assert c["soc_pct"] == w.Sentinel.SOC_UNKNOWN
    assert c["current_ca"] == 0
    p.source, p.voltage_mv, p.current_ma, p.soc_pct = "battery", 7650, 820, 61
    c = core(adapter)
    assert (c["pack_mv"], c["current_ca"], c["soc_pct"]) == (7650, 82, 61)
    assert c["cell_min_mv"] == w.Sentinel.NO_READING_U16, "cells are inside the HAT"


def test_battery_warnings_use_the_supervisors_own_thresholds(rig) -> None:
    adapter, tick, _, _ = rig
    p = tick.robot.power
    p.source, p.voltage_mv = "battery", 7000
    for soc, want in ((60, 0), (20, w.Warn.BATT_LOW), (8, w.Warn.BATT_CRITICAL)):
        p.soc_pct = soc
        assert (
            core(adapter)["warn_bits"] & (w.Warn.BATT_LOW | w.Warn.BATT_CRITICAL)
            == want
        )


def test_faults_and_mode_reach_the_wire(rig) -> None:
    adapter, tick, _, _ = rig
    r = tick.robot
    r.mode, r.fault_flags = Mode.ERROR, int(Fault.ESTOP | Fault.TILT)
    c = core(adapter)
    assert c["mode"] == list(Mode).index(Mode.ERROR)
    assert c["arm_state"] == 0
    assert (
        c["warn_bits"] & w.Warn.FAILSAFE_ACTIVE
        and c["warn_bits"] & w.Warn.ATTITUDE_LIMIT
    )
    r.mode = Mode.TELEOP
    assert core(adapter)["arm_state"] == 1


def test_wheel_commands_split_like_the_mcu_and_measured_is_measured(rig) -> None:
    adapter, tick, _, _ = rig
    r = tick.robot
    r.twist_capped = DesiredTwist(0, 1000)  # 1 rad/s spin, wheelbase 150 -> ±75 mm/s
    r.speed_l_mm_s, r.speed_r_mm_s = -60, 70
    g = ground(adapter)
    assert (g["track_left_cmd"], g["track_right_cmd"]) == (-1500, 1500)
    assert (g["track_left_meas"], g["track_right_meas"]) == (-1200, 1400)


def test_range_without_a_valid_reading_is_absent(rig) -> None:
    adapter, tick, _, _ = rig
    r = tick.robot
    r.range_mm, r.range_status = 800, RangeStatus.NOT_READY
    assert ground(adapter)["range_fwd_mm"] == w.Sentinel.NO_READING_U16
    r.range_status = RangeStatus.OK
    assert ground(adapter)["range_fwd_mm"] == 800


# ── Every governor gate, through the real apply_safety ───────────


def _teleop(**robot) -> tuple[RobotState, WorldState]:
    r = RobotState(mode=Mode.TELEOP, reflex_connected=True, range_status=RangeStatus.OK)
    r.range_mm = 2000
    for k, v in robot.items():
        setattr(r, k, v)
    return r, WorldState()


@pytest.mark.parametrize(
    "setup,want_reason,want_scale",
    [
        (lambda: (RobotState(mode=Mode.IDLE), WorldState()), w.Limit.MODE_GATE, 0),
        (lambda: _teleop(fault_flags=int(Fault.STALL)), w.Limit.FAULT_GATE, 0),
        (lambda: _teleop(reflex_connected=False), w.Limit.DISCONNECT_GATE, 0),
        (lambda: _teleop(range_mm=280), w.Limit.RANGE_SCALING, 64),
        (lambda: _teleop(range_mm=450), w.Limit.RANGE_SCALING, 128),
        (lambda: _teleop(range_status=RangeStatus.TIMEOUT), w.Limit.STALE_RANGE, 128),
        (lambda: _teleop(), w.Limit.NONE, 255),
    ],
)
def test_governor_gate_maps_to_wire(setup, want_reason, want_scale) -> None:
    robot, world = setup()
    apply_safety(DesiredTwist(300, 0), robot, world)
    assert _limit_from_caps(robot.speed_caps) == (want_reason, want_scale)


def test_soc_critical_gate_maps_to_wire() -> None:
    robot, world = _teleop()
    robot.power.soc_pct = 5
    apply_safety(DesiredTwist(300, 0), robot, world)
    assert _limit_from_caps(robot.speed_caps) == (w.Limit.SOC_CRITICAL, 0)


def test_vision_gates_map_and_compound() -> None:
    robot, world = _teleop(range_mm=450)  # range 0.5
    world.clear_confidence = 0.9
    world.vision_rx_mono_ms = time.monotonic() * 1000.0 - 10_000  # stale: 0.5
    apply_safety(DesiredTwist(300, 0), robot, world)
    reason, scale = _limit_from_caps(robot.speed_caps)
    assert reason in (w.Limit.RANGE_SCALING, w.Limit.STALE_VISION)
    assert scale == 64, "0.5 x 0.5 compounds to a quarter"

    robot, world = _teleop()
    world.clear_confidence = 0.1
    world.vision_rx_mono_ms = time.monotonic() * 1000.0
    apply_safety(DesiredTwist(300, 0), robot, world)
    assert _limit_from_caps(robot.speed_caps) == (w.Limit.VISION_SCALING, 64)


# ── TickLoop.estop(): the one public action every caller uses ────


class _Workers:
    def __getattr__(self, name):  # TickLoop only needs the object to exist here
        return lambda *a, **k: None


class _Reflex:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.sent = 0

    def on_telemetry(self, cb) -> None:
        pass

    def send_estop(self) -> None:
        self.sent += 1


@pytest.mark.parametrize("connected", [True, False])
def test_tickloop_estop_zeroes_teleop_and_reaches_the_mcu_when_it_can(
    connected,
) -> None:
    from supervisor.core.tick_loop import TickLoop

    reflex = _Reflex(connected)
    loop = TickLoop(reflex=reflex, face=None, workers=_Workers())  # type: ignore[arg-type]
    loop.set_teleop_twist(400, 900)
    assert loop.estop() is connected
    assert reflex.sent == (1 if connected else 0)
    t = loop._behavior._teleop_twist
    assert (t.v_mm_s, t.w_mrad_s) == (0, 0), "zeroed even when the MCU is unreachable"


# ── Mode requests (Vantage CONTROL.md §8a) ──────────────────────────────────────────────


def _v(mode: Mode) -> int:
    return list(Mode).index(mode)


def test_armed_request_enters_teleop_through_the_state_machine(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.mode = Mode.IDLE
    adapter.request_mode(_v(Mode.TELEOP), armed=True)
    assert tick.robot.mode == Mode.TELEOP


def test_disarmed_client_cannot_enter_a_motion_mode(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.mode = Mode.IDLE
    adapter.request_mode(_v(Mode.TELEOP), armed=False)
    assert tick.robot.mode == Mode.IDLE and tick.requests == []


def test_any_client_may_ask_to_stop(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.mode = Mode.TELEOP
    adapter.request_mode(_v(Mode.IDLE), armed=False)
    assert tick.robot.mode == Mode.IDLE


def test_idle_out_of_error_is_the_robots_own_recovery(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.mode = Mode.ERROR
    adapter.request_mode(_v(Mode.IDLE), armed=False)
    assert tick.clears == 1 and tick.robot.mode == Mode.IDLE


def test_the_state_machine_may_refuse(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.mode = Mode.ERROR
    adapter.request_mode(_v(Mode.TELEOP), armed=True)
    assert tick.robot.mode == Mode.ERROR, "ERROR is left only by recovery"
    tick.robot.mode = Mode.TELEOP
    adapter.request_mode(_v(Mode.WANDER), armed=True)
    assert tick.robot.mode == Mode.TELEOP, "Buddy enters WANDER only from IDLE"


def test_unknown_mode_value_is_ignored(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.mode = Mode.IDLE
    adapter.request_mode(250, armed=True)
    assert tick.robot.mode == Mode.IDLE and tick.requests == []


# ── Gyro yaw rate and relative heading (Vantage channels.yaw_rate / heading) ──


def test_yaw_rate_and_relative_heading_are_served(rig) -> None:
    adapter, tick, _, _ = rig
    tick.robot.gyro_z_mrad_s = 350  # turning left at 0.35 rad/s
    tick.robot.heading_rel_deg = 90.5
    c = core(adapter)
    assert c["rate_body_2"] == 35, "0.01 rad/s, left positive, as gyro_z"
    assert c["hdg_cdeg"] == 9050
    tick.robot.heading_rel_deg = 359.999
    assert core(adapter)["hdg_cdeg"] < 36000, "wraps, never 36000"


def test_manifest_declares_what_the_adapter_serves() -> None:
    import tomllib

    m = tomllib.loads((VANTAGE / "profiles/buddy.vehicle.toml").read_text())
    ch = m["channels"]
    assert ch["imu_quat"] is False, "identity quaternion is served: not an attitude"
    assert ch["yaw_rate"] is True
    assert ch["heading"] == "relative", "no magnetometer: never claim magnetic"
