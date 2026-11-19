"""Game cards: the rules for one game, added to the prompt only while it is played.

Progressive disclosure (docs/learning-games.md §3): the cached system prompt carries one menu
line; a card (rules + content for the child's grade) goes in as a system message right before
the child's message, so it never breaks the cached prefix. The active game is the
``Game: <id>`` the model writes first in its notes; on the turn a game is asked for, before
any notes, a keyword cue on the child's words picks it.

Cards are data, one TOML file each in this directory.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.llm.games import checker as checker  # noqa: F401  (games.checker)
from app.llm.games import drill as drill  # noqa: F401  (games.drill)
from app.llm.games import guess as guess  # noqa: F401  (games.guess)
from app.llm.games import rocket as rocket  # noqa: F401  (games.rocket)
from app.llm.games import sound_swap as _sound_swap

# Games whose rounds are run by code (questions, checking, score).
DRILLS = {
    rocket.DRILL.game_id: rocket.DRILL,
    _sound_swap.DRILL.game_id: _sound_swap.DRILL,
}

_DIR = Path(__file__).parent
GRADES = ("K", "G1", "G2", "G3")
_GRADE_NAMES = {"K": "Kindergarten", "G1": "Grade 1", "G2": "Grade 2", "G3": "Grade 3"}
_NOTES_GAME = re.compile(r"\bGame:\s*([a-z][a-z0-9_]*)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class GameCard:
    id: str
    name: str
    menu: str  # a few words for the menu line
    skill: str  # learning skill it practises ("" = not a learning game)
    keywords: re.Pattern[str]
    rules: str
    levels: dict[str, str]  # grade -> content for that grade

    def render(self, grade: str, *, asked: bool = False, drilled: bool = False) -> str:
        """``asked``: picked from the child's words, not from a game already in the notes.
        ``drilled``: the rounds are run by code (DRILLS), which picks every item."""
        level = self.levels.get(grade) or self._nearest(grade)
        head = (
            f"GAME CARD: {self.name} (Game: {self.id}). The child's words may be asking for"
            " this game. If they are, start it right away in this reply; if they are only"
            f' talking about it, don\'t. While it lasts, write "Game: {self.id}" first in'
            " notes."
            if asked
            else f'GAME CARD: {self.name} (Game: {self.id}). Write "Game: {self.id}" first'
            " in notes while it lasts."
        )
        lines = [head, self.rules.strip()]
        if self.skill:
            lines.append(
                "In this game every reply ends with the next question or puzzle, said out"
                " loud: the speech rule about not tacking on questions does not apply to"
                " game questions."
            )
        if level:
            lines.append(f"LEVEL ({_GRADE_NAMES.get(grade, grade)}): {level.strip()}")
        if level and not drilled:
            lines.append(
                "If the child misses two in a row, make the next ones easier without saying"
                " so. If they want to stop or play something else, stop at once, cheerfully."
            )
        return "\n".join(lines)

    def _nearest(self, grade: str) -> str:
        i = GRADES.index(grade) if grade in GRADES else 2
        for j in sorted(range(len(GRADES)), key=lambda k: abs(k - i)):
            if GRADES[j] in self.levels:
                return self.levels[GRADES[j]]
        return ""


def _load(path: Path) -> GameCard:
    d = tomllib.loads(path.read_text())
    if d.get("id") != path.stem:
        raise ValueError(f"{path}: id {d.get('id')!r} does not match the file name")
    for key in ("name", "menu", "keywords", "rules"):
        if not d.get(key):
            raise ValueError(f"{path}: {key} is required")
    levels = {str(k): str(v) for k, v in (d.get("levels") or {}).items()}
    bad = set(levels) - set(GRADES)
    if bad:
        raise ValueError(f"{path}: unknown grades {sorted(bad)}")
    return GameCard(
        id=d["id"],
        name=d["name"],
        menu=d["menu"],
        skill=d.get("skill", ""),
        keywords=re.compile(r"\b(?:" + "|".join(d["keywords"]) + r")\b", re.IGNORECASE),
        rules=d["rules"],
        levels=levels,
    )


@cache
def cards() -> dict[str, GameCard]:
    return {c.id: c for c in (_load(p) for p in sorted(_DIR.glob("*.toml")))}


def menu_line() -> str:
    """One line for the system prompt (cached): what she can offer, and the notes rule."""
    games = "; ".join(f"{c.name} ({c.menu})" for c in cards().values())
    return (
        f"- Games you know well: {games}. When one starts, the first thing in notes is"
        ' "Game: <id>" (ids: '
        + ", ".join(cards())
        + "); the rules arrive as a GAME CARD."
    )


def active_game(user_text: str, last_notes: str) -> tuple[GameCard, bool] | None:
    """(card, asked): the game in the last reply's notes, unless the child's words name a
    different one (a switch). ``asked`` is True when the card comes from the child's words."""
    m = _NOTES_GAME.search(last_notes or "")
    playing = cards().get(m.group(1).lower()) if m else None
    named = [c for c in cards().values() if c.keywords.search(user_text or "")]
    if len(named) == 1 and named[0] is not playing:
        return named[0], True
    if playing is not None:
        return playing, False
    return None


def grade_for_age(age: int | None) -> str:
    """Base level from the child's age (docs/learning-games.md §2)."""
    if age is None:
        return "G2"
    if age <= 5:
        return "K"
    return {6: "G1", 7: "G2"}.get(age, "G3")
