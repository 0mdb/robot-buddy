"""Sound Swap puzzles per grade for the drill engine (games/drill.py).

Whole words only (TTS can't be trusted with /sh/-style sounds, learning-games.md §6). The
younger levels name a sound by a cue word ("the sound at the start of horse") instead of a
letter name. Every answer is a real word.
"""

from __future__ import annotations

import random

from app.llm.games.drill import Drill, Item

# (word, cue word, answer): start the word with the cue word's first sound.
_FIRST = [
    ("cat", "horse", "hat"), ("cat", "ball", "bat"), ("sun", "ball", "bun"),
    ("pig", "dog", "dig"), ("pig", "water", "wig"), ("hop", "tiger", "top"),
    ("mat", "rabbit", "rat"), ("bed", "rabbit", "red"),
    ("fan", "cow", "can"), ("hen", "tiger", "ten"), ("bug", "rabbit", "rug"),
    ("map", "cow", "cap"), ("run", "fish", "fun"), ("big", "fish", "fig"),
    ("dot", "horse", "hot"), ("sit", "bear", "bit"), ("net", "jam", "jet"),
]  # fmt: skip
# (word, which, cue word, answer): change the middle or last sound to the cue's.
_INNER = [
    ("cat", "last", "pig", "cap"), ("pin", "middle", "hat", "pan"),
    ("hop", "last", "tiger", "hot"), ("bed", "middle", "hat", "bad"),
    ("sun", "middle", "hat", "san"), ("bus", "middle", "cat", "bas"),
    ("map", "last", "dog", "mad"), ("pig", "middle", "pot", "pog"),
    ("bag", "last", "tiger", "bat"), ("cup", "middle", "cat", "cap"),
    ("hit", "middle", "hat", "hat"), ("ten", "last", "dog", "ted"),
]  # fmt: skip
_INNER = [
    x for x in _INNER if x[3] in {"cap", "pan", "hot", "bad", "mad", "bat", "hat"}
]
# (word, letters to drop, answer)
_FIRST = [x for x in _FIRST if x[1] != x[2]]
_DROP = [
    ("star", "s", "tar"), ("spin", "s", "pin"), ("snap", "s", "nap"),
    ("stop", "t", "sop"), ("black", "l", "back"), ("clap", "l", "cap"),
    ("trip", "r", "tip"), ("slip", "l", "sip"), ("string", "r", "sting"),
    ("frog", "r", "fog"), ("plate", "l", "pate"), ("grow", "r", "go"),
]  # fmt: skip
_DROP = [x for x in _DROP if x[2] != "pate"]
# (word, from letters, to letters, answer)
_SWAP = [
    ("flip", "fl", "sh", "ship"), ("chop", "ch", "sh", "shop"), ("thin", "th", "sk", "skin"),
    ("crab", "cr", "gr", "grab"), ("block", "bl", "cl", "clock"), ("spot", "sp", "sh", "shot"),
    ("trap", "tr", "sn", "snap"), ("drum", "dr", "pl", "plum"), ("shell", "sh", "sm", "smell"),
]  # fmt: skip
# (word, s added at the start, answer)
_ADD = [
    ("nap", "snap"),
    ("top", "stop"),
    ("lip", "slip"),
    ("pot", "spot"),
    ("kit", "skit"),
]
_ADD = [x for x in _ADD if x[1] != "skit"]
# Grade 3: word parts. (spoken puzzle, answer)
_PARTS = [
    ("What word do you get when you put un in front of happy?", "unhappy"),
    ("What word do you get when you put re in front of play?", "replay"),
    ("What word do you get when you put dis in front of like?", "dislike"),
    ("What word do you get when you put un in front of tie?", "untie"),
    ("What word do you get when you put re in front of build?", "rebuild"),
    ("What do you call someone who teaches?", "teacher"),
    ("What do you call someone who paints?", "painter"),
    ("What do you call someone who sings?", "singer"),
    ("What do you call someone who acts in a play?", "actor"),
    ("What do you get when you add ly to quick?", "quickly"),
    ("What do you get when you add ly to slow?", "slowly"),
    ("What word means a market that is super big?", "supermarket"),
]


def make(rng: random.Random, grade: str) -> Item:
    if grade == "K":
        w, cue, ans = rng.choice(_FIRST)
        return Item(
            f"Say {w}. Now start it with the sound at the start of {cue}. What word is it?",
            ans,
            f"{w} becomes {ans}",
            kind="word",
        )
    if grade == "G1":
        if rng.random() < 0.5:
            w, cue, ans = rng.choice(_FIRST)
            return Item(
                f"Say {w}. Now start it with the sound at the start of {cue}. What word is it?",
                ans,
                f"{w} becomes {ans}",
                kind="word",
            )
        if rng.random() < 0.5:
            w, which, cue, ans = rng.choice(_INNER)
            spot = "at the end of" if which == "last" else "in the middle of"
            return Item(
                f"Say {w}. Now change the {which} sound to the sound {spot} {cue}."
                " What word is it?",
                ans,
                f"{w} becomes {ans}",
                kind="word",
            )
        w, drop, ans = rng.choice(_DROP[:4])
        return Item(
            f"Say {w} without the {drop}.",
            ans,
            f"{w} without the {drop} is {ans}",
            "word",
        )
    if grade == "G2":
        r = rng.random()
        if r < 0.45:
            w, drop, ans = rng.choice(_DROP)
            return Item(
                f"Say {w} without the {drop}.",
                ans,
                f"{w} without the {drop} is {ans}",
                "word",
            )
        if r < 0.8:
            w, a, b, ans = rng.choice(_SWAP)
            return Item(
                f"Say {w}. Now change the {a} to {b}. What word is it?",
                ans,
                f"{w} becomes {ans}",
                kind="word",
            )
        w, ans = rng.choice(_ADD)
        return Item(
            f"Add an s to the start of {w}. What word is it?",
            ans,
            f"it's {ans}",
            "word",
        )
    ask, ans = rng.choice(_PARTS)
    return Item(ask, ans, f"it's {ans}", kind="word")


DRILL = Drill(
    game_id="sound_swap",
    make=make,
    start="Five sound puzzles! First one:",
    countdown="{n} to go!",
    finish="cheer with the honest score, {right} out of {total}.",
)
