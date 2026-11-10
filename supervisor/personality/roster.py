"""Household roster: the opt-in, parent-managed list of who lives with Buddy.

Design: ~/vantage/docs/SIM-INTERACTION.md, decision I3 and stage 3.

- **Local only.** One TOML file beside the personality memory (``data/household.toml``), which
  is git-ignored. Nothing in it leaves the robot: the only thing derived from it that reaches the
  server is the youngest enrolled child's *age*, so an unidentified speaker gets the most
  conservative profile (fallback rule 1). Names never leave the robot until recognition exists
  (stage 5), and then only the recognised speaker's.
- **Off by default.** No file, or ``enabled = false``, means the roster is not used at all.
- **Parent-deletable in one action.** :func:`forget_everyone` removes the file and anything
  stored beside it for the roster.

Never commit a real roster, and never put a real household's names in tests or docs.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import tomllib
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path

log = logging.getLogger(__name__)

KINDS = ("kid", "adult", "animal")
MAX_MEMBERS = 12
MAX_NAME_LEN = 40
KID_AGE = (1, 17)
ADULT_AGE = (18, 120)

# Things stored beside the roster for it (voice embeddings, from stage 5). Removed with it.
_SIDECAR_DIR = "household_voice"


class RosterError(ValueError):
    """A request the roster refuses (validation); the message is safe to show a parent."""


@dataclass(frozen=True, slots=True)
class Member:
    id: str
    name: str
    kind: str
    age: int | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {"id": self.id, "name": self.name, "kind": self.kind}
        if self.age is not None:
            d["age"] = self.age
        return d


@dataclass(frozen=True, slots=True)
class Roster:
    enabled: bool = False
    members: tuple[Member, ...] = field(default=())

    def to_dict(self) -> dict[str, object]:
        return {"enabled": self.enabled, "members": [m.to_dict() for m in self.members]}

    def youngest_kid_age(self) -> int | None:
        if not self.enabled:
            return None
        ages = [m.age for m in self.members if m.kind == "kid" and m.age is not None]
        return min(ages) if ages else None

    def audience_hint(self) -> dict[str, object] | None:
        """The audience block for the /converse profile message, or None.

        Nobody is recognised yet (no detection until stage 5), so the speaker is "unknown",
        and the server's fallback rule 1 gives them the youngest enrolled child's profile. Only
        that age leaves the robot; no names, no ids.
        """
        age = self.youngest_kid_age()
        if age is None:
            return None
        return {
            "present": [{"kind": "unknown", "confidence": 0.0, "sources": []}],
            "speaking": 0,
            "household": {"youngest_kid_age": age},
        }


# ── Validation ──────────────────────────────────────────────────────


def _clean_name(raw: object) -> str:
    if not isinstance(raw, str):
        raise RosterError("name must be text")
    name = unicodedata.normalize("NFC", raw).strip()
    if not name:
        raise RosterError("name is required")
    if len(name) > MAX_NAME_LEN:
        raise RosterError(f"name is longer than {MAX_NAME_LEN} characters")
    if any(unicodedata.category(c).startswith("C") for c in name):
        raise RosterError("name contains control characters")
    return name


def _clean_age(kind: str, raw: object) -> int | None:
    if kind == "animal":
        if raw not in (None, ""):
            raise RosterError("animals have no age in the roster")
        return None
    if raw in (None, ""):
        if kind == "kid":
            raise RosterError("a child's age is required (it picks how Buddy talks)")
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise RosterError("age must be a whole number")
    lo, hi = KID_AGE if kind == "kid" else ADULT_AGE
    if not lo <= raw <= hi:
        raise RosterError(f"a {kind}'s age must be {lo}-{hi}")
    return raw


def _clean_kind(raw: object) -> str:
    if raw not in KINDS:
        raise RosterError(f"kind must be one of {', '.join(KINDS)}")
    return str(raw)


# ── Operations (pure: return a new Roster) ──────────────────────────


def add_member(
    roster: Roster, *, name: object, kind: object, age: object = None
) -> Roster:
    if len(roster.members) >= MAX_MEMBERS:
        raise RosterError(f"the roster holds at most {MAX_MEMBERS} members")
    k = _clean_kind(kind)
    m = Member(id=f"{k}_{secrets.token_hex(3)}", name=_clean_name(name), kind=k)
    m = replace(m, age=_clean_age(k, age))
    return replace(roster, members=(*roster.members, m))


def update_member(roster: Roster, member_id: str, changes: dict[str, object]) -> Roster:
    unknown = set(changes) - {"name", "kind", "age"}
    if unknown:
        raise RosterError(f"cannot change {', '.join(sorted(unknown))}")
    out: list[Member] = []
    found = False
    for m in roster.members:
        if m.id == member_id:
            found = True
            kind = _clean_kind(changes.get("kind", m.kind))
            name = _clean_name(changes.get("name", m.name))
            age_raw = (
                changes["age"]
                if "age" in changes
                else (m.age if kind == m.kind else None)
            )
            m = Member(id=m.id, name=name, kind=kind, age=_clean_age(kind, age_raw))
        out.append(m)
    if not found:
        raise KeyError(member_id)
    return replace(roster, members=tuple(out))


def remove_member(roster: Roster, member_id: str) -> Roster:
    kept = tuple(m for m in roster.members if m.id != member_id)
    if len(kept) == len(roster.members):
        raise KeyError(member_id)
    return replace(roster, members=kept)


# ── Storage ─────────────────────────────────────────────────────────


def load_strict(path: Path) -> Roster:
    """Read the roster, raising RosterError if the file exists but cannot be read. Every write
    goes through this, so a damaged file is refused, never silently replaced."""
    if not path.exists():
        return Roster()
    try:
        data = tomllib.loads(path.read_text())
        members = []
        for raw in data.get("member", []):
            kind = _clean_kind(raw.get("kind"))
            members.append(
                Member(
                    id=str(raw["id"]),
                    name=_clean_name(raw.get("name")),
                    kind=kind,
                    age=_clean_age(kind, raw.get("age")),
                )
            )
        return Roster(enabled=bool(data.get("enabled", False)), members=tuple(members))
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, RosterError) as e:
        raise RosterError(f"the roster file is damaged ({e}); fix or delete it") from e


def load(path: Path) -> Roster:
    """Read the roster for use. A missing or damaged file is an empty, disabled roster (fail
    closed: a damaged roster is not used)."""
    try:
        return load_strict(path)
    except RosterError as e:
        log.warning("household roster not used: %s", e)
        return Roster()


def _toml_str(s: str) -> str:
    # A JSON string is a valid TOML basic string (same escapes, \uXXXX for non-ASCII).
    return json.dumps(s)


def save(path: Path, roster: Roster) -> None:
    """Write atomically, owner-readable only."""
    lines = [
        "# Buddy's household roster. Robot-local and private: never commit or share this file.",
        "# Managed from the dashboard (Household). Delete the file to forget everyone.",
        "version = 1",
        f"enabled = {'true' if roster.enabled else 'false'}",
    ]
    for m in roster.members:
        lines += [
            "",
            "[[member]]",
            f"id = {_toml_str(m.id)}",
            f"name = {_toml_str(m.name)}",
        ]
        lines.append(f"kind = {_toml_str(m.kind)}")
        if m.age is not None:
            lines.append(f"age = {m.age}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def forget_everyone(path: Path) -> None:
    """Delete the roster and everything stored beside it for the roster."""
    path.unlink(missing_ok=True)
    path.with_name(path.name + ".tmp").unlink(missing_ok=True)
    shutil.rmtree(path.parent / _SIDECAR_DIR, ignore_errors=True)


def default_path(memory_path: str | Path) -> Path:
    """The roster lives beside the personality memory."""
    return Path(memory_path).parent / "household.toml"


class RosterFile:
    """A roster re-read when its file changes; cheap to poll (one stat)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime: float | None = None
        self._roster = Roster()

    def get(self) -> Roster:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._mtime, self._roster = None, Roster()
            return self._roster
        if mtime != self._mtime:
            self._mtime, self._roster = mtime, load(self.path)
        return self._roster
