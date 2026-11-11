"""Deterministic safety cues in what the child said.

The conversation model is small, and the SAFETY section of its prompt alone was followed about
half the time: a sad, scared, or endangered child was often met with a curious question and no
grown-up (~/vantage/docs/SIM-INTERACTION.md, stage 1 baseline, findings B1-B6). A targeted note
naming the cue, placed right before the child's message, is followed far more reliably than a
general rule.

This is a hint to the model, not a filter and not a classifier of record. It errs towards
firing: a false positive costs one gentle "tell a grown-up"; a miss can cost much more. The L1
suite measures it against hand-labelled turns, never against these patterns.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_SECRET = "keeping a secret from grown-ups"
# Operator, 2026-11-10: mild grief needs a grown-up every time (SIM-INTERACTION stage 1's open
# policy question). A child's follow-up rarely names the death again ("I keep thinking about
# him", "is he coming back tomorrow"), so this cue carries over from recent turns.
_GRIEF = "someone or a pet dying"
_STICKY = (_GRIEF,)
STICKY_TURNS = 3
# "I died in Minecraft" is not grief. Games only; anything else errs towards firing.
_GAME = re.compile(
    r"\b(games?|minecraft|roblox|fortnite|mario|level|respawn\w*|extra lives?|zombies?|"
    r"my character|video ?game)\b",
    re.IGNORECASE,
)

_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "a stranger or someone they don't know well",
        re.compile(
            r"\b(stranger|a (man|lady|woman|guy|person|grown-?up|kid) (at|in|on|from|said|asked|"
            r"wants?|told|offered|gave)|someone i don'?t know|next door|neighbou?r|"
            r"in (his|her|their|a) (car|van|truck|house)|come (with|in|see|to)|get in|"
            r"meet (up|me)|wants? to meet)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "sharing private things online",
        re.compile(
            r"\b(online|in the game|on the game|on the internet|app|chat)\b.*\b(where i live|"
            r"address|school|phone|picture|photo|meet|password|real name)\b|"
            r"\b(where i live|my address|what school)\b",
            re.IGNORECASE,
        ),
    ),
    (
        _SECRET,
        re.compile(
            r"\b(secret|don'?t tell|not to tell|won'?t tell|if i tell|can'?t tell|hid|hide|"
            r"hiding|nobody knows)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "something dangerous",
        re.compile(
            r"\b(pills?|medicine|tablets?|vitamins?|matches|match|lighter|fire|stove|oven|"
            r"knife|knives|sharp|outlet|plug|socket|gun|bleach|soap|cleaner|chemical|"
            r"under the sink|smells? (funny|weird|bad)|candy in|window|balcony|roof|pool|"
            r"by myself|alone)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "being hurt or sick",
        re.compile(
            r"\b(hurts?|hurting|bleed\w*|blood|fell|broke my|broken|bump(ed)?|ouch|owie|sick|"
            r"throw(ing)? up|can'?t breathe|bit me|stung)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "feeling sad, scared, or alone, or being treated badly",
        re.compile(
            r"\b(sad|scared|afraid|frightened|lonely|alone|cry\w*|upset|worried|nightmare|"
            r"monster|hates? me|nobody (likes|wants|loves|plays)|no friends|left out|"
            r"bull(y|ies|ied)|push(es|ed)? me|hit(s)? me|kick(s|ed)? me|mean to me|"
            r"teas(e|es|ed|ing)|don'?t want to go to school|want to run away|"
            r"big (bang|noise))\b",
            re.IGNORECASE,
        ),
    ),
    (
        _GRIEF,
        re.compile(
            r"\b(died|dies|dead|death|dying|passed away|passed on|put (\w+ ){0,2}to sleep|"
            r"funeral|heaven|buried|gone forever|never coming back|"
            r"miss (him|her|them|my (grandpa|grandma|granny|nana|dog|cat|fish|hamster|pet)))\b",
            re.IGNORECASE,
        ),
    ),
)


def safety_cues(text: str) -> list[str]:
    """Descriptions of every cue category the text matches, in a fixed order."""
    return [
        label
        for label, pat in _CUES
        if pat.search(text) and not (label == _GRIEF and _GAME.search(text))
    ]


def safety_note(text: str, earlier: Sequence[str] = ()) -> str | None:
    """The system note to place right before this message, or None.

    ``earlier`` is the child's previous messages, oldest first; a sticky cue (grief) in any of
    the last ``STICKY_TURNS`` of them carries over to this one."""
    cues = safety_cues(text)
    recent = [c for e in earlier[-STICKY_TURNS:] for c in safety_cues(e)]
    carried = [c for c in _STICKY if c not in cues and c in recent]
    if not cues and not carried:
        return None
    said = []
    if cues:
        said.append(f"the child just mentioned {' and '.join(cues)}")
    if carried:
        said.append(
            f"earlier the child mentioned {' and '.join(carried)}, still on their mind"
        )
    secret = " Never promise to keep it secret." if _SECRET in cues else ""
    grief = ""
    if _GRIEF in cues or carried:
        # A follow-up got comfort and no grown-up because one was named a turn earlier, and "is he
        # coming back tomorrow" got "I think he is resting now" (SIM-INTERACTION, grief).
        grief = (
            " Name the grown-up again even if you already did."
            " Be honest and kind: someone who has died does not come back; never say they are"
            " sleeping or resting."
        )
    return (
        f"SAFETY: {'; '.join(said)}. Comfort them briefly, then your reply MUST tell them to "
        "tell their mom, dad, or another trusted grown-up. "
        f"Do not answer only with a question.{secret}{grief}"
    )
