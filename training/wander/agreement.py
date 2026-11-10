"""Agreement gate: the fast tier must behave like the full stack (Vantage SIM-AUTONOMY.md §3).

Runs the same WANDER episode in both tiers and compares them:

  full  ~/vantage/sim/buddy_sim.py --supervisor --test wander   real supervisor process, real time,
                                                               PTY, wall clock
  fast  episode.run_wander                                     same supervisor code, in process,
                                                               virtual clock

Trajectories are aligned at first motion (each tier's start-up latency differs and is not the
thing being tested). The full tier runs on the wall clock, so it is not bit-repeatable, and a
wandering robot is chaotic. Positions therefore agree only over a short horizon, and that horizon
is what the gate checks. Discrete behaviour (which governor caps appeared, MCU stops) is compared
over the whole episode.

  uv run python agreement.py                 default cases
  uv run python agreement.py --case office 0 30

Needs the full tier free: nothing else may hold the supervisor's ports (8080, Vantage 5599-5602).
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import episode
import fast_env

SIM = fast_env.SIM_DIR
SIM_PY = Path(os.environ.get("VANTAGE_SIM_PYTHON", SIM / ".venv" / "bin" / "python"))

DEFAULT_CASES = [("office", 0.0, 30.0), ("hallway", 90.0, 30.0), ("kitchen", 0.0, 30.0)]
MOVING_MM_S = 20.0
HORIZON_S = 10.0  # positions must agree over this long after first motion
POS_TOL_M = 0.15  # ... to within this
YAW_TOL_DEG = 15.0


def run_full(room: str, yaw: float, duration: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "full.json"
        cmd = [
            str(SIM_PY),
            "buddy_sim.py",
            "--room",
            room,
            "--yaw",
            str(yaw),
            "--supervisor",
            "--test",
            "wander",
            "--duration",
            str(duration),
            "--out",
            str(out),
        ]
        env = {**os.environ, "MUJOCO_GL": os.environ.get("MUJOCO_GL", "egl")}
        p = subprocess.run(
            cmd,
            cwd=SIM,
            capture_output=True,
            text=True,
            timeout=duration + 120,
            env=env,
        )
        if not out.exists():
            tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
            return {"error": "full tier produced no result: " + " | ".join(tail)}
        return json.loads(out.read_text())


def _first_motion_t(track: list) -> float | None:
    return next((t for t, _x, _y, _yaw, v in track if abs(v) > MOVING_MM_S), None)


def _from_first_motion(track: list) -> list[tuple[float, float, float, float]]:
    t0 = _first_motion_t(track)
    if t0 is None:
        return []
    return [(t - t0, x, y, yaw) for t, x, y, yaw, _v in track if t >= t0]


def _caps_within_horizon(r: dict) -> set[str]:
    t0 = _first_motion_t(r["track"]) or 0.0
    return {k for k, t in r["caps_first_t"].items() if t <= t0 + HORIZON_S}


def _at(track: list, t: float) -> tuple[float, float, float] | None:
    ts = [p[0] for p in track]
    i = bisect.bisect_left(ts, t)
    if i >= len(track):
        return None
    return track[i][1], track[i][2], track[i][3]


def compare(full: dict, fast: dict) -> dict[str, Any]:
    a, b = _from_first_motion(full["track"]), _from_first_motion(fast["track"])
    if not a or not b:
        return {"pass": False, "why": "a tier never moved"}
    pos_err, yaw_err, series = 0.0, 0.0, []
    t = 0.5
    while t <= HORIZON_S:
        pa, pb = _at(a, t), _at(b, t)
        if pa is None or pb is None:
            break
        e = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        dy = abs((pa[2] - pb[2] + 180) % 360 - 180)
        pos_err, yaw_err = max(pos_err, e), max(yaw_err, dy)
        series.append((t, round(e, 3)))
        t += 0.5
    caps_full, caps_fast = _caps_within_horizon(full), _caps_within_horizon(fast)
    checks = {
        f"position within {POS_TOL_M} m for {HORIZON_S:.0f} s": pos_err <= POS_TOL_M,
        f"heading within {YAW_TOL_DEG}° for {HORIZON_S:.0f} s": yaw_err <= YAW_TOL_DEG,
        f"same governor cap kinds for {HORIZON_S:.0f} s": caps_full == caps_fast,
        "MCU stops within 1": abs(full["obstacle_stops"] - fast["obstacle_stops"]) <= 1,
        "both stayed in WANDER": full["mode_share"].get("WANDER", 0) > 0.95
        and fast["mode_share"].get("WANDER", 0) > 0.95,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "max_pos_err_m": round(pos_err, 3),
        "max_yaw_err_deg": round(yaw_err, 1),
        "pos_err_series": series,
        "caps": {"full": sorted(caps_full), "fast": sorted(caps_fast)},
        "side_by_side": {
            k: (full[k], fast[k])
            for k in (
                "coverage_m2_per_min",
                "mean_speed_mm_s",
                "bumps",
                "obstacle_stops",
                "stuck_frac",
                "mean_authority",
            )
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--case", nargs=3, action="append", metavar=("ROOM", "YAW", "SECONDS")
    )
    ap.add_argument("--json", help="write the full comparison here")
    a = ap.parse_args()
    cases = [(r, float(y), float(d)) for r, y, d in a.case] if a.case else DEFAULT_CASES
    report, ok = [], True
    for room, yaw, dur in cases:
        full = run_full(room, yaw, dur)
        fast = episode.run_wander(room, yaw, dur, with_track=True)
        if "error" in full or "error" in fast:
            print(
                f"{room} yaw {yaw:g}: ERROR full={full.get('error')} fast={fast.get('error')}"
            )
            ok = False
            report.append(
                {
                    "room": room,
                    "yaw": yaw,
                    "error": [full.get("error"), fast.get("error")],
                }
            )
            continue
        c = compare(full, fast)
        ok &= c["pass"]
        report.append({"room": room, "yaw": yaw, "duration_s": dur, **c})
        print(
            f"{room} yaw {yaw:g}, {dur:.0f} s: {'PASS' if c['pass'] else 'FAIL'}  "
            f"pos err ≤ {c['max_pos_err_m']} m, yaw err ≤ {c['max_yaw_err_deg']}°"
        )
        for name, passed in c["checks"].items():
            print(f"   {'ok ' if passed else 'XX '} {name}")
        print(f"   caps full {c['caps']['full']}  fast {c['caps']['fast']}")
        for k, (f, s) in c["side_by_side"].items():
            print(f"   {k:22s} full {f:<8} fast {s}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1) + "\n")
    print("AGREEMENT", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
