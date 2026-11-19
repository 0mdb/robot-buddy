"""The Guessing Game, kept straight by code: who picked, the secret, and whether a guess hit.

Playtest 2026-11-18 (Owen, Clark): left to the model's own notes, the roles and the secret
drifted ("Turn" meant who picked one turn and whose go the next; the secret went kite,
flamingo, squirrel in one round), "Oh, I got it" was congratulated with no guess said,
Buddy guessed its own secret (guitar) in Clark's round, and "bus" heard as "boss" was
argued with three times until Owen spelled it. Now the code decides the picker and the
secret, checks each guess against it, and gives the model one GUESS line to follow; the
model keeps the fun and the yes/no answers.

The state lives in the reply notes in a fixed form the code dictates and reads back:
``Game: guess. Picker: buddy. Secret: bus`` / ``Game: guess. Picker: child`` /
``Game: guess. Round over. Picker: buddy``. Nothing else is stored, so a rolled-back
speculative turn can't skew it.
"""

from __future__ import annotations

import re

TAG = "Game: guess"
_PICKER = re.compile(r"\bPicker:\s*(buddy|child)\b", re.IGNORECASE)
_SECRET = re.compile(r"\bSecret:\s*([a-z][a-z' -]*?)\s*(?:[.;,(]|$)", re.IGNORECASE)
_OVER = re.compile(r"\bRound over\b", re.IGNORECASE)
_KIND = re.compile(r"\b(animal|food|thing)s?\b", re.IGNORECASE)

# Who picks the next secret, from the child's words.
_CHILD_PICKS = re.compile(
    r"\b(?:you guess|now you guess|your turn to guess|guess (?:mine|my)|i'?ll pick|"
    r"i(?:'?m| am) thinking of|i have (?:one|something)|let me pick|i pick)\b",
    re.IGNORECASE,
)
_BUDDY_PICKS = re.compile(
    r"\b(?:i guess|i'?ll guess|i get to guess|my turn to guess|let me guess|you pick|"
    r"you think of|your secret|pick (?:one|something|a secret))\b",
    re.IGNORECASE,
)
# A win claimed without saying the guess.
_CLAIM = re.compile(
    r"\b(?:i got it|i know what it is|i know it|i won|i win|i guessed it|i figured it out|"
    r"i know the answer|you guessed it)\b",
    re.IGNORECASE,
)
_GIVE_UP = re.compile(
    r"\b(?:i give up|tell me (?:what it is|the answer|the secret)|i don'?t know what it is)\b",
    re.IGNORECASE,
)
_YES = re.compile(
    r"(?:oh,? )?(?:yes|yeah|yep|yup|uh[- ]huh|i did|that'?s (?:it|right))\b", re.I
)
_HINT_AFTER = 8


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def _skeleton(word: str) -> str:
    """First letter + the consonants after it, doubles collapsed: "bus" and "boss" are "bs"."""
    w = word.lower()
    cons = re.sub(r"[aeiouy]", "", w[1:])
    return re.sub(r"(.)\1+", r"\1", w[0] + cons)


def _unspell(words: list[str]) -> list[str]:
    """Spelled letters joined: "B-U-S" (b u s) is "bus" (Owen spelled it, 2026-11-18)."""
    out: list[str] = []
    run = ""
    for w in words + [""]:
        if len(w) == 1:
            run += w
            continue
        if run:
            out.append(run)
        run = ""
        if w:
            out.append(w)
    return out


def named(secret: str, said: str) -> bool:
    """The child's words name the secret (or its plural), or spell it."""
    w = " " + " ".join(_unspell(_words(said))) + " "
    s = " ".join(_words(secret))
    return any(f" {s}{end} " in w for end in ("", "s", "es"))


def sounds_like(secret: str, said: str) -> str | None:
    """A word that may be the secret misheard ("boss" for "bus"): same first letter and
    consonants, only the vowels differ. One-word secrets of 3+ letters only."""
    sw = _words(secret)
    if len(sw) != 1 or len(sw[0]) < 3:
        return None
    target = _skeleton(sw[0])
    for w in _words(said):
        if len(w) >= 3 and w != sw[0] and _skeleton(w) == target:
            return w
    return None


def _state(notes: str) -> tuple[str | None, str | None, bool]:
    """(picker, secret, round_over) from a reply's notes; picker None when not in the game."""
    if TAG.lower() not in (notes or "").lower():
        return None, None, False
    p = _PICKER.search(notes)
    s = _SECRET.search(notes)
    secret = s.group(1).strip().lower() if s else None
    if secret in ("none", "no", "waiting", "unknown"):
        secret = None
    return (
        p.group(1).lower() if p else None,
        secret,
        bool(_OVER.search(notes)),
    )


def _questions_so_far(pairs: list[tuple[str, str]], secret: str) -> int:
    """Replies in a row (newest back) holding this secret: the child's questions so far."""
    n = 0
    for notes, _ in reversed(pairs):
        picker, s, over = _state(notes)
        if picker != "buddy" or s != secret or over:
            break
        n += 1
    return n


def status(pairs: list[tuple[str, str]], picks: dict[str, str], child: str = "") -> str:
    """The GUESS line for this turn. ``pairs``: (reply notes, the child's next words) for each
    reply so far, oldest first (the last pair's words are being answered now). ``picks``:
    the GAME PICKS secret per kind, for a new round Buddy picks."""
    notes = pairs[-1][0] if pairs else ""
    said = child or (pairs[-1][1] if pairs else "")
    picker, secret, over = _state(notes)

    if picker == "buddy" and secret and not over:
        # "yes" to "Did you say <secret>?" (asked because their last words sounded like it)
        confirmed = (
            len(pairs) >= 2
            and sounds_like(secret, pairs[-2][1]) is not None
            and _YES.match(said.strip()) is not None
        )
        if named(secret, said) or confirmed:
            return (
                f'GUESS (run by code; trust it): they guessed it, the secret was "{secret}".'
                " Cheer, say what it was, and offer another round (they pick next, unless"
                f' they want you to). Notes exactly: "{TAG}. Round over. Picker: buddy".'
            )
        heard = sounds_like(secret, said)
        if heard:
            return (
                f'GUESS (run by code; trust it): the speech came through as "{heard}", which'
                f' may be "{secret}" misheard. Ask "Did you say {secret}?" and if they say'
                f' yes, they guessed it. Notes exactly: "{TAG}. Picker: buddy. Secret:'
                f' {secret}" then your answers so far.'
            )
        if _GIVE_UP.search(said):
            return (
                f'GUESS (run by code; trust it): they give up. Say it kindly: it was "{secret}",'
                " with one fun fact or the clue that would have got it. Offer another round."
                f' Notes exactly: "{TAG}. Round over. Picker: buddy".'
            )
        if _CLAIM.search(said):
            return (
                "GUESS (run by code; trust it): they say they know it but haven't said what"
                " it is. Don't say they won: ask them to say their guess out loud. Notes"
                f' exactly: "{TAG}. Picker: buddy. Secret: {secret}" then your answers so far.'
            )
        n = _questions_so_far(pairs, secret)
        hint = (
            f" They've asked {n} questions: offer a small hint."
            if n >= _HINT_AFTER
            else ""
        )
        return (
            f'GUESS (run by code; trust it): YOU picked the secret, "{secret}"; the child is'
            " guessing. Answer their yes/no question truthfully about it (start Yes! or"
            " No!); a thing they name that isn't it is a No. Never guess yourself and never"
            " say it or give away more than they asked."
            + hint
            + f' Notes exactly: "{TAG}. Picker: buddy. Secret: {secret}" then your answers'
            " so far."
        )

    if picker == "child" and not over:
        return (
            "GUESS (run by code; trust it): the CHILD picked the secret; YOU are guessing."
            " You have no secret of your own: never say you picked one or are thinking of"
            " one. If they say your last guess was right, cheer and offer another round"
            f' (notes "{TAG}. Round over. Picker: child"). Otherwise ask ONE yes/no question'
            " or make a guess from their answers so far (if they aren't ready yet, say"
            f' "Tell me when you\'re ready!"). Notes exactly: "{TAG}. Picker: child" then'
            " their answers so far."
        )

    # A new round: who picks?
    if _CHILD_PICKS.search(said):
        new = "child"
    elif _BUDDY_PICKS.search(said):
        new = "buddy"
    elif picker in ("buddy", "child"):  # after a round: swap
        new = "child" if picker == "buddy" else "buddy"
    else:
        new = "buddy"
    if new == "child":
        return (
            "GUESS (run by code; trust it): a new round; the CHILD picks a secret and YOU"
            " guess. Don't pick one yourself. If they're ready, ask your first yes/no"
            ' question (start broad: "Is it an animal?"); if not, say "Tell me when you\'re'
            f' ready!". Notes exactly: "{TAG}. Picker: child".'
        )
    m = _KIND.search(said)
    kind = m.group(1).lower() if m else "animal"
    secret = picks.get(kind) or next(iter(picks.values()), "cat")
    return (
        f'GUESS (run by code; trust it): a new round; YOU pick, and your secret is "{secret}"'
        f" (a {kind}). Say you've got one, it's {'an' if kind == 'animal' else 'a'} {kind},"
        " and invite their first yes/no question. Never say it. Notes exactly:"
        f' "{TAG}. Picker: buddy. Secret: {secret}".'
    )
