"""Stage 2: tune WANDER's motion tunables in the fast tier (Vantage SIM-AUTONOMY.md).

CMA-ES over `skill_executor.WANDER_TUNABLES`, normalised to [0, 1] by their registry bounds. Every
candidate runs the same training episodes, in parallel across cores; two rooms are held out and
only scored at the end. The fast tier is deterministic, so a candidate's score is exact, not noisy.
Spawns vary by yaw so one fixed path cannot be memorised.

Objective: the operator's "gentle first" (2026-11-10). Bumps and MCU stops weigh heavily, coverage
is rewarded but secondary, and stuck time is a hard penalty. A coverage floor stops "barely
move" from winning. Weights are below, in one place.

  uv run python tune.py                         # ~30 generations, ~30 workers
  uv run python tune.py --generations 5 --workers 8 --episode 60    # quick look

Output in out/tune/: log.jsonl (per generation), best.json (params + scores), report.md
(defaults vs tuned on train and held-out rooms, 180 s episodes). To try a result on the robot,
set each `wander.<name>` through the param registry; nothing here changes robot defaults.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", message="Could not import matplotlib")
import cma  # noqa: E402

import episode  # noqa: E402
import fast_env  # noqa: E402,F401  (puts the supervisor and the sim on sys.path)
from supervisor.core.skill_executor import (  # noqa: E402
    WANDER_TUNABLES,
    wander_tunable_defaults,
)

# ---- objective: "gentle first" ---------------------------------------------------------------
W_COVER = 5.0  # per m²/min of new floor
W_BUMP = 1.0  # per side contact per minute
W_STOP = 1.0  # per MCU obstacle stop per minute
W_TOUCH = 10.0  # per unit fraction of time in contact (pushing, scraping)
W_STUCK = 20.0  # per unit fraction of time stuck (> 2 s still)
COVER_FLOOR = 0.25  # m²/min; ~65 % of the 0.39 baseline. Below it, a steep penalty:
W_FLOOR = 40.0

TRAIN_ROOMS = [
    "office",
    "living_room",
    "dining_room",
    "kitchen",
    "hallway",
    "recreation_room",
]
HOLDOUT_ROOMS = ["family_room", "bedroom"]
YAWS = [0.0, 135.0]
OUT = Path(__file__).parent / "out" / "tune"


def episode_score(r: dict[str, Any]) -> float:
    if "error" in r:
        return -100.0
    mins = r["duration_s"] / 60
    cov = r["coverage_m2_per_min"]
    return (
        W_COVER * cov
        - W_BUMP * r["bumps"] / mins
        - W_STOP * r["obstacle_stops"] / mins
        - W_TOUCH * r["contact_frac"]
        - W_STUCK * r["stuck_frac"]
        - W_FLOOR * max(0.0, COVER_FLOOR - cov)
    )


# ---- parameter encoding ----------------------------------------------------------------------
NAMES = list(WANDER_TUNABLES)


def decode(x: list[float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, xi in zip(NAMES, x):
        kind, lo, hi, step, _doc = WANDER_TUNABLES[name]
        v = lo + min(1.0, max(0.0, xi)) * (hi - lo)
        v = lo + round((v - lo) / step) * step
        v = min(hi, max(lo, v))
        out[name] = int(round(v)) if kind == "int" else round(v, 4)
    return out


def encode(params: dict[str, float]) -> list[float]:
    return [
        (params[n] - WANDER_TUNABLES[n][1])
        / (WANDER_TUNABLES[n][2] - WANDER_TUNABLES[n][1])
        for n in NAMES
    ]


# ---- evaluation ------------------------------------------------------------------------------
def _run(job: tuple[dict[str, float], str, float, float]) -> dict[str, Any]:
    params, room, yaw, dur = job
    r = episode.run_wander(room, yaw, dur, skill_params=params)
    r["score"] = episode_score(r)
    return r


def evaluate(
    pool: ProcessPoolExecutor,
    candidates: list[dict[str, float]],
    rooms: list[str],
    dur: float,
) -> list[tuple[float, list[dict[str, Any]]]]:
    jobs = [(p, room, yaw, dur) for p in candidates for room in rooms for yaw in YAWS]
    results = list(pool.map(_run, jobs, chunksize=1))
    per = len(rooms) * len(YAWS)
    out = []
    for i in range(len(candidates)):
        rs = results[i * per : (i + 1) * per]
        out.append((sum(r["score"] for r in rs) / per, rs))
    return out


def summary(rs: list[dict[str, Any]]) -> dict[str, float]:
    ok = [r for r in rs if "error" not in r]
    n = max(1, len(ok))
    mins = sum(r["duration_s"] for r in ok) / 60 or 1
    return {
        "score": round(sum(r["score"] for r in rs) / max(1, len(rs)), 3),
        "coverage_m2_per_min": round(sum(r["coverage_m2_per_min"] for r in ok) / n, 3),
        "bumps_per_3min": round(sum(r["bumps"] for r in ok) / mins * 3, 1),
        "mcu_stops_per_3min": round(sum(r["obstacle_stops"] for r in ok) / mins * 3, 1),
        "touching": round(sum(r["contact_frac"] for r in ok) / n, 3),
        "stuck": round(sum(r["stuck_frac"] for r in ok) / n, 3),
        "errors": len(rs) - len(ok),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=30)
    ap.add_argument("--popsize", type=int, default=16)
    ap.add_argument("--sigma", type=float, default=0.2)
    ap.add_argument(
        "--episode", type=float, default=120.0, help="seconds per training episode"
    )
    ap.add_argument(
        "--final", type=float, default=180.0, help="seconds per final-report episode"
    )
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    defaults = wander_tunable_defaults()
    es = cma.CMAEvolutionStrategy(
        encode(defaults),
        a.sigma,
        {"bounds": [0.0, 1.0], "popsize": a.popsize, "seed": a.seed, "verbose": -9},
    )
    best: tuple[float, dict[str, float]] = (-math.inf, defaults)
    log = (OUT / "log.jsonl").open("w")
    t_start = time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        base_score, base_rs = evaluate(pool, [defaults], TRAIN_ROOMS, a.episode)[0]
        print(f"defaults: train score {base_score:.3f}  {summary(base_rs)}", flush=True)
        best = (base_score, defaults)
        for gen in range(a.generations):
            xs = es.ask()
            cands = [decode(x) for x in xs]
            scored = evaluate(pool, cands, TRAIN_ROOMS, a.episode)
            es.tell(xs, [-s for s, _ in scored])  # CMA minimises
            i = max(range(len(scored)), key=lambda k: scored[k][0])
            if scored[i][0] > best[0]:
                best = (scored[i][0], cands[i])
            rec = {
                "gen": gen,
                "t_s": round(time.monotonic() - t_start),
                "gen_best": round(scored[i][0], 3),
                "best": round(best[0], 3),
                "gen_best_summary": summary(scored[i][1]),
            }
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(
                f"gen {gen:2d}  {rec['t_s']:5d} s  gen best {rec['gen_best']:7.3f}  "
                f"best {rec['best']:7.3f}  {rec['gen_best_summary']}",
                flush=True,
            )

        # Final report: defaults vs best, longer episodes, train and held-out rooms.
        rows = {}
        for label, params in (("defaults", defaults), ("tuned", best[1])):
            for split, rooms in (("train", TRAIN_ROOMS), ("held-out", HOLDOUT_ROOMS)):
                _, rs = evaluate(pool, [params], rooms, a.final)[0]
                rows[(label, split)] = summary(rs)
    changed = {k: (defaults[k], v) for k, v in best[1].items() if v != defaults[k]}
    (OUT / "best.json").write_text(
        json.dumps(
            {
                "params": best[1],
                "changed": changed,
                "train_score": best[0],
                "report": {f"{k[0]}/{k[1]}": v for k, v in rows.items()},
            },
            indent=1,
        )
        + "\n"
    )
    cols = [
        "score",
        "coverage_m2_per_min",
        "bumps_per_3min",
        "mcu_stops_per_3min",
        "touching",
        "stuck",
        "errors",
    ]
    md = [
        "# WANDER tuning — gentle first",
        "",
        f"{a.generations} generations × {a.popsize}, {a.episode:.0f} s training episodes on "
        f"{', '.join(TRAIN_ROOMS)} × yaw {YAWS}; report episodes {a.final:.0f} s. Held out: "
        f"{', '.join(HOLDOUT_ROOMS)}. Fast tier.",
        "",
        "| | split | " + " | ".join(cols) + " |",
        "|---|---|" + "---|" * len(cols),
    ]
    for (label, split), sm in rows.items():
        md.append(
            f"| {label} | {split} | " + " | ".join(str(sm[c]) for c in cols) + " |"
        )
    md += ["", "| tunable | default | tuned |", "|---|---|---|"]
    md += [f"| `wander.{k}` | {d} | **{v}** |" for k, (d, v) in changed.items()]
    (OUT / "report.md").write_text("\n".join(md) + "\n")
    print("\n" + "\n".join(md))


if __name__ == "__main__":
    main()
