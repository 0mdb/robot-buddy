"""Stage 3's learned WANDER policy: a small MLP in numpy, from what the robot senses to a twist.

Vantage SIM-AUTONOMY.md, proposal 4. Pure numpy, no training framework, so the same file can run
on the Pi 5 at 50 Hz. Observation scales are fixed constants, not learned statistics, so the robot
computes exactly what training saw.

Observations are only what the robot has (rule 1 in README.md): sonar range and its status, wheel
speeds, gyro yaw rate, the governor's capped command from the last tick, the policy's own last
action, and a slow clock phase. Sim truth never enters. No camera (decision F).

The policy acts where `_patrol_drift` and `_avoid_obstacle` do, below the OBSTACLE escape and the
no-progress recovery, and always under `apply_safety()` (learned.py). Its output is a request the
governor may scale or zero, exactly like every other twist source.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# RangeStatus values (supervisor/devices/protocol.py); copied as ints so this file has no
# supervisor import and can be lifted onto the robot as-is.
RANGE_OK = 0

RANGE_SCALE_MM = 2000.0  # 1.0 = 2 m
RANGE_FAR = (
    1.5  # what a non-OK reading encodes as: "nothing seen" (timeout, out of range)
)
HISTORY_TICKS = (0, 5, 10, 20)  # current, 0.1, 0.2, 0.4 s ago at 50 Hz
SPEED_SCALE = 300.0  # mm/s
RATE_SCALE = 2000.0  # mrad/s, the governor's yaw-rate cap
CLOCK_PERIOD_S = 10.0  # a slow phase the policy may use to vary its path, as _patrol_drift's flip does

# Action range. The governor still applies its caps on top; these only bound what is asked for.
V_MIN, V_MAX = -150.0, 300.0
W_MAX = 1500.0

N_OBS = (
    len(HISTORY_TICKS) + 1 + 2 + 1 + 2 + 2 + 2
)  # ranges, ok, wheels, gyro, capped, last, clock
N_HIDDEN = 16
N_ACT = 2


def n_params(n_hidden: int = N_HIDDEN) -> int:
    return N_OBS * n_hidden + n_hidden + n_hidden * N_ACT + N_ACT


@dataclass(slots=True)
class Mlp:
    """obs -> tanh hidden -> tanh out -> (v_mm_s, w_mrad_s)."""

    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray

    @classmethod
    def from_flat(cls, x: np.ndarray, n_hidden: int = N_HIDDEN) -> Mlp:
        x = np.asarray(x, dtype=np.float64)
        if x.size != n_params(n_hidden):
            raise ValueError(f"expected {n_params(n_hidden)} params, got {x.size}")
        i = 0

        def take(n: int, shape: tuple[int, ...]) -> np.ndarray:
            nonlocal i
            out = x[i : i + n].reshape(shape)
            i += n
            return out

        return cls(
            w1=take(N_OBS * n_hidden, (n_hidden, N_OBS)),
            b1=take(n_hidden, (n_hidden,)),
            w2=take(n_hidden * N_ACT, (N_ACT, n_hidden)),
            b2=take(N_ACT, (N_ACT,)),
        )

    def flat(self) -> np.ndarray:
        return np.concatenate([self.w1.ravel(), self.b1, self.w2.ravel(), self.b2])

    def act(self, obs: np.ndarray) -> np.ndarray:
        """Normalised action in [-1, 1]²."""
        return np.tanh(self.w2 @ np.tanh(self.w1 @ obs + self.b1) + self.b2)

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({"n_hidden": int(self.b1.size), "params": self.flat().tolist()})
            + "\n"
        )

    @classmethod
    def load(cls, path: Path) -> Mlp:
        d = json.loads(path.read_text())
        return cls.from_flat(np.array(d["params"]), int(d["n_hidden"]))


def to_twist(a: np.ndarray) -> tuple[int, int]:
    v = V_MIN + (float(a[0]) + 1.0) * 0.5 * (V_MAX - V_MIN)
    return int(round(v)), int(round(float(a[1]) * W_MAX))


def from_twist(v_mm_s: float, w_mrad_s: float) -> np.ndarray:
    a0 = 2.0 * (v_mm_s - V_MIN) / (V_MAX - V_MIN) - 1.0
    return np.array([a0, w_mrad_s / W_MAX])


def initial(patrol_v_mm_s: float, n_hidden: int = N_HIDDEN) -> np.ndarray:
    """All weights zero, output bias set so the untrained policy drives straight at the patrol
    speed. A search starting from 'stand still' would spend its first generations on the coverage
    floor alone."""
    m = Mlp.from_flat(np.zeros(n_params(n_hidden)), n_hidden)
    a = np.clip(from_twist(patrol_v_mm_s, 0.0), -0.999, 0.999)
    m.b2[:] = np.arctanh(a)
    return m.flat()


@dataclass(slots=True)
class ObsBuilder:
    """Turns successive robot readings into the observation vector. One per robot; call once per
    tick, in order. Holds the range history and the last action."""

    history: list[float] = field(default_factory=list)
    last: np.ndarray = field(default_factory=lambda: np.zeros(N_ACT))

    def build(
        self,
        *,
        range_mm: int,
        range_status: int,
        speed_l_mm_s: int,
        speed_r_mm_s: int,
        gyro_z_mrad_s: int,
        capped_v_mm_s: int,
        capped_w_mrad_s: int,
        tick_mono_ms: float,
    ) -> np.ndarray:
        ok = range_status == RANGE_OK and range_mm > 0
        r = min(RANGE_FAR, range_mm / RANGE_SCALE_MM) if ok else RANGE_FAR
        self.history.insert(0, r)
        del self.history[HISTORY_TICKS[-1] + 1 :]
        ranges = [self.history[min(k, len(self.history) - 1)] for k in HISTORY_TICKS]
        phase = 2.0 * math.pi * (tick_mono_ms / 1000.0) / CLOCK_PERIOD_S
        return np.array(
            [
                *ranges,
                1.0 if ok else 0.0,
                speed_l_mm_s / SPEED_SCALE,
                speed_r_mm_s / SPEED_SCALE,
                gyro_z_mrad_s / RATE_SCALE,
                capped_v_mm_s / SPEED_SCALE,
                capped_w_mrad_s / RATE_SCALE,
                *self.last,
                math.sin(phase),
                math.cos(phase),
            ]
        )
