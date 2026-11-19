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

from app.llm.games.checker import _CONFUSABLE, number_in, numbers_in, restated_sum

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


_DUNNO = re.compile(
    r"\b(?:don'?t know|don ?t know|do not know|no idea|not sure|dunno|i give up|help me|"
    r"pass)\b"
)
# "I said 90": the child disputes how their last answer was heard (Owen, 2026-11-18).
_DISPUTE = re.compile(
    r"\b(?:i said|i did say|i answered|that'?s what i said|i got it)\b"
)


def _restated_answer(it: Item, said: str) -> int | None:
    """The answer inside a sum said back: the one number that isn't the question's own.
    "3 plus 7" for "3 plus what makes 10?" is 7 (Owen, 2026-11-18: it was "unclear", never
    scored, so a 5/5 round was called 4/5); "8 plus 6 is 14" is 14; "is it 8 plus 6?" has
    none, nor does a different sum (asked again)."""
    given, left = numbers_in(it.ask), numbers_in(said)
    if not given or given[0] not in left:
        return None  # a different sum ("is it 8 plus 6?" for 12 - 6): not an answer
    for g in given:
        if g in left:
            left.remove(g)
    return left[0] if len(left) == 1 else None


def verdict(it: Item, said: str, *, asked_before: bool = False) -> str:
    """right | wrong | none (didn't know) | unclear (ask again: no clear number, a restated
    sum, "2 or 3", a teen/ty mix-up). ``asked_before``: this item was already asked again
    once, so an unclear answer now counts as none (no endless re-asking)."""
    low = (said or "").lower()
    if it.kind == "number":
        got = number_in(said, expect=int(it.answer))
        if got is None and restated_sum(said):
            got = _restated_answer(it, said)
        if got is None:
            return "none" if _DUNNO.search(low) or asked_before else "unclear"
        if str(got) == it.answer:
            return "right"
        if str(_CONFUSABLE.get(got)) == it.answer:
            return "wrong" if asked_before else "unclear"
        return "wrong"
    w = _words(said)
    if f" {it.answer} " in w or it.answer.replace(" ", "") in w.replace(" ", ""):
        return "right"
    if _DUNNO.search(w):
        return "none"
    return "wrong" if w.strip() else "none"


def replay(
    drill: Drill, pairs: list[tuple[str, str]], seed: int, grade: Grade
) -> tuple[dict[int, str], list[int]]:
    """Every item's verdict so far, oldest first (a re-asked item keeps its latest), and the
    item numbers asked. A dispute ("I said 90" when 90 was the last item's answer) marks
    the last item right and the current one "disputed" (asked again)."""
    verdicts: dict[int, str] = {}
    times: dict[int, int] = {}
    asked: list[int] = []
    for notes, said in pairs:
        m = _QNUM.search(notes)
        if not m:
            continue
        k = int(m.group(1))
        asked.append(k)
        times[k] = times.get(k, 0) + 1
        prev = k - 1
        if (
            prev in verdicts
            and prev // ROUND == k // ROUND
            and verdicts[prev] != "right"
            and _DISPUTE.search((said or "").lower())
        ):
            p_it = item(drill, seed, prev, _at(grade, prev))
            if p_it.kind == "number" and str(number_in(said)) == p_it.answer:
                verdicts[prev] = "right"
                verdicts[k] = "disputed"
                continue
        it = item(drill, seed, k, _at(grade, k))
        verdicts[k] = verdict(it, said, asked_before=times[k] > 1)
    return verdicts, asked


def status(drill: Drill, pairs: list[tuple[str, str]], seed: int, grade: Grade) -> str:
    """The ROUND lines for the card. ``pairs``: (reply notes, the child's next words) for
    every reply so far, oldest first; the last pair's words are being answered now."""
    tag = f"Game: {drill.game_id}"
    verdicts, asked = replay(drill, pairs, seed, grade)
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
    rnd, pos = divmod(n, ROUND)
    right = sum(1 for k, x in verdicts.items() if k // ROUND == rnd and x == "right")
    if v == "unclear":
        return (
            "ROUND (run by code; trust it): that wasn't a clear answer (it may have been"
            " misheard, or they said the sum back). Don't mark it, don't change the subject:"
            f' ask for just the number, e.g. "Just the number this time: {it.ask}" Notes:'
            f' "{tag}. Q#{n}".'
        )
    if v == "disputed":
        prev = item(drill, seed, n - 1, _at(grade, n - 1))
        return (
            f"ROUND (run by code; trust it): the child says they answered the last one with"
            f" {prev.answer}, and that was RIGHT ({prev.say_answer}): say sorry for mishearing"
            f" and count it. Score {right}/{pos}. Then ask the current one again, word for"
            f' word: "{it.ask}" Notes: "{tag}. Q#{n}".'
        )
    said_line = {
        "right": f"RIGHT ({it.say_answer}; their answer may have come through as a"
        " different word, but it was right). Cheer briefly.",
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


@dataclass(frozen=True, slots=True)
class Expected:
    """What the code will have asked by the end of this reply: ``item``, and ``left`` (the
    countdown word, e.g. "three") when it is a new item, None for a re-ask."""

    item: Item
    left: str | None


def expected(
    drill: Drill, pairs: list[tuple[str, str]], seed: int, grade: Grade, child: str = ""
) -> Expected | None:
    """The item this reply must end on, as ``status`` tells the model; None when no item is
    due (the round is over, or the child is leaving). Lets the server keep the model's own
    words from asking a different item or miscounting (``fix_sentence``)."""
    if ending(child):
        return None
    m = _QNUM.search(pairs[-1][0]) if pairs else None
    if m is None:
        verdicts, asked = replay(drill, pairs, seed, grade) if pairs else ({}, [])
        nxt = max(asked) + 1 if asked else 0
        nxt += (-nxt) % ROUND
        return Expected(item(drill, seed, nxt, _at(grade, nxt)), None)
    n = int(m.group(1))
    verdicts, _ = replay(drill, pairs, seed, grade)
    v = verdicts.get(n, "none")
    if v in ("unclear", "disputed"):
        return Expected(item(drill, seed, n, _at(grade, n)), None)
    pos = n % ROUND
    if pos == ROUND - 1:
        return None
    return Expected(
        item(drill, seed, n + 1, _at(grade, n + 1)), _COUNT[ROUND - pos - 2]
    )


_NUM_WORD = r"(?:one|two|three|four|five|\d)"
_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_SUM_ASK = re.compile(
    r"\b(?:plus|minus|times|divided|take away|makes)\b|\d\s*[-+x×*/÷]\s*\d"
)


def _countdown_re(drill: Drill) -> re.Pattern[str]:
    """ "{n} to blast-off!" -> matches "two to blast-off", "Two more to blast off"."""
    words = re.escape(drill.countdown.split("{n}")[1].strip(" !.")).replace(
        r"\-", "[- ]?"
    )
    words = words.replace(r"\ ", r"\s+")
    return re.compile(rf"\b({_NUM_WORD})(?=(?:\s+more)?\s+{words})", re.IGNORECASE)


def fix_sentence(drill: Drill, exp: Expected | None, text: str) -> str:
    """The model's words with what the code owns put right, before they are spoken: a sum
    asked that isn't the expected item is dropped (the server then says the right one), and
    a countdown says the true number left. Owen, 2026-11-18: "Next one: 5 plus 5? What is
    12 minus 5?" (two sums, the first made up) and "Two to blast-off!" three times running."""
    if exp is None or not text:
        return text
    want = sorted(re.findall(r"\d+", exp.item.ask))
    cd = _countdown_re(drill)
    out: list[str] = []
    for sent in _SPLIT.split(text.strip()):
        if (
            exp.item.kind == "number"
            and sent.rstrip().endswith("?")
            and _SUM_ASK.search(sent.lower())
            and re.findall(r"\d+", sent)
            and sorted(re.findall(r"\d+", sent)) != want
        ):
            continue
        if exp.left is not None:
            left = exp.left
            sent = cd.sub(
                lambda m: left.capitalize() if m.group(1)[0].isupper() else left, sent
            )
        out.append(sent)
    return " ".join(out)


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
        if got is None and restated_sum(said):
            got = _restated_answer(it, said)
        return "" if got is None else str(got)
    return it.answer if v == "right" else ""


def practice(
    drill: Drill, skill: str, pairs: list[tuple[str, str]], seed: int, grade: Grade
) -> dict[str, Any] | None:
    """The progress record for the child's last answer (the last pair's words answer the
    ``Q#<n>`` in that pair's notes); None if no item was asked, the answer is to be asked
    again, or the child left the game. A dispute re-scores the previous item (same key, so
    the robot replaces it). Checked by code (learning-games.md §2.1)."""
    if not skill or not pairs:
        return None
    notes, said = pairs[-1]
    m = re.search(rf"Game:\s*{drill.game_id}\b.*?\bQ#(\d+)", notes or "")
    if not m:
        return None
    n = int(m.group(1))
    verdicts, _ = replay(drill, pairs, seed, grade)
    v = verdicts.get(n, "none")
    if v == "disputed":
        n, v = n - 1, "right"
    elif v == "unclear" or (v != "right" and ending(said)):
        return None
    g = _at(grade, n)
    it = item(drill, seed, n, g)
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
        "answer": it.answer if v == "right" else _parsed(it, said, v),
        "verdict": v,
        "decided": "code",
        "source": "voice",
    }
