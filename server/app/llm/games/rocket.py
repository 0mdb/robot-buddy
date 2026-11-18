"""Rocket Math: sums per grade for the drill engine (games/drill.py)."""

from __future__ import annotations

import random

from app.llm.games.drill import Drill, Item
from app.llm.games.drill import item as _item
from app.llm.games.drill import status as _status


def _q(spoken: str, answer: int) -> Item:
    return Item(f"What is {spoken}?", str(answer), f"{spoken} is {answer}")


def make(rng: random.Random, grade: str) -> Item:
    kind = rng.random()
    if grade == "K":
        a, b = rng.randint(1, 5), rng.randint(0, 5)
        return _q(f"{a} plus {b}", a + b)
    if grade == "G1":
        if kind < 0.5:
            a, b = rng.randint(2, 10), rng.randint(1, 10)
            return _q(f"{a} plus {b}", a + b)
        a = rng.randint(6, 20)
        b = rng.randint(1, min(10, a))
        return _q(f"{a} minus {b}", a - b)
    if grade == "G2":
        if kind < 0.35:  # facts with addends to 10
            a, b = rng.randint(3, 10), rng.randint(3, 10)
            return _q(f"{a} plus {b}", a + b)
        if kind < 0.6:  # related subtraction
            a, b = rng.randint(3, 10), rng.randint(3, 10)
            return _q(f"{a + b} minus {b}", a)
        if kind < 0.8:  # tens within 100
            a = rng.randint(1, 8) * 10
            b = rng.randint(1, (100 - a) // 10) * 10
            return _q(f"{a} plus {b}", a + b)
        a, b = rng.randint(2, 9), rng.randint(2, 9)  # missing number
        return Item(
            f"{a} plus what makes {a + b}?", str(b), f"{a} plus {b} makes {a + b}"
        )
    if kind < 0.6:  # G3
        a, b = rng.randint(2, 10), rng.randint(2, 10)
        return _q(f"{a} times {b}", a * b)
    if kind < 0.8:
        a, b = rng.randint(2, 10), rng.randint(2, 10)
        return _q(f"{a * b} divided by {a}", b)
    a = rng.randint(1, 6) * 50
    b = rng.randint(1, 6) * 10
    return _q(f"{a} plus {b}", a + b)


DRILL = Drill(
    game_id="rocket_math",
    make=make,
    start="Five questions to blast-off! First one:",
    countdown="{n} to blast-off!",
    finish="BLAST OFF with the excited emotion and the honest score, {right} out of {total}.",
)


def question(seed: int, n: int, grade: str) -> Item:
    return _item(DRILL, seed, n, grade)


def status(pairs: list[tuple[str, str]], seed: int, grade: str) -> str:
    return _status(DRILL, pairs, seed, grade)
