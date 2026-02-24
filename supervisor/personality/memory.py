"""Local memory store for the personality engine (PE spec S2 §8).

COPPA-compliant: stores only semantic tags (no raw transcripts),
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

MAX_TOTAL_ENTRIES = 50

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
        )


# ── Memory Store (PE spec S2 §8.4) ──────────────────────────────────


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
                    self._entries[entry.tag] = entry
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
    ) -> bool:
        """Add a new memory entry or reinforce an existing one.

        Returns True if the entry was added/reinforced, False if blocked
        (consent gate, invalid category, etc.).
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

        now = time.time()

        # Reinforce existing entry
        if tag in self._entries:
            entry = self._entries[tag]
            entry.reinforcement_count += 1
            entry.last_reinforced_ts = now
            entry.initial_strength = 1.0  # reset to full on reinforce
            return True

        # Enforce per-tier max
        tier_entries = [e for e in self._entries.values() if e.category == category]
        if len(tier_entries) >= tier.max_entries:
            # Evict weakest in this tier
            weakest = min(tier_entries, key=lambda e: e.current_strength(now))
            del self._entries[weakest.tag]

        # Enforce total max
        if len(self._entries) >= MAX_TOTAL_ENTRIES:
            # Evict weakest entry across all tiers
            weakest = min(self._entries.values(), key=lambda e: e.current_strength(now))
            del self._entries[weakest.tag]

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
        )
        self._entries[tag] = entry
        return True

    def get_active(self, threshold: float = 0.05) -> list[MemoryEntry]:
        """Return all entries with current_strength above threshold."""
        now = time.time()
        return [
            e for e in self._entries.values() if e.current_strength(now) > threshold
        ]

    def tag_summary(self) -> list[str]:
        """Return active tag names for LLM profile injection."""
        return [e.tag for e in self.get_active()]

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
