"""Tests for the personality memory store (PE spec S2 §8)."""

from __future__ import annotations

import time

import pytest

from supervisor.personality.memory import (
    DECAY_TIERS,
    MAX_TOTAL_ENTRIES,
    MemoryEntry,
    MemoryStore,
    infer_valence_arousal,
)


# ── MemoryEntry ───────────────────────────────────────────────────────


class TestMemoryEntry:
    def test_name_tier_never_decays(self):
        now = time.time()
        entry = MemoryEntry(
            tag="child_name_emma",
            category="name",
            valence_bias=0.05,
            arousal_bias=0.02,
            initial_strength=1.0,
            created_ts=now - 365 * 86400,  # 1 year ago
            last_reinforced_ts=now - 365 * 86400,
            reinforcement_count=1,
            decay_lambda=0.0,
            source="llm_extract",
        )
        # Name tier: floor=1.0, lambda=0.0 → always 1.0
        assert entry.current_strength(now) == 1.0

    def test_topic_tier_decays_to_half_at_21_days(self):
        now = time.time()
        half_life_s = 21 * 86400
        entry = MemoryEntry(
            tag="likes_dinosaurs",
            category="topic",
            valence_bias=0.05,
            arousal_bias=0.02,
            initial_strength=1.0,
            created_ts=now - half_life_s,
            last_reinforced_ts=now - half_life_s,
            reinforcement_count=1,
            decay_lambda=DECAY_TIERS["topic"].decay_lambda,
            source="llm_extract",
        )
        strength = entry.current_strength(now)
        assert 0.45 < strength < 0.55, f"Expected ~0.5, got {strength}"

    def test_ritual_tier_floor(self):
        now = time.time()
        # Very old ritual — should floor at 0.10
        entry = MemoryEntry(
            tag="greeting_fist_bump",
            category="ritual",
            valence_bias=0.0,
            arousal_bias=0.0,
            initial_strength=1.0,
            created_ts=now - 5 * 365 * 86400,  # 5 years ago
            last_reinforced_ts=now - 5 * 365 * 86400,
            reinforcement_count=1,
            decay_lambda=DECAY_TIERS["ritual"].decay_lambda,
            source="llm_extract",
        )
        strength = entry.current_strength(now)
        assert strength == pytest.approx(0.10, abs=0.01)

    def test_topic_tier_no_floor(self):
        now = time.time()
        # Very old topic — floor is 0.0
        entry = MemoryEntry(
            tag="likes_trains",
            category="topic",
            valence_bias=0.0,
            arousal_bias=0.0,
            initial_strength=1.0,
            created_ts=now - 365 * 86400,
            last_reinforced_ts=now - 365 * 86400,
            reinforcement_count=1,
            decay_lambda=DECAY_TIERS["topic"].decay_lambda,
            source="llm_extract",
        )
        strength = entry.current_strength(now)
        assert strength < 0.01  # Essentially forgotten

    def test_fresh_entry_full_strength(self):
        now = time.time()
        entry = MemoryEntry(
            tag="test",
            category="topic",
            valence_bias=0.0,
            arousal_bias=0.0,
            initial_strength=1.0,
            created_ts=now,
            last_reinforced_ts=now,
            reinforcement_count=1,
            decay_lambda=DECAY_TIERS["topic"].decay_lambda,
            source="llm_extract",
        )
        assert entry.current_strength(now) == pytest.approx(1.0, abs=0.001)

    def test_serialization_roundtrip(self):
        now = time.time()
        entry = MemoryEntry(
            tag="test_tag",
            category="topic",
            valence_bias=0.05,
            arousal_bias=-0.02,
            initial_strength=1.0,
            created_ts=now,
            last_reinforced_ts=now,
            reinforcement_count=3,
            decay_lambda=3.82e-7,
            source="llm_extract",
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.tag == entry.tag
        assert restored.category == entry.category
        assert restored.valence_bias == entry.valence_bias
        assert restored.reinforcement_count == entry.reinforcement_count


# ── Valence/Arousal Inference ──────────────────────────────────────────


class TestInferValenceArousal:
    def test_positive_prefix(self):
        v, a = infer_valence_arousal("likes_dinosaurs")
        assert v > 0
        assert a > 0

    def test_negative_prefix(self):
        v, a = infer_valence_arousal("scared_of_spiders")
        assert v < 0
        assert a > 0

    def test_neutral_tag(self):
        v, a = infer_valence_arousal("child_name_emma")
        assert v == 0.0
        assert a == 0.0


# ── MemoryStore ────────────────────────────────────────────────────────


class TestMemoryStore:
    def test_consent_gate_blocks_storage(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=False)
        result = store.add_or_reinforce("likes_dinosaurs", "topic")
        assert result is False
        assert store.entry_count == 0

    def test_add_new_entry(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        result = store.add_or_reinforce("likes_dinosaurs", "topic")
        assert result is True
        assert store.entry_count == 1
        active = store.get_active()
        assert len(active) == 1
        assert active[0].tag == "likes_dinosaurs"
        assert active[0].category == "topic"
        assert active[0].decay_lambda == DECAY_TIERS["topic"].decay_lambda

    def test_reinforce_existing(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        store.add_or_reinforce("likes_dinosaurs", "topic")
        store.add_or_reinforce("likes_dinosaurs", "topic")
        assert store.entry_count == 1
        active = store.get_active()
        assert active[0].reinforcement_count == 2

    def test_invalid_category_defaults_to_topic(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        store.add_or_reinforce("something", "invalid_category")
        active = store.get_active()
        assert active[0].category == "topic"

    def test_per_tier_max_eviction(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        # Tone tier max = 3
        for i in range(4):
            store.add_or_reinforce(f"tone_{i}", "tone")
        assert store.entry_count == 3  # One was evicted

    def test_total_max_eviction(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        # Fill to 50 entries (use topic tier, max 20 per tier)
        # Use a mix of categories to avoid per-tier cap
        for i in range(20):
            store.add_or_reinforce(f"topic_{i}", "topic")
        for i in range(10):
            store.add_or_reinforce(f"pref_{i}", "preference")
        for i in range(5):
            store.add_or_reinforce(f"ritual_{i}", "ritual")
        for i in range(3):
            store.add_or_reinforce(f"tone_{i}", "tone")
        store.add_or_reinforce("child_name_test", "name")
        # Now at 39. Add more topics (but already at 20 tier max).
        # Add 11 more preferences (only 10 max per tier → will evict)
        for i in range(10, 21):
            store.add_or_reinforce(f"pref_{i}", "preference")
        # Should cap at MAX_TOTAL_ENTRIES
        assert store.entry_count <= MAX_TOTAL_ENTRIES

    def test_persistence_roundtrip(self, tmp_path):
        path = str(tmp_path / "mem.json")
        store = MemoryStore(path, consent=True)
        store.add_or_reinforce("likes_dinosaurs", "topic")
        store.add_or_reinforce("child_name_emma", "name")
        store.save()

        # Load into new store
        store2 = MemoryStore(path, consent=True)
        store2.load()
        assert store2.entry_count == 2
        tags = store2.tag_summary()
        assert "likes_dinosaurs" in tags
        assert "child_name_emma" in tags

    def test_reset_wipes_file(self, tmp_path):
        path = str(tmp_path / "mem.json")
        store = MemoryStore(path, consent=True)
        store.add_or_reinforce("test", "topic")
        store.save()
        assert (tmp_path / "mem.json").exists()

        store.reset()
        assert store.entry_count == 0
        assert not (tmp_path / "mem.json").exists()

    def test_tag_summary_only_active(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        store.add_or_reinforce("fresh_tag", "topic")
        # Add a very old entry directly
        old_entry = MemoryEntry(
            tag="ancient_tag",
            category="topic",
            valence_bias=0.0,
            arousal_bias=0.0,
            initial_strength=1.0,
            created_ts=0.0,
            last_reinforced_ts=0.0,  # epoch — very old
            reinforcement_count=1,
            decay_lambda=DECAY_TIERS["topic"].decay_lambda,
            source="llm_extract",
        )
        store._entries["ancient_tag"] = old_entry
        summary = store.tag_summary()
        assert "fresh_tag" in summary
        assert "ancient_tag" not in summary

    def test_empty_tag_rejected(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        result = store.add_or_reinforce("", "topic")
        assert result is False
        assert store.entry_count == 0

    def test_valence_bias_inferred(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        store.add_or_reinforce("likes_trains", "topic")
        active = store.get_active()
        assert active[0].valence_bias > 0  # Positive inferred

    def test_load_nonexistent_file(self, tmp_path):
        store = MemoryStore(str(tmp_path / "nonexistent.json"), consent=True)
        store.load()  # Should not raise
        assert store.entry_count == 0

    def test_load_corrupted_file(self, tmp_path):
        path = tmp_path / "mem.json"
        path.write_text("not json")
        store = MemoryStore(str(path), consent=True)
        store.load()  # Should not raise
        assert store.entry_count == 0

    def test_to_dict_includes_current_strength(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        store.add_or_reinforce("test_tag", "topic")
        d = store.to_dict()
        assert d["version"] == 1
        assert len(d["entries"]) == 1
        assert "current_strength" in d["entries"][0]
        assert d["entries"][0]["current_strength"] > 0.9

    def test_increment_session(self, tmp_path):
        store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
        store.increment_session(120.0)
        store.increment_session(60.0)
        d = store.to_dict()
        assert d["session_count"] == 2
        assert d["total_conversation_s"] == 180.0
