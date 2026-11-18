"""Server-chosen secrets for guessing games (app/llm/game_picks.py)."""

from __future__ import annotations

import random

from app.llm import game_picks
from app.llm.conversation import ConversationHistory
from app.llm.game_picks import CATEGORIES, GamePicks


def test_used_pick_is_replaced() -> None:
    g = GamePicks(random.Random(1))
    animal, food = g.picks["animal"], g.picks["food"]
    g.mark_used(f"Secret: {animal}. Said: has fur? yes")
    assert g.picks["animal"] != animal
    assert g.picks["food"] == food  # other kinds untouched


def test_unrelated_notes_keep_picks() -> None:
    g = GamePicks(random.Random(2))
    before = dict(g.picks)
    g.mark_used("Turn: child guessing. Said: lives in water? no")
    g.mark_used("")
    assert g.picks == before


def test_no_repeat_across_recent_games() -> None:
    for d in game_picks._RECENT.values():
        d.clear()
    rng = random.Random(3)
    seen = []
    for _ in range(10):
        g = GamePicks(rng)
        seen.append(g.picks["animal"])
    assert len(set(seen)) == 10


def test_lists_have_no_duplicates() -> None:
    for name, items in CATEGORIES.items():
        assert len(items) == len(set(items)), name


def test_state_block_carries_picks_and_updates() -> None:
    h = ConversationHistory()
    h.update_profile({"mood": "happy", "intensity": 0.5, "turn_id": 1, "valence": 0.2})
    h.add_user("let's play guess the animal, you pick")
    msgs = h.to_ollama_messages()
    text = "\n".join(str(m["content"]) for m in msgs)
    pick = h.game_picks.picks["animal"]
    assert f"animal: {pick}" in text
    h.add_assistant("Okay, I have one!", notes=f"Secret: {pick}")
    assert h.game_picks.picks["animal"] != pick
