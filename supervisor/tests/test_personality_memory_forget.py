"""MemoryStore.forget: drop specific tags, keep the rest (parent removal; eval cleanup)."""

from __future__ import annotations

from pathlib import Path

from supervisor.personality.memory import MemoryStore


def test_forget_drops_only_named_tags(tmp_path: Path) -> None:
    store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
    for tag in ("likes_dinosaurs", "cat_pepper", "dog_name_rocket"):
        store.add_or_reinforce(tag, "topic")
    assert store.forget(["cat_pepper", "dog_name_rocket", "not_there"]) == 2
    assert store.tag_summary() == ["likes_dinosaurs"]
    reloaded = MemoryStore(str(tmp_path / "mem.json"), consent=True)
    reloaded.load()
    assert reloaded.tag_summary() == ["likes_dinosaurs"]


def test_tag_summary_puts_recent_first(tmp_path: Path) -> None:
    import time

    store = MemoryStore(str(tmp_path / "mem.json"), consent=True)
    for tag in ("old_one", "older_greeting", "cat_pepper"):
        store.add_or_reinforce(tag, "topic")
        time.sleep(0.01)
    store.add_or_reinforce("old_one", "topic")  # reinforced last
    assert store.tag_summary()[:2] == ["old_one", "cat_pepper"]
