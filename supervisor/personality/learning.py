"""Learning-game progress per child: attempts, current step per skill, the two locks.

Design: docs/learning-games.md §2 (levels, ceiling + mastery locks) and §2.1 (measuring).

- **Robot-local and private.** One JSON file in the roster's sidecar directory
  (``data/household_learning/progress.json``, mode 600), so "Forget everyone" removes it and
  removing a member removes theirs. Never sent anywhere except the dashboard and, as
  ``learner`` (steps and ceiling, no attempts), Buddy's own LAN server.
- **Attempts come from code.** The server checks drill answers itself (``drill.py``) and sends
  one record per answered item; the robot files it under the recognised speaker. An attempt is
  keyed by ``<seed>:<game>:<Q#>`` and replaced if the same item is re-answered (a late resume
  merges speech and re-checks it), so nothing is double-counted.
- **A game is one round of 5 items.** Only complete rounds count for mastery and stepping down.
- **Steps change only when a round completes**, so the next round is the first at the new step.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

GRADES = ("K", "G1", "G2", "G3")
GRADE_NAMES = {"K": "Kindergarten", "G1": "Grade 1", "G2": "Grade 2", "G3": "Grade 3"}
ROUND = 5  # items per game (server/app/llm/games/drill.py ROUND)
MASTERY_ACC = 0.8
MASTERY_GAMES = 3  # ...on this many different days
STEP_DOWN_ACC = 0.5  # "misses most of" a game
CONFIDENT_CODE_SHARE = 0.8
MAX_ATTEMPTS = 1000  # per member; oldest dropped first
VERDICTS = ("right", "wrong", "none")
_ANSWER_MAX = 40


def base_grade(age: int | None) -> str:
    """Base level from the roster age (§2); mirrors server games.grade_for_age."""
    if age is None:
        return "G2"
    if age <= 5:
        return "K"
    return {6: "G1", 7: "G2"}.get(age, "G3")


def default_ceiling(age: int | None) -> str:
    """Base level + 1 (§2 lock 1)."""
    return _shift(base_grade(age), 1)


def _shift(grade: str, by: int) -> str:
    i = GRADES.index(grade) if grade in GRADES else 2
    return GRADES[max(0, min(len(GRADES) - 1, i + by))]


def _idx(grade: str) -> int:
    return GRADES.index(grade) if grade in GRADES else 2


def default_path(memory_path: str | Path) -> Path:
    """In the roster's sidecar directory (removed by roster.forget_everyone)."""
    return Path(memory_path).parent / "household_learning" / "progress.json"


@dataclass(frozen=True, slots=True)
class RoundResult:
    round_id: str
    skill: str
    step: str
    right: int
    scored: int
    code: int  # items decided by code
    day: str  # local date of the round's last item
    at: float

    @property
    def acc(self) -> float:
        return self.right / self.scored if self.scored else 0.0


def _clean_attempt(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a record from the server; None if it can't be used."""
    try:
        key = str(rec["key"])
        game = str(rec["game"])
        skill = str(rec["skill"])
        step = str(rec["step"])
        verdict = str(rec["verdict"])
        q = int(rec["q"])
    except (KeyError, TypeError, ValueError):
        return None
    if (
        not key
        or not game
        or not skill
        or step not in GRADES
        or verdict not in VERDICTS
    ):
        return None
    seed_game = key.rsplit(":", 1)[0]
    return {
        "key": key,
        "round": f"{seed_game}:{q // ROUND}",
        "game": game,
        "skill": skill,
        "step": step,
        "item": str(rec.get("item", ""))[:80],
        "expected": str(rec.get("expected", ""))[:40],
        # The parsed answer (a number or the right word), never the child's raw words.
        "answer": str(rec.get("answer", ""))[:_ANSWER_MAX],
        "verdict": verdict,
        "decided": "code" if rec.get("decided", "code") == "code" else "model",
        "source": "touch" if rec.get("source") == "touch" else "voice",
    }


class LearningStore:
    """The progress file. Re-read when it changes on disk, written atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {"version": 1, "members": {}}
        self._mtime: float | None = None

    # ── storage ────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._data = {"version": 1, "members": {}}
            self._mtime = None
            return self._data
        if mtime != self._mtime:
            try:
                data = json.loads(self.path.read_text())
                if not isinstance(data.get("members"), dict):
                    raise ValueError("no members")
                self._data = data
            except (OSError, ValueError) as e:
                log.warning("learning progress unreadable (%s); starting empty", e)
                self._data = {"version": 1, "members": {}}
            self._mtime = mtime
        return self._data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self._data, f, separators=(",", ":"))
        os.replace(tmp, self.path)
        self._mtime = self.path.stat().st_mtime

    def _member(self, member_id: str, *, create: bool = False) -> dict[str, Any] | None:
        members = self._load()["members"]
        m = members.get(member_id)
        if m is None and create:
            m = members[member_id] = {"ceiling": None, "skills": {}, "attempts": []}
        return m

    # ── levels ─────────────────────────────────────────────────────

    def ceiling(self, member_id: str, age: int | None) -> str:
        m = self._member(member_id)
        c = m.get("ceiling") if m else None
        return c if c in GRADES else default_ceiling(age)

    def step(self, member_id: str, skill: str, age: int | None) -> str:
        m = self._member(member_id)
        s = (m or {}).get("skills", {}).get(skill, {}).get("step")
        step = s if s in GRADES else base_grade(age)
        ceiling = self.ceiling(member_id, age)
        return step if _idx(step) <= _idx(ceiling) else ceiling

    def set_ceiling(self, member_id: str, grade: str | None) -> None:
        """A parent's ceiling; None = the default (base + 1)."""
        if grade is not None and grade not in GRADES:
            raise ValueError(f"grade must be one of {', '.join(GRADES)}")
        m = self._member(member_id, create=True)
        assert m is not None
        m["ceiling"] = grade
        self._save()

    def learner(self, member_id: str, age: int | None) -> dict[str, Any]:
        """For the profile (learning-games.md §3): base, ceiling, step per practised skill,
        and the skills she may praise (confident, L3). No attempts, no words."""
        m = self._member(member_id) or {}
        skills = m.get("skills", {})
        return {
            "base": base_grade(age),
            "ceiling": self.ceiling(member_id, age),
            "steps": {s: self.step(member_id, s, age) for s in skills},
            "confident": sorted(s for s, v in skills.items() if v.get("confident")),
        }

    # ── attempts ───────────────────────────────────────────────────

    def record(
        self,
        member_id: str,
        age: int | None,
        rec: dict[str, Any],
        *,
        now: float | None = None,
    ) -> list[str]:
        """File one answered item. Returns what changed ("add_sub_facts: G2 -> G3")."""
        a = _clean_attempt(rec)
        if a is None or not member_id:
            return []
        now = time.time() if now is None else now
        a["at"] = now
        m = self._member(member_id, create=True)
        assert m is not None
        attempts: list[dict[str, Any]] = m["attempts"]
        for i, old in enumerate(attempts):
            if old.get("key") == a["key"]:
                attempts[i] = a
                break
        else:
            attempts.append(a)
        del attempts[:-MAX_ATTEMPTS]
        changes: list[str] = []
        done = [x for x in attempts if x["round"] == a["round"]]
        if len(done) >= ROUND:
            changes = self._after_round(m, a["skill"], age, member_id, now)
        self._save()
        return changes

    def _after_round(
        self, m: dict[str, Any], skill: str, age: int | None, member_id: str, now: float
    ) -> list[str]:
        sk = m["skills"].setdefault(skill, {})
        step = self.step(member_id, skill, age)
        since = float(sk.get("since", 0.0))
        rounds = [
            r
            for r in rounds_of(m["attempts"])
            if r.skill == skill and r.step == step and r.at >= since
        ]
        changes: list[str] = []
        good = [r for r in rounds if r.scored >= ROUND and r.acc >= MASTERY_ACC]
        days = {r.day for r in good}
        if len(days) >= MASTERY_GAMES:
            mastered = set(sk.get("mastered", []))
            mastered.add(step)
            sk["mastered"] = sorted(mastered, key=_idx)
            code = sum(r.code for r in good)
            items = sum(r.scored for r in good)
            if items and code / items >= CONFIDENT_CODE_SHARE:
                sk["confident"] = True
            if _idx(step) < _idx(self.ceiling(member_id, age)):
                sk["step"], sk["since"] = _shift(step, 1), now
                changes.append(f"{skill}: {step} -> {sk['step']} (mastered)")
            return changes
        last2 = [r for r in rounds if r.scored >= ROUND][-2:]
        if (
            len(last2) == 2
            and all(r.acc < STEP_DOWN_ACC for r in last2)
            and step != "K"
        ):
            sk["step"], sk["since"] = _shift(step, -1), now
            changes.append(f"{skill}: {step} -> {sk['step']} (stepped down)")
        return changes

    # ── parents ────────────────────────────────────────────────────

    def reset(self, member_id: str) -> None:
        """Clear a child's progress (attempts and steps); the ceiling stays."""
        m = self._member(member_id)
        if m is None:
            return
        m["skills"], m["attempts"] = {}, []
        self._save()

    def forget(self, member_id: str) -> None:
        """Everything about a member (they were removed from the roster)."""
        members = self._load()["members"]
        if members.pop(member_id, None) is not None:
            self._save()

    def summary(self, member_id: str, age: int | None) -> dict[str, Any]:
        """The dashboard view for one child (§2.1 "Parents see")."""
        m = self._member(member_id) or {"skills": {}, "attempts": []}
        rounds = rounds_of(m["attempts"])
        skills = []
        for skill in sorted({a["skill"] for a in m["attempts"]} | set(m["skills"])):
            sk = m["skills"].get(skill, {})
            mine = [r for r in rounds if r.skill == skill and r.scored >= ROUND]
            tries = [a for a in m["attempts"] if a["skill"] == skill]
            missed: dict[str, int] = {}
            for a in tries:
                if a["verdict"] != "right" and a["item"]:
                    missed[a["item"]] = missed.get(a["item"], 0) + 1
            last5 = mine[-5:]
            skills.append(
                {
                    "skill": skill,
                    "step": self.step(member_id, skill, age),
                    "mastered": sk.get("mastered", []),
                    "confident": bool(sk.get("confident")),
                    "games": [
                        {"day": r.day, "step": r.step, "right": r.right, "of": r.scored}
                        for r in mine[-10:]
                    ],
                    "trend": round(sum(r.acc for r in last5) / len(last5), 2)
                    if last5
                    else None,
                    "code_share": round(
                        sum(1 for a in tries if a["decided"] == "code") / len(tries), 2
                    )
                    if tries
                    else None,
                    "missed_most": [
                        k for k, _ in sorted(missed.items(), key=lambda kv: -kv[1])[:3]
                    ],
                }
            )
        return {
            "member_id": member_id,
            "base": base_grade(age),
            "ceiling": self.ceiling(member_id, age),
            "ceiling_is_default": m.get("ceiling") not in GRADES,
            "skills": skills,
        }


def rounds_of(attempts: list[dict[str, Any]]) -> list[RoundResult]:
    """Group attempts into games (rounds), oldest first."""
    by: dict[str, list[dict[str, Any]]] = {}
    for a in attempts:
        by.setdefault(a["round"], []).append(a)
    out = []
    for rid, items in by.items():
        first, last = items[0], max(items, key=lambda x: x["at"])
        out.append(
            RoundResult(
                round_id=rid,
                skill=first["skill"],
                step=first["step"],
                right=sum(1 for x in items if x["verdict"] == "right"),
                scored=len(items),
                code=sum(1 for x in items if x["decided"] == "code"),
                day=datetime.fromtimestamp(last["at"]).astimezone().date().isoformat(),
                at=float(last["at"]),
            )
        )
    out.sort(key=lambda r: r.at)
    return out
