"""One WANDER episode in the fast tier, scored exactly as the full tier scores it.

The meter is Vantage's `sim/wander_meter.py` (world truth: coverage, contacts, stops). The
supervisor's view is fed from the same dict its `/status` endpoint serves, sampled at the same
5 Hz the full tier polls it, so a metric means the same thing in both tiers.

  uv run python episode.py --room office --duration 180
  uv run python episode.py --rooms office hallway kitchen --duration 180 --json out.json
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import fast_env
import wander_meter  # Vantage sim, on sys.path via fast_env

PHYS_SAMPLE_S = 0.05  # 20 Hz, as buddy_sim samples truth
STATUS_SAMPLE_S = 0.2  # 5 Hz, as buddy_sim polls /status


def run_wander(
    room: str,
    yaw_deg: float = 0.0,
    duration_s: float = 180.0,
    *,
    skill_params: dict[str, Any] | None = None,
    skill: Any = None,
    sonar_specular_max_deg: float | None = None,
    open_doors: frozenset[str] = frozenset(),
    with_track: bool = False,
    spawn: int = 0,
) -> dict[str, Any]:
    fb = fast_env.FastBuddy(
        room,
        yaw_deg,
        open_doors=open_doors,
        spawn=spawn,
        skill_params=skill_params,
        skill=skill,
        sonar_specular_max_deg=sonar_specular_max_deg,
    )
    try:
        if not fb.run_until(lambda f: f.mode == "IDLE", 5.0):
            return {"room": room, "error": f"never reached IDLE (mode {fb.mode})"}
        ok, why = fb.request_mode("WANDER")
        if not ok:
            return {"room": room, "error": f"WANDER refused: {why}"}
        meter = wander_meter.WanderMeter(fb.b.model, fb.emu.fw.fault["OBSTACLE"])
        next_status = 0.0
        t_end = fb.t_s + duration_s
        while fb.t_s < t_end:
            fb.step(PHYS_SAMPLE_S)
            meter.sample_physics(fb.b, fb.emu, fb.t_s)
            if fb.t_s >= next_status:
                meter.sample_status(
                    {**fb.tick.robot.to_dict(), **fb.tick.world.to_dict()}, fb.t_s
                )
                next_status = fb.t_s + STATUS_SAMPLE_S
        out: dict[str, Any] = {
            "room": room,
            "yaw": yaw_deg,
            "spawn": spawn,
            "tier": "fast",
            **meter.result(),
        }
        out["caps_seen"] = meter.caps_seen
        out["caps_first_t"] = meter.caps_first_t
        if with_track:
            out["track"] = meter.track
        return out
    finally:
        fb.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rooms", nargs="+", default=["office"])
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--duration", type=float, default=180.0)
    ap.add_argument("--json", help="write all results here")
    a = ap.parse_args()
    results = []
    for room in a.rooms:
        t0 = time.perf_counter()
        r = run_wander(room, a.yaw, a.duration)
        wall = time.perf_counter() - t0
        results.append(r)
        if "error" in r:
            print(f"{room:16s} ERROR {r['error']}")
            continue
        print(
            f"{room:16s} {wall:5.1f} s wall ({a.duration / wall:4.1f}x)  "
            f"cover {r['coverage_m2_per_min']} m²/min  bumps {r['bumps']}  "
            f"MCU stops {r['obstacle_stops']}  stuck {r['stuck_frac']}  "
            f"authority {r['mean_authority']}"
        )
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
