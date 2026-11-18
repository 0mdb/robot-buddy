"""Answers checked by code, not by the model (docs/learning-games.md §2.1).

Playtest 2026-11-18, before this existed: in Rocket Math the model told a child "You got
it!" for 5 + 4 = 13, 10 - 3 = 9 and 5 + 5 = 20. So the model writes each question in its
notes in a fixed form, and the server works out the answer, reads the number in the child's
words, and gives the model the verdict before it replies.
"""

from __future__ import annotations

import re

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_SCALES = {"hundred": 100, "thousand": 1000}
# Teen/ty pairs Whisper mixes up: an answer that is the other one of a pair is "unclear".
_CONFUSABLE = {13: 30, 14: 40, 15: 50, 16: 60, 17: 70, 18: 80, 19: 90}
_CONFUSABLE |= {v: k for k, v in _CONFUSABLE.items()}

_Q = re.compile(
    r"\bQ:\s*(\d+)\s*([-+x×*/÷])\s*(\d+|\?)\s*(?:=\s*(\d+))?", re.IGNORECASE
)
_SECRET = re.compile(r"\bSecret:\s*(\d[\d,]*)\b", re.IGNORECASE)


def number_in(text: str) -> int | None:
    """The number a child said, from digits or words ("forty-two", "a hundred and five").
    None when there is no number, or more than one."""
    t = (text or "").lower().replace(",", "")
    digits = re.findall(r"\b\d+\b", t)
    if digits:
        return int(digits[0]) if len(set(digits)) == 1 else None
    total, current, seen = 0, 0, False
    for w in re.findall(r"[a-z]+", t.replace("-", " ")):
        if w in _ONES:
            current += _ONES[w]
            seen = True
        elif w in _TENS:
            current += _TENS[w]
            seen = True
        elif w in _SCALES:
            current = max(current, 1) * _SCALES[w]
            if w == "thousand":
                total, current = total + current, 0
            seen = True
        elif w in ("and", "a") and seen:
            continue
        elif seen:
            break  # "seven, no wait eight" style corrections are left as the first number
    return total + current if seen else None


def _solve(a: int, op: str, b: str, c: str | None) -> int | None:
    op = {"x": "*", "×": "*", "÷": "/"}.get(op.lower(), op)
    if b == "?":  # missing number: a op ? = c
        if c is None:
            return None
        cv = int(c)
        if op == "+":
            return cv - a
        if op == "-":
            return a - cv
        if op == "*":
            return cv // a if a and cv % a == 0 else None
        return a // cv if cv and a % cv == 0 else None
    bv = int(b)
    if op == "+":
        return a + bv
    if op == "-":
        return a - bv
    if op == "*":
        return a * bv
    return a // bv if bv and a % bv == 0 else None


def check_math(last_notes: str, child_said: str) -> str | None:
    """A verdict line for the question in the last reply's notes (``Q: 7+8``), or None
    when there is no question in a form the code can check."""
    m = _Q.search(last_notes or "")
    if not m:
        return None
    a, op, b, c = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    answer = _solve(a, op, b, c)
    if answer is None:
        return None
    q = m.group(0)[2:].strip()
    said = number_in(child_said)
    if said is None:
        return (
            f"ANSWER CHECK (by code; trust it): {q}, answer {answer}. The child gave no"
            " clear number: if they don't know, give the answer with a trick and ask a NEW"
            " question; if it was unclear, ask them to say it again."
        )
    if said == answer:
        return (
            f"ANSWER CHECK (by code; trust it): {q}, answer {answer}. The child said {said}:"
            " RIGHT. Cheer briefly, then ask a NEW question."
        )
    if _CONFUSABLE.get(said) == answer:
        return (
            f"ANSWER CHECK (by code; trust it): {q}, answer {answer}. The child said {said},"
            f" which may be {answer} misheard: ask them to say it again, not wrong yet."
        )
    return (
        f"ANSWER CHECK (by code; trust it): {q}, answer {answer}. The child said {said}:"
        " WRONG. Say so kindly, give the answer and a quick trick, then ask a NEW question"
        " (do not repeat this one)."
    )


def check_guess(last_notes: str, child_said: str) -> str | None:
    """Higher/lower for Number Detective: the secret in notes vs the child's guess."""
    m = _SECRET.search(last_notes or "")
    said = number_in(child_said)
    if not m or said is None:
        return None
    secret = int(m.group(1).replace(",", ""))
    if said == secret:
        return f"GUESS CHECK (by code; trust it): the child guessed {said}: that IS the secret."
    way = "HIGHER" if secret > said else "LOWER"
    return (
        f"GUESS CHECK (by code; trust it): the child guessed {said}; the secret is {way}"
        f" than {said}. Never say the secret."
    )
