"""Stage 3: learn WANDER's motion as a small policy, in the fast tier (Vantage SIM-AUTONOMY.md).

CMA-ES over the weights of `policy.Mlp` (~270 parameters). The policy replaces `_patrol_drift`
and `_avoid_obstacle` only (learned.py); the OBSTACLE escape, the no-progress recovery, the
governor, and the MCU all stay. The other tunables are stage 2's tuned set, so the learner
competes with the best rule-based WANDER on equal terms.

Why evolution and not PPO: the objective is stage 2's, already validated on the full stack, and an
episode-level search optimises exactly that with no per-step reward to design. It reuses tune.py's
parallel machinery as is, and ~270 parameters is well inside CMA's range. Revisit if the policy
needs to grow past a few thousand parameters, or if vision joins the observations.

Domain randomisation (proposal 5, gap 1): each episode draws the sonar's specular-miss angle from
SPECULAR_RANGE. Every candidate in a generation sees the same draws (common random numbers), so a
generation's ranking stays exact; the draws change between generations. The best single sample is
then biased toward easy draws, so each generation also scores the distribution's mean, and the
result is the best-scoring mean.

  uv run python rl.py                                 # ~150 generations, ~3 h on 30 workers
  uv run python rl.py --generations 3 --popsize 6 --episode 30 --name smoke
  uv run python rl.py --name rl1 --resume             # continue from out/rl1/es.pkl

Output in out/<name>/: log.jsonl, policy.json (the best mean so far, every generation),
es.pkl (resume), report.md and best.json (rule-based tuned vs learned, train and held-out, at the
nominal sonar and at both ends of the randomised range).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

warnings.filterwarnings("ignore", message="Could not import matplotlib")
import cma  # noqa: E402

import episode  # noqa: E402
import learned  # noqa: E402
import policy  # noqa: E402
import tune  # noqa: E402  (objective, aggregation, rooms, spawns: stage 2's, unchanged)

SPECULAR_RANGE = (
    30.0,
    60.0,
)  # degrees; sim default 45, bench sweep pending (SIM.md finding 1)
SPECULAR_NOMINAL = 45.0
BASE_PARAMS = tune.OUT_ROOT / "tune2" / "best.json"

# (policy params or None for rule-based, tunables, room, spawn, seconds, specular deg)
Job = tuple[list[float] | None, dict[str, float], str, int, float, float]


def _run(job: Job) -> dict[str, Any]:
    flat, tunables, room, spawn, dur, spec = job
    if flat is None:
        r = episode.run_wander(
            room,
            0.0,
            dur,
            skill_params=tunables,
            spawn=spawn,
            sonar_specular_max_deg=spec,
        )
    else:
        skill = learned.LearnedSkillExecutor(
            policy.Mlp.from_flat(np.array(flat)), **tunables
        )
        r = episode.run_wander(
            room, 0.0, dur, skill=skill, spawn=spawn, sonar_specular_max_deg=spec
        )
    r["specular_deg"] = spec
    r["score"] = tune.episode_score(r)
    return r


def evaluate(
    pool: ProcessPoolExecutor,
    candidates: list[list[float] | None],
    tunables: dict[str, float],
    rooms: list[str],
    spawns: list[int],
    dur: float,
    speculars: list[float],
) -> list[tuple[float, list[dict[str, Any]]]]:
    """`speculars` has one entry per (room, spawn), shared by every candidate."""
    cells = [(room, k) for room in rooms for k in spawns]
    assert len(speculars) == len(cells)
    jobs: list[Job] = [
        (c, tunables, room, k, dur, spec)
        for c in candidates
        for (room, k), spec in zip(cells, speculars)
    ]
    results = list(pool.map(_run, jobs, chunksize=1))
    per = len(cells)
    return [
        (
            tune.aggregate([r["score"] for r in results[i * per : (i + 1) * per]]),
            results[i * per : (i + 1) * per],
        )
        for i in range(len(candidates))
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=150)
    ap.add_argument("--popsize", type=int, default=24)
    ap.add_argument("--sigma", type=float, default=0.3)
    ap.add_argument("--hidden", type=int, default=policy.N_HIDDEN)
    ap.add_argument("--episode", type=float, default=120.0)
    ap.add_argument("--final", type=float, default=180.0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--name", default="rl1")
    ap.add_argument("--base", type=Path, default=BASE_PARAMS, help="stage 2 best.json")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    out = tune.OUT_ROOT / a.name
    out.mkdir(parents=True, exist_ok=True)

    if not a.base.exists():
        raise SystemExit(
            f"{a.base} not found: run tune.py --name tune2 first (stage 2's set)"
        )
    tunables: dict[str, float] = json.loads(a.base.read_text())["params"]
    rng_master = np.random.default_rng(a.seed)
    n_cells = len(tune.TRAIN_ROOMS) * len(tune.TRAIN_SPAWNS)

    es_path = out / "es.pkl"
    if a.resume and es_path.exists():
        state = pickle.loads(es_path.read_bytes())
        es, gen0, best_mean, rng_master = (
            state["es"],
            state["gen"] + 1,
            state["best_mean"],
            state["rng"],
        )
        print(f"resumed at generation {gen0}, best mean {best_mean[0]:.3f}", flush=True)
    else:
        x0 = policy.initial(tunables["patrol_v_mm_s"], a.hidden)
        es = cma.CMAEvolutionStrategy(
            x0, a.sigma, {"popsize": a.popsize, "seed": a.seed, "verbose": -9}
        )
        gen0, best_mean = 0, (-math.inf, x0.tolist())
    log = (out / "log.jsonl").open("a" if a.resume else "w")
    t_start = time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        if gen0 == 0:
            nominal = [SPECULAR_NOMINAL] * n_cells
            s, rs = evaluate(
                pool,
                [None],
                tunables,
                tune.TRAIN_ROOMS,
                tune.TRAIN_SPAWNS,
                a.episode,
                nominal,
            )[0]
            print(
                f"rule-based ({a.base}): train {s:.3f}  {tune.summary(rs)}", flush=True
            )
        for gen in range(gen0, a.generations):
            spec = rng_master.uniform(*SPECULAR_RANGE, size=n_cells).round(1).tolist()
            xs = es.ask()
            cands = [list(map(float, x)) for x in xs] + [list(map(float, es.mean))]
            scored = evaluate(
                pool,
                cands,
                tunables,
                tune.TRAIN_ROOMS,
                tune.TRAIN_SPAWNS,
                a.episode,
                spec,
            )
            es.tell(xs, [-s for s, _ in scored[:-1]])  # CMA minimises
            mean_score, mean_rs = scored[-1]
            if mean_score > best_mean[0]:
                best_mean = (mean_score, cands[-1])
                policy.Mlp.from_flat(np.array(best_mean[1]), a.hidden).save(
                    out / "policy.json"
                )
            i = max(range(len(xs)), key=lambda k: scored[k][0])
            rec = {
                "gen": gen,
                "t_s": round(time.monotonic() - t_start),
                "sample_best": round(scored[i][0], 3),
                "mean": round(mean_score, 3),
                "best_mean": round(best_mean[0], 3),
                "sigma": round(float(es.sigma), 4),
                "mean_summary": tune.summary(mean_rs),
            }
            log.write(json.dumps(rec) + "\n")
            log.flush()
            es_path.write_bytes(
                pickle.dumps(
                    {"es": es, "gen": gen, "best_mean": best_mean, "rng": rng_master}
                )
            )
            print(
                f"gen {gen:3d}  {rec['t_s']:5d} s  sample best {rec['sample_best']:7.3f}  "
                f"mean {rec['mean']:7.3f}  best mean {rec['best_mean']:7.3f}  "
                f"sigma {rec['sigma']:.3f}  {rec['mean_summary']}",
                flush=True,
            )

        rows = report_rows(pool, tunables, best_mean[1], a.final)
    write_report(out, a, rows, best_mean[0])


def report_rows(
    pool: ProcessPoolExecutor, tunables: dict[str, float], flat: list[float], dur: float
) -> dict[tuple[str, str, float], dict[str, Any]]:
    rows = {}
    for spec in (SPECULAR_NOMINAL, SPECULAR_RANGE[0], SPECULAR_RANGE[1]):
        for split, rooms, spawns in (
            ("train", tune.TRAIN_ROOMS, tune.TRAIN_SPAWNS),
            ("held-out", tune.HOLDOUT_ROOMS, tune.HOLDOUT_SPAWNS),
        ):
            n = len(rooms) * len(spawns)
            both = evaluate(
                pool, [None, flat], tunables, rooms, spawns, dur, [spec] * n
            )
            for label, (_, rs) in zip(("rule-based", "learned"), both):
                rows[(label, split, spec)] = tune.summary(rs)
    return rows


def write_report(
    out: Path,
    a: argparse.Namespace,
    rows: dict[tuple[str, str, float], dict[str, Any]],
    best_train: float,
) -> None:
    cols = [
        "score",
        "coverage_m2_per_min",
        "bumps_per_3min",
        "repeat_bumps_per_3min",
        "mcu_stops_per_3min",
        "touching",
        "stuck",
        "speed_p95",
        "worst_bumps",
        "worst",
        "errors",
    ]
    md = [
        f"# WANDER stage 3 — learned policy ({a.name})",
        "",
        f"CMA-ES, {a.generations} generations × {a.popsize}, MLP {policy.N_OBS}-{a.hidden}-2, "
        f"{a.episode:.0f} s training episodes on {', '.join(tune.TRAIN_ROOMS)} × spawns "
        f"{tune.TRAIN_SPAWNS}, sonar specular angle drawn from {SPECULAR_RANGE}°. Report episodes "
        f"{a.final:.0f} s. Held out: {', '.join(tune.HOLDOUT_ROOMS)} × spawns "
        f"{tune.HOLDOUT_SPAWNS}. Rule-based = the tunables in `{a.base.name}` "
        f"({a.base.parent.name}/), which the learner also runs under. Fast tier.",
        "",
        "| | split | specular ° | " + " | ".join(cols) + " |",
        "|---|---|---|" + "---|" * len(cols),
    ]
    for (label, split, spec), sm in rows.items():
        md.append(
            f"| {label} | {split} | {spec:.0f} | "
            + " | ".join(str(sm[c]) for c in cols)
            + " |"
        )
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "best.json").write_text(
        json.dumps(
            {
                "best_mean_train_score": best_train,
                "report": {f"{k[0]}/{k[1]}/{k[2]:.0f}": v for k, v in rows.items()},
            },
            indent=1,
        )
        + "\n"
    )
    print("\n" + "\n".join(md))


if __name__ == "__main__":
    main()
