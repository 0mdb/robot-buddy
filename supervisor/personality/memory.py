"""Local memory store for the personality engine (PE spec S2 §8).

Privacy-by-default: stores only semantic tags (no raw transcripts),
local-only on Pi filesystem, consent-gated, parent-deletable.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# ── Decay Tier Configuration (PE spec S2 §8.2) ────────────────────────


@dataclass(slots=True, frozen=True)
class DecayTier:
    """Immutable configuration for a memory decay tier."""

    decay_lambda: float  # per-second decay rate
    floor: float  # minimum strength (never decays below)
    max_entries: int  # per-tier cap


DECAY_TIERS: dict[str, DecayTier] = {
    "name": DecayTier(decay_lambda=0.0, floor=1.0, max_entries=1),
    "ritual": DecayTier(decay_lambda=8.91e-8, floor=0.10, max_entries=5),
    "topic": DecayTier(decay_lambda=3.82e-7, floor=0.0, max_entries=20),
    "tone": DecayTier(decay_lambda=1.15e-6, floor=0.0, max_entries=3),
    "preference": DecayTier(decay_lambda=2.01e-6, floor=0.0, max_entries=10),
}

# Per person (and for the household bucket): memory is kept per recognised household member
# since 2026-11-18 (PE spec S2 §8.1 amended), so each child's facts stay theirs.
MAX_TOTAL_ENTRIES = 50
# Across everyone, a backstop.
MAX_ALL_ENTRIES = 300

HOUSEHOLD = ""  # member_id of facts not tied to a recognised person


def entry_key(member_id: str, tag: str) -> str:
    """Storage key: household facts keep the bare tag (files written before per-person
    memory load unchanged); a member's facts are ``<member_id>:<tag>``."""
    return f"{member_id}:{tag}" if member_id else tag


# Default valence/arousal biases inferred from tag semantics.
_POSITIVE_PREFIXES = ("likes_", "loves_", "enjoys_", "interested_", "favorite_")
_NEGATIVE_PREFIXES = ("dislikes_", "scared_of_", "upset_by_", "afraid_of_")


def infer_valence_arousal(tag: str) -> tuple[float, float]:
    """Infer default valence/arousal bias from tag name."""
    lower = tag.lower()
    for prefix in _POSITIVE_PREFIXES:
        if lower.startswith(prefix):
            return (0.05, 0.02)
    for prefix in _NEGATIVE_PREFIXES:
        if lower.startswith(prefix):
            return (-0.05, 0.02)
    return (0.0, 0.0)


# ── Memory Entry (PE spec S2 §8.1) ──────────────────────────────────


@dataclass(slots=True)
class MemoryEntry:
    """A single memory entry with exponential decay."""

    tag: str
    category: str  # "name" | "topic" | "ritual" | "tone" | "preference"
    valence_bias: float
    arousal_bias: float
    initial_strength: float
    created_ts: float  # wall-clock (time.time())
    last_reinforced_ts: float  # wall-clock
    reinforcement_count: int
    decay_lambda: float  # per-second decay rate (from tier)
    source: str  # "llm_extract" | "rule_infer"
    member_id: str = HOUSEHOLD  # roster member the fact is about; "" = household

    @property
    def key(self) -> str:
        return entry_key(self.member_id, self.tag)

    def current_strength(self, now: float | None = None) -> float:
        """Compute current strength via exponential decay, floored by tier."""
        if now is None:
            now = time.time()
        age_s = max(0.0, now - self.last_reinforced_ts)
        raw = self.initial_strength * math.exp(-self.decay_lambda * age_s)
        tier = DECAY_TIERS.get(self.category)
        floor = tier.floor if tier else 0.0
        return max(floor, raw)

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "category": self.category,
            "valence_bias": self.valence_bias,
            "arousal_bias": self.arousal_bias,
            "initial_strength": self.initial_strength,
            "created_ts": self.created_ts,
            "last_reinforced_ts": self.last_reinforced_ts,
            "reinforcement_count": self.reinforcement_count,
            "decay_lambda": self.decay_lambda,
            "source": self.source,
            "member_id": self.member_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MemoryEntry:
        return cls(
            tag=str(d["tag"]),
            category=str(d.get("category", "topic")),
            valence_bias=float(d.get("valence_bias", 0.0)),
            arousal_bias=float(d.get("arousal_bias", 0.0)),
            initial_strength=float(d.get("initial_strength", 1.0)),
            created_ts=float(d.get("created_ts", 0.0)),
            last_reinforced_ts=float(d.get("last_reinforced_ts", 0.0)),
            reinforcement_count=int(d.get("reinforcement_count", 0)),
            decay_lambda=float(d.get("decay_lambda", 0.0)),
            source=str(d.get("source", "llm_extract")),
            member_id=str(d.get("member_id", HOUSEHOLD) or HOUSEHOLD),
        )


# ── Memory Store (PE spec S2 §8.4) ──────────────────────────────────


# ── Tag hygiene ─────────────────────────────────────────────────────
# The LLM coins a new tag for every phrasing of a fact (animal_pepper_cat, pet_pepper_cat,
# child_has_cat_pepper) and tags the conversation itself (greeting_response,
# child_acknowledgement): the air rig's memory test, 2026-11-15. Compare tags by their
# content words.
_JUNK_WORDS = frozenset(
    {
        "greeting", "hello", "hi", "bye", "goodbye", "response", "reply", "acknowledgement",
        "acknowledgment", "friendly", "contact", "checkin", "check", "initiating",
        "initiated", "conversation", "chat", "talking", "interaction", "back",
    }
)  # fmt: skip
_GENERIC_WORDS = frozenset(
    {
        "child", "kid", "has", "have", "had", "is", "the", "a", "an", "of", "my", "named",
        "called", "like", "likes", "love", "loves", "favorite", "favourite", "interested",
        "in", "about", "topic", "animal", "pet", "new", "recent", "mentioned", "and",
    }
)  # fmt: skip


def _content_words(tag: str) -> frozenset[str]:
    words = [w for w in tag.lower().replace("-", "_").split("_") if w]
    stems = {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}
    return frozenset(
        w for w in stems if w not in _JUNK_WORDS and w not in _GENERIC_WORDS
    )


class MemoryStore:
    """Local-only memory store with decay tiers, eviction, and consent gate.

    All persistence is JSON on the local filesystem. Memory entries are
    never transmitted to the server — only semantic tag names are shared
    via the LLM profile for context injection.
    """

    def __init__(self, path: str, consent: bool) -> None:
        self._path = Path(path)
        self._consent = consent
        self._entries: dict[str, MemoryEntry] = {}  # tag → entry
        self._session_count: int = 0
        self._total_conversation_s: float = 0.0
        self._created_ts: float = 0.0

    @property
    def consent(self) -> bool:
        return self._consent

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    # ── Persistence ──────────────────────────────────────────────────

    def load(self) -> None:
        """Load memory entries from JSON file."""
        if not self._path.exists():
            self._created_ts = time.time()
            return
        try:
            raw = json.loads(self._path.read_text())
            if raw.get("version") != 1:
                log.warning("unknown memory version %s, ignoring", raw.get("version"))
                self._created_ts = time.time()
                return
            for entry_dict in raw.get("entries", []):
                try:
                    entry = MemoryEntry.from_dict(entry_dict)
                    if entry.category == "name" and not entry.member_id:
                        # Names belong to a person; a household-wide name (from before
                        # per-person memory) called everyone by one child's name.
                        log.info("memory: dropped household name entry %r", entry.tag)
                        continue
                    self._entries[entry.key] = entry
                except Exception as e:
                    log.warning("skipping malformed memory entry: %s", e)
            self._session_count = int(raw.get("session_count", 0))
            self._total_conversation_s = float(raw.get("total_conversation_s", 0.0))
            self._created_ts = float(raw.get("created_ts", time.time()))
            log.info("loaded %d memory entries from %s", len(self._entries), self._path)
        except Exception as e:
            log.warning("failed to load memory store: %s", e)
            self._created_ts = time.time()

    def save(self) -> None:
        """Persist memory entries to JSON file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "entries": [e.to_dict() for e in self._entries.values()],
                "session_count": self._session_count,
                "total_conversation_s": round(self._total_conversation_s, 1),
                "created_ts": self._created_ts,
            }
            self._path.write_text(json.dumps(data, indent=2) + "\n")
        except Exception as e:
            log.warning("failed to save memory store: %s", e)

    # ── Core Operations ──────────────────────────────────────────────

    def add_or_reinforce(
        self,
        tag: str,
        category: str,
        valence_bias: float | None = None,
        arousal_bias: float | None = None,
        source: str = "llm_extract",
        member_id: str = HOUSEHOLD,
    ) -> bool:
        """Add a new memory entry or reinforce an existing one, for ``member_id`` (the
        recognised speaker) or the household.

        Returns True if the entry was added/reinforced, False if blocked
        (consent gate, invalid category, a name with no recognised person, etc.).
        """
        if not self._consent:
            return False

        tag = tag.strip()
        if not tag:
            return False

        # Validate category
        if category not in DECAY_TIERS:
            category = "topic"
        tier = DECAY_TIERS[category]
        if category == "name" and not member_id:
            # Nobody recognised: the name could be anyone's, and the roster has names.
            log.info("memory: dropped name tag with no recognised speaker")
            return False

        now = time.time()

        content = _content_words(tag)
        if not content:
            log.info("memory: dropped content-free tag %r", tag)
            return False
        # The same fact under another name: reinforce the tag already stored.
        same = self._same_fact(content, member_id)
        if same is not None and same != tag:
            log.info("memory: %r is %r again", tag, same)
            tag = same
        key = entry_key(member_id, tag)

        # Reinforce existing entry
        if key in self._entries:
            entry = self._entries[key]
            entry.reinforcement_count += 1
            entry.last_reinforced_ts = now
            entry.initial_strength = 1.0  # reset to full on reinforce
            return True

        mine = [e for e in self._entries.values() if e.member_id == member_id]
        # Enforce per-tier max (per person)
        tier_entries = [e for e in mine if e.category == category]
        if len(tier_entries) >= tier.max_entries:
            # Evict weakest in this tier
            weakest = min(tier_entries, key=lambda e: e.current_strength(now))
            del self._entries[weakest.key]
            mine.remove(weakest)

        # Enforce total max (per person, then across everyone)
        if len(mine) >= MAX_TOTAL_ENTRIES:
            weakest = min(mine, key=lambda e: e.current_strength(now))
            del self._entries[weakest.key]
        if len(self._entries) >= MAX_ALL_ENTRIES:
            weakest = min(self._entries.values(), key=lambda e: e.current_strength(now))
            del self._entries[weakest.key]

        # Infer bias from tag name if not provided
        if valence_bias is None or arousal_bias is None:
            default_v, default_a = infer_valence_arousal(tag)
            if valence_bias is None:
                valence_bias = default_v
            if arousal_bias is None:
                arousal_bias = default_a

        entry = MemoryEntry(
            tag=tag,
            category=category,
            valence_bias=valence_bias,
            arousal_bias=arousal_bias,
            initial_strength=1.0,
            created_ts=now,
            last_reinforced_ts=now,
            reinforcement_count=1,
            decay_lambda=tier.decay_lambda,
            source=source,
            member_id=member_id,
        )
        self._entries[key] = entry
        return True

    def _same_fact(
        self, content: frozenset[str], member_id: str = HOUSEHOLD
    ) -> str | None:
        """An existing tag with the same content words (or a superset/subset of two or
        more), i.e. the same fact phrased differently. Single-word overlaps don't count:
        'likes_cats' must not swallow 'cat_pepper'."""
        for e in self._entries.values():
            if e.member_id != member_id:
                continue
            tag = e.tag
            other = _content_words(tag)
            if other == content:
                return tag
            small = min(other, content, key=len)
            if len(small) >= 2 and (other <= content or content <= other):
                return tag
        return None

    def get_active(self, threshold: float = 0.05) -> list[MemoryEntry]:
        """Return all entries with current_strength above threshold."""
        now = time.time()
        return [
            e for e in self._entries.values() if e.current_strength(now) > threshold
        ]

    def tag_summary(self, member_id: str | None = None) -> list[str]:
        """Active tag names for LLM profile injection, most recently reinforced first:
        ``member_id``'s own facts, then the household's (``None``: household only).

        The prompt shows only the first few (server conversation.py), and insertion order
        put the oldest first: old generic tags crowded out what a child said last time, and
        a long-gap recall test got 0/4 with the facts stored (2026-11-15)."""
        by = self.tags_by_member()
        own = by.get(member_id, []) if member_id else []
        return own + by.get(HOUSEHOLD, [])

    def tags_by_member(self) -> dict[str, list[str]]:
        """Active tags per member id ("" = household), most recently reinforced first."""
        active = sorted(
            self.get_active(), key=lambda e: e.last_reinforced_ts, reverse=True
        )
        out: dict[str, list[str]] = {}
        for e in active:
            out.setdefault(e.member_id, []).append(e.tag)
        return out

    def forget_member(self, member_id: str) -> int:
        """Drop everything known about one member (removed from the roster)."""
        keys = [k for k, e in self._entries.items() if e.member_id == member_id]
        for k in keys:
            del self._entries[k]
        if keys:
            self.save()
        return len(keys)

    def reset(self) -> None:
        """Wipe all memory entries and delete the file (parent 'Forget Everything')."""
        self._entries.clear()
        self._session_count = 0
        self._total_conversation_s = 0.0
        try:
            if self._path.exists():
                self._path.unlink()
            log.info("memory store reset (file deleted)")
        except Exception as e:
            log.warning("failed to delete memory file: %s", e)

    def forget(self, tags: list[str]) -> int:
        """Drop specific entries (a parent removing one memory; the eval rig cleaning up
        after itself). Returns how many were removed."""
        wanted = set(tags)
        removed = [
            k for k, e in list(self._entries.items()) if k in wanted or e.tag in wanted
        ]
        for k in removed:
            del self._entries[k]
        if removed:
            self.save()
            log.info("memory: forgot %d entries: %s", len(removed), removed)
        return len(removed)

    def increment_session(self, conversation_s: float = 0.0) -> None:
        """Track session count and total conversation time."""
        self._session_count += 1
        self._total_conversation_s += conversation_s

    def to_dict(self) -> dict:
        """Full serialization for API responses."""
        now = time.time()
        return {
            "version": 1,
            "entries": [
                {
                    **e.to_dict(),
                    "current_strength": round(e.current_strength(now), 4),
                }
                for e in self._entries.values()
            ],
            "session_count": self._session_count,
            "total_conversation_s": round(self._total_conversation_s, 1),
            "created_ts": self._created_ts,
            "entry_count": len(self._entries),
        }
