"""Drill rounds run by code: the server picks each item, checks the answer, keeps the score.

Shared by Rocket Math and Sound Swap (docs/learning-games.md §2.1). Playtests 2026-11-18:
left to the model, wrong answers were called right (5 + 4 = 13 "You got it!"; "hat" for a
ball-to-tall swap), and items planned in the notes went unsaid because the model writes its
words before its notes. Now the model gets the verdict, the score and the exact next item;
it adds the voice and copies "Q#<n>" into its notes.

Everything is derived from the conversation each turn (no mutable state), so a speculative
turn that is rolled back can't skew the score.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from typing import Any
from dataclasses import dataclass

from app.llm.games.checker import _CONFUSABLE, number_in

ROUND = 5
# A grade, or the grade for a round number: a round keeps the grade it started with, so a
# step change (progress, learning-games.md §2) or a new speaker can't swap items mid-round.
Grade = str | Callable[[int], str]
_QNUM = re.compile(r"\bQ#(\d+)\b")
_COUNT = ("one", "two", "three", "four")


@dataclass(frozen=True, slots=True)
class Item:
    ask: str  # said word for word: "What is 7 plus 8?"
    answer: str  # "15" or "hat"
    say_answer: str  # "7 plus 8 is 15", "the word is hat"
    kind: str = "number"  # "number" | "word"


@dataclass(frozen=True, slots=True)
class Drill:
    game_id: str
    make: Callable[[random.Random, str], Item]
    start: str  # what to say before item 1 (e.g. "Five questions to blast-off!")
    countdown: str  # "{n} to blast-off!"
    finish: str  # the end-of-round instruction, with {right} and {total}


def item(drill: Drill, seed: int, n: int, grade: str) -> Item:
    """Item number ``n`` (0-based) of this conversation; a round's items are distinct."""
    rnd, pos = divmod(n, ROUND)
    rng = random.Random(f"{drill.game_id}:{seed}:{rnd}:{grade}")
    picked: list[Item] = []
    for _ in range(200):
        it = drill.make(rng, grade)
        if all(it.ask != p.ask for p in picked):
            picked.append(it)
        if len(picked) == ROUND:
            break
    while len(picked) < ROUND:  # tiny tables: allow repeats rather than fail
        picked.append(drill.make(rng, grade))
    return picked[pos]


def _at(grade: Grade, n: int) -> str:
    """The grade for item ``n``."""
    return grade(n // ROUND) if callable(grade) else grade


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z ]+", " ", (text or "").lower()) + " "


def verdict(it: Item, said: str) -> str:
    """right | wrong | none (no answer) | unclear (teen/ty mix-up)."""
    if it.kind == "number":
        got = number_in(said)
        if got is None:
            return "none"
        if str(got) == it.answer:
            return "right"
        return "unclear" if str(_CONFUSABLE.get(got)) == it.answer else "wrong"
    w = _words(said)
    if f" {it.answer} " in w or it.answer.replace(" ", "") in w.replace(" ", ""):
        return "right"
    if re.search(r"\b(don ?t know|no idea|not sure|dunno|i give up|help)\b", w):
        return "none"
    return "wrong" if w.strip() else "none"


def status(drill: Drill, pairs: list[tuple[str, str]], seed: int, grade: Grade) -> str:
    """The ROUND lines for the card. ``pairs``: (reply notes, the child's next words) for
    every reply so far, oldest first; the last pair's words are being answered now."""
    tag = f"Game: {drill.game_id}"
    verdicts: dict[int, str] = {}
    asked: list[int] = []
    for notes, said in pairs:
        m = _QNUM.search(notes)
        if m:
            k = int(m.group(1))
            asked.append(k)
            verdicts[k] = verdict(item(drill, seed, k, _at(grade, k)), said)
    m = _QNUM.search(pairs[-1][0]) if pairs else None
    if m is None:  # starting, or a new round after a finished one
        nxt = max(asked) + 1 if asked else 0
        nxt += (-nxt) % ROUND
        it = item(drill, seed, nxt, _at(grade, nxt))
        return (
            f"ROUND (run by code; trust it): a new round of {ROUND}. One short excited"
            f' sentence, then end your reply with exactly: "{drill.start} {it.ask}" Notes:'
            f' "{tag}. Q#{nxt}".'
        )
    n = int(m.group(1))
    it = item(drill, seed, n, _at(grade, n))
    v = verdicts.get(n, "none")
    if v == "unclear":
        return (
            f"ROUND (run by code; trust it): the answer sounded unclear (maybe {it.answer}"
            f' misheard). Ask them to say it again: "{it.ask}" Notes: "{tag}. Q#{n}".'
        )
    rnd, pos = divmod(n, ROUND)
    right = sum(1 for k, x in verdicts.items() if k // ROUND == rnd and x == "right")
    said_line = {
        "right": f"RIGHT ({it.say_answer}). Cheer briefly.",
        "wrong": f'WRONG. Start with "Not quite, {it.say_answer}."',
        "none": f'no answer. Say kindly "{it.say_answer}."',
    }[v]
    head = f"ROUND (run by code; trust it): last answer {said_line} Score {right}/{pos + 1}."
    if pos == ROUND - 1:
        return (
            f"{head} That was the last one: say whether it was right, then "
            + drill.finish.format(right=right, total=ROUND)
            + f' Offer another round. Notes: "{tag}. Round over" (no Q#).'
        )
    nxt = item(drill, seed, n + 1, _at(grade, n + 1))
    count = drill.countdown.format(n=_COUNT[ROUND - pos - 2])
    return (
        f'{head} Then say "{count}" and end with the next one, word for word: "{nxt.ask}"'
        f' Notes: "{tag}. Q#{n + 1}". But if the child said goodbye or wants to stop, stop'
        f' instead: no question, and notes "{tag}. Stopped" (no Q#).'
    )


# The child or the reply ends the game: never add a question after it (playtest 2026-11-18:
# "goodbye" mid-round, she said goodbye, then the server asked the next sum).
_ENDING = re.compile(
    r"\b(good ?bye|bye|see (?:you|ya)|good ?night|stop|i ?(?:am|'m) done|no more|"
    r"that'?s enough|something else|play (?:something|another)|later)\b",
    re.IGNORECASE,
)


def ending(text: str) -> bool:
    """Words that end the game (goodbye, stop, something else)."""
    return bool(_ENDING.search(text or ""))


def tail(
    drill: Drill, notes: str, text: str, seed: int, grade: Grade, child: str = ""
) -> str | None:
    """The item the notes say was asked when the words didn't ask it, to be spoken. Never
    when the child's words (``child``) or the reply end the game."""
    if ending(child) or ending(text):
        return None
    m = re.search(rf"Game:\s*{drill.game_id}\b.*?\bQ#(\d+)", notes or "")
    if not m:
        return None
    n = int(m.group(1))
    it = item(drill, seed, n, _at(grade, n))
    if it.kind == "number":
        said = re.findall(r"\d+", text or "")
        if all(x in said for x in re.findall(r"\d+", it.ask)):
            return None
    elif _words(it.ask).strip()[:24] in _words(text):
        return None
    return it.ask


def _parsed(it: Item, said: str, v: str) -> str:
    if it.kind == "number":
        got = number_in(said)
        return "" if got is None else str(got)
    return it.answer if v == "right" else ""


def practice(
    drill: Drill, skill: str, notes: str, said: str, seed: int, grade: Grade
) -> dict[str, Any] | None:
    """The progress record for the item the last reply asked (``Q#<n>`` in its notes),
    answered by ``said``; None if no item was asked or the answer was unclear (a teen/ty
    mix-up is asked again and never counted). Checked by code (learning-games.md §2.1)."""
    m = re.search(rf"Game:\s*{drill.game_id}\b.*?\bQ#(\d+)", notes or "")
    if not m or not skill:
        return None
    n = int(m.group(1))
    g = _at(grade, n)
    it = item(drill, seed, n, g)
    v = verdict(it, said)
    if v == "unclear" or (v != "right" and ending(said)):
        return None  # asked again, or the child left the game: not a miss
    return {
        "key": f"{seed}:{drill.game_id}:{n}",
        "q": n,
        "game": drill.game_id,
        "skill": skill,
        "step": g,
        "item": it.ask,
        "expected": it.answer,
        # What the child answered, as parsed: a number, or the right word. Never their raw
        # words: the progress file is always on, and transcripts belong only in the opt-in
        # conversation history (PE spec S2 §8.5).
        "answer": _parsed(it, said, v),
        "verdict": v,
        "decided": "code",
        "source": "voice",
    }
