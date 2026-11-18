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


# Whisper hears a child's lone "three" as "free", "tree" or "sweet" (Rocket Math with Owen,
# 2026-11-18). Only used when the answer is short and has no real number in it.
_SOUNDS_LIKE = {"free": 3, "tree": 3, "sweet": 3}
_SHORT_WORDS = 4
_OPERATOR = re.compile(
    r"\b(?:plus|minus|times|divided|take away)\b|(?<=\d)\s*[-+x×*/÷]\s*(?=\d)"
)
_EITHER = re.compile(r"\bor\b")


def numbers_in(text: str) -> list[int]:
    """Every number said, in order, from digits or words. Repeats and corrections stay
    separate: "ninety, ninety" is [90, 90] (not 180), "ten... it's eleven" is [10, 11],
    "forty two" is [42], "a hundred and five" is [105]."""
    t = (text or "").lower().replace(",", " ")
    out: list[int] = []
    total = current = 0
    seen = False
    last = ""  # kind of the last word in the current number: ones, teen, tens, scale

    def flush() -> None:
        nonlocal total, current, seen, last
        if seen:
            out.append(total + current)
        total = current = 0
        seen, last = False, ""

    for tok in re.findall(r"\d+|[a-z]+", t.replace("-", " ")):
        if tok.isdigit():
            flush()
            out.append(int(tok))
            continue
        if tok in _ONES:
            v = _ONES[tok]
            kind = "teen" if v >= 10 else "ones"
            # a ones word joins a tens word ("forty two") or follows a scale ("hundred five")
            if (
                seen
                and not (kind == "ones" and last in ("tens", "scale"))
                and not (kind == "teen" and last == "scale")
            ):
                flush()
            current += v
            seen, last = True, kind
        elif tok in _TENS:
            if seen and last != "scale":
                flush()
            current += _TENS[tok]
            seen, last = True, "tens"
        elif tok in _SCALES:
            current = max(current, 1) * _SCALES[tok]
            if tok == "thousand":
                total, current = total + current, 0
            seen, last = True, "scale"
        elif tok in ("and", "a") and (seen or tok == "a"):
            continue
        else:
            flush()
    flush()
    return out


def number_in(text: str, *, expect: int | None = None) -> int | None:
    """The child's answer: the last number they said (so "ten... it's eleven" is 11). None
    when there is no number, or when they restated a sum ("is it 8 plus 6?") or gave two
    ("2 or 3"). A lone sound-alike in a short answer ("is it free?") counts only when it is
    ``expect``, the right answer: Whisper's mishearing may give credit, never take it."""
    if _OPERATOR.search((text or "").lower()):
        return None
    nums = numbers_in(text)
    if len(set(nums)) > 1 and _EITHER.search((text or "").lower()):
        return None  # "2 or 3": not an answer yet
    if nums:
        return nums[-1]
    words = re.findall(r"[a-z]+", (text or "").lower())
    if len(words) <= _SHORT_WORDS:
        alike = [_SOUNDS_LIKE[w] for w in words if w in _SOUNDS_LIKE]
        if len(alike) == 1 and expect is not None and alike[0] == expect:
            return alike[0]
    return None


def restated_sum(text: str) -> bool:
    """The child said a sum back ("is it 8 plus 6?") rather than an answer."""
    return bool(_OPERATOR.search((text or "").lower())) and bool(numbers_in(text))


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
