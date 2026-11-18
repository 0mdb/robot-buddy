"""Per-person memory (PE spec S2 §8.1 amended 2026-11-18) and conversation resume."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

from supervisor.personality.memory import MemoryStore


def _store(tmp_path) -> MemoryStore:
    return MemoryStore(str(tmp_path / "mem.json"), consent=True)


class TestPerPersonMemory:
    def test_facts_stay_with_their_person(self, tmp_path):
        s = _store(tmp_path)
        s.add_or_reinforce("likes_minecraft", "topic", member_id="kid_a")
        s.add_or_reinforce("likes_unicorns", "topic", member_id="kid_b")
        s.add_or_reinforce("pet_dog_rosie", "topic")
        assert s.tag_summary("kid_a") == ["likes_minecraft", "pet_dog_rosie"]
        assert s.tag_summary("kid_b") == ["likes_unicorns", "pet_dog_rosie"]
        assert s.tag_summary(None) == ["pet_dog_rosie"]

    def test_name_needs_a_recognised_person(self, tmp_path):
        s = _store(tmp_path)
        assert not s.add_or_reinforce("child_name_owen", "name")
        assert s.add_or_reinforce("child_name_owen", "name", member_id="kid_a")
        assert s.add_or_reinforce("child_name_mia", "name", member_id="kid_b")
        assert s.tag_summary("kid_a") == ["child_name_owen"]  # one name each, both kept

    def test_same_fact_is_per_person(self, tmp_path):
        s = _store(tmp_path)
        s.add_or_reinforce("likes_cats", "topic", member_id="kid_a")
        s.add_or_reinforce("likes_cats", "topic", member_id="kid_b")
        assert s.entry_count == 2

    def test_legacy_file_household_names_dropped(self, tmp_path):
        path = tmp_path / "mem.json"
        now = time.time()
        base = {"valence_bias": 0, "arousal_bias": 0, "initial_strength": 1.0,
                "created_ts": now, "last_reinforced_ts": now, "reinforcement_count": 1,
                "decay_lambda": 0.0, "source": "llm_extract"}  # fmt: skip
        path.write_text(json.dumps({"version": 1, "entries": [
            {**base, "tag": "child_name_owen", "category": "name"},
            {**base, "tag": "likes_minecraft", "category": "topic"},
        ]}))  # fmt: skip
        s = MemoryStore(str(path), consent=True)
        s.load()
        assert s.tag_summary(None) == ["likes_minecraft"]

    def test_forget_by_tag_and_member(self, tmp_path):
        s = _store(tmp_path)
        s.add_or_reinforce("likes_minecraft", "topic", member_id="kid_a")
        s.add_or_reinforce("likes_lego", "topic", member_id="kid_a")
        s.add_or_reinforce("pet_dog_rosie", "topic")
        assert s.forget(["likes_minecraft"]) == 1  # dashboard sends bare tags
        assert s.forget_member("kid_a") == 1
        assert s.tags_by_member() == {"": ["pet_dog_rosie"]}


class _Params:
    def __init__(self, **v):
        self.v = v

    def get_value(self, name, default=None):
        return self.v.get(name, default)

    def on_change(self, _cb):
        pass


def _loop():
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    loop = TickLoop(reflex=None, face=None, workers=workers, param_registry=_Params())
    loop.world.household_kinds = {"kid_a": "kid", "dad": "adult"}
    return loop


def _see(loop, *mids):
    loop.world.faces_held = [{"member_id": m, "range_mm": 800} for m in mids]
    loop.world.faces_seen_mono_ms = time.monotonic() * 1000.0


class TestResume:
    def test_first_conversation_is_fresh(self):
        assert _loop()._should_resume() is False

    def test_same_person_soon_continues(self):
        loop = _loop()
        _see(loop, "kid_a")
        loop._should_resume()
        loop._last_conv_mono = time.monotonic()
        assert loop._should_resume() is True

    def test_someone_else_starts_fresh(self):
        loop = _loop()
        _see(loop, "kid_a")
        loop._should_resume()
        loop._last_conv_mono = (
            time.monotonic() - 60
        )  # after a pause (quick = same talk)
        _see(loop, "dad")
        assert loop._should_resume() is False

    def test_unrecognised_counts_as_same(self):
        loop = _loop()
        _see(loop, "kid_a")
        loop._should_resume()
        loop._last_conv_mono = time.monotonic()
        _see(loop, "kid_a", "dad")  # two faces: speaker unknown
        assert loop._should_resume() is True

    def test_long_gap_starts_fresh(self):
        loop = _loop()
        loop._last_conv_mono = time.monotonic() - 600
        assert loop._should_resume() is False


class TestPickMemory:
    def test_speaker_facts_then_household(self):
        loop = _loop()
        _see(loop, "kid_a")
        p = {"memory_by_member": {"kid_a": ["likes_minecraft"], "": ["pet_dog_rosie"],
                                  "kid_b": ["likes_unicorns"]}}  # fmt: skip
        loop._pick_memory(p)
        assert p["memory_tags"] == ["likes_minecraft", "pet_dog_rosie"]
        assert p["memory_scope"] == "speaker"
        assert "memory_by_member" not in p

    def test_nobody_recognised_household_only(self):
        loop = _loop()
        p = {"memory_by_member": {"kid_a": ["likes_minecraft"], "": ["pet_dog_rosie"]}}
        loop._pick_memory(p)
        assert p["memory_tags"] == ["pet_dog_rosie"]
        assert p["memory_scope"] == "household"


class TestHelperLeansIn:
    def test_quick_answer_from_someone_else_continues(self):
        """Dad leaned in to help Owen mid-Rocket-Math and the game was reset (2026-11-18)."""
        loop = _loop()
        _see(loop, "kid_a")
        loop._should_resume()
        loop._last_conv_mono = time.monotonic() - 3  # in the follow-up window
        _see(loop, "dad")
        assert loop._should_resume() is True
        assert loop._conv_member == "kid_a"  # still Owen's conversation

    def test_someone_else_after_a_pause_starts_fresh(self):
        loop = _loop()
        _see(loop, "kid_a")
        loop._should_resume()
        loop._last_conv_mono = time.monotonic() - 60
        _see(loop, "dad")
        assert loop._should_resume() is False
