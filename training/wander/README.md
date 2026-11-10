# training/wander — developing WANDER in simulation

Buddy's own behaviour, developed against Vantage's MuJoCo model of the house. The design and the
decisions behind it are in `~/vantage/docs/SIM-AUTONOMY.md`. This directory is decision D:
robot-buddy owns the env, the reward, and anything learned. Vantage owns the world.

## Two tiers

| | Full tier | Fast tier (here) |
|---|---|---|
| Runs | `~/vantage/sim/buddy_sim.py --supervisor` | `fast_env.FastBuddy` |
| Supervisor | this repo's, as its own process, unmodified | this repo's `TickLoop._tick()`, imported |
| Serial | PTY, real COBS bytes | in-memory pipe, the same bytes and both sides' real codecs |
| Clock | wall, 1× | virtual: ~29× per core bare, ~12× with scoring |
| Workers, HTTP, Vantage | yes | no |
| Use | proof before anything deploys | tuning and training |

`agreement.py` is the gate between them. It runs the same episode in both tiers and fails if
they disagree. Run it after any change to `fast_env.py`, Vantage's `reflex_emu.py`, or the tick
loop.

## Setup

```bash
cd ~/vantage/sim && uv venv .venv -p 3.12 && uv pip install -p .venv mujoco numpy pillow shapely mapbox-earcut
cd ~/vantage/sim && .venv/bin/python export_house.py          # the house, into ~/.cache/vantage-sim/house
cd ~/robot-buddy/training/wander && uv sync --group dev
```

`VANTAGE_SIM` overrides where the world is imported from (default `~/vantage/sim`).

## Use

```bash
uv run pytest -q test_fast_env.py                         # fast tier reproduces sim-check's numbers
uv run python episode.py --rooms office hallway --duration 180
uv run python agreement.py                                # needs the full tier's ports free
cd ~/vantage/sim && .venv/bin/python wander_baseline.py   # full-tier WANDER baseline, ~25 min
```

## What the fast tier reproduces (office, facing the wall; full tier = Vantage `just sim-check`)

| | Full tier | Fast tier |
|---|---|---|
| Client silent → robot stopped, from ~250 mm/s | 810, 814 ms | 780 ms |
| Governor caps, approaching the wall | range < 500 then < 300 | same |
| MCU obstacle latch / at rest | — / 212–215 mm | 247 / 214 mm |

## Rules

- **Observations are only what the robot has.** Sim truth is for scoring, never an input.
- **The governor stays in the loop.** Never raise a threshold for the learner's sake.
- **Sim tunables never reach a manifest or `config.h`** (Vantage `SIM.md` rule 3).
- Nothing here changes robot behaviour. A result becomes a robot change only through a
  normal commit to `supervisor/`, after the full tier and a bench trial.
