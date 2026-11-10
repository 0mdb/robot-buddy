"""The fast tier reproduces what the full stack measured (Vantage `just sim-check`, 2026-11-09).

Same room and spawn as sim-check (office, yaw 0, facing a wall ~2.5 m away). The full-tier numbers
in the comments are what the real supervisor produced over the PTY on the wall clock.
"""

from __future__ import annotations

import pytest

import fast_env


@pytest.fixture
def fb():
    f = fast_env.FastBuddy("office", 0.0)
    assert f.run_until(lambda x: x.mode == "IDLE", 5.0), f.mode
    yield f
    f.close()


def _drive(fb: fast_env.FastBuddy, v: int, seconds: float, stop_if=None) -> None:
    """Resend the twist at 20 Hz, as a client does (well inside the 0.5 s TTL)."""
    end = fb.t_s + seconds
    while fb.t_s < end:
        fb.set_teleop_twist(v, 0)
        fb.step(0.05)
        if stop_if is not None and stop_if(fb):
            return


def test_teleop_silence_stops_the_robot_like_the_full_tier(fb):
    assert fb.request_mode("TELEOP")[0]
    _drive(fb, 300, 1.5)
    assert fb.b.body_vel()[0] > 200, "should be cruising before the client goes silent"
    t_silent = fb.t_s
    assert fb.run_until(lambda x: abs(x.b.body_vel()[0]) < 5, 3.0)
    stop_ms = (fb.t_s - t_silent) * 1000
    # Full tier: 810 and 814 ms on two runs. TTL 500 ms + the firmware's decel ramp.
    assert 700 <= stop_ms <= 950, stop_ms


def test_range_governor_then_mcu_stop_at_the_wall(fb):
    assert fb.request_mode("TELEOP")[0]
    seen: list[str] = []

    def watch(x: fast_env.FastBuddy) -> bool:
        for c in x.tick.robot.speed_caps:
            kind = c.reason.split("=")[0] + (
                "<" + c.reason.split("<")[1] if "<" in c.reason else ""
            )
            if kind not in seen:
                seen.append(kind)
        return bool(x.emu.faults & x.emu.fw.fault["OBSTACLE"])

    _drive(fb, 300, 20.0, stop_if=watch)
    assert fb.emu.faults & fb.emu.fw.fault["OBSTACLE"], "never reached the wall"
    # Full tier: RANGE_SCALING 50 % then 25 %, then the MCU stop; the robot comes to rest at
    # sonar 212-215 mm.
    assert seen[:2] == ["range<500", "range<300"], seen
    assert fb.emu.range_mm < 250  # latched on the first sample under the threshold
    # sim-check reports the range once the robot is at rest, stopping distance included.
    _drive(fb, 300, 3.0, stop_if=lambda x: abs(x.b.body_vel()[0]) < 5)
    assert 195 <= fb.emu.range_mm <= 235, fb.emu.range_mm


def test_estop_from_teleop_goes_to_error(fb):
    assert fb.request_mode("TELEOP")[0]
    _drive(fb, 200, 0.5)
    fb.estop()
    assert fb.run_until(lambda x: x.mode == "ERROR", 1.0), fb.mode


def test_wander_moves_and_uses_the_planner_default_skill(fb):
    assert fb.request_mode("WANDER")[0]
    x0, y0, *_ = fb.b.pose()
    fb.step(20.0)
    x1, y1, *_ = fb.b.pose()
    assert fb.mode == "WANDER"
    assert fb.tick.world.active_skill == "patrol_drift"
    assert ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 > 0.5
    assert fb.pipe.bad_frames == 0


def test_two_instances_share_a_process():
    a = fast_env.FastBuddy("office", 0.0)
    b = fast_env.FastBuddy("hallway", 90.0)
    for f in (a, b):
        assert f.run_until(lambda x: x.mode == "IDLE", 5.0)
        assert f.request_mode("WANDER")[0]
    for _ in range(20):
        a.step(0.5)
        b.step(0.5)
    assert a.mode == b.mode == "WANDER"
    assert abs(a.t_s - b.t_s) < 0.05
    a.close()
    b.close()
