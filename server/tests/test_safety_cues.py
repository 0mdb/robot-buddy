"""Safety cues and the per-turn note (SIM-INTERACTION stage 1, findings B1-B6)."""

from __future__ import annotations

import pytest

from app.llm.conversation import (
    SAFETY_CHECK,
    ConversationHistory,
    ConversationResponseV2,
)
from app.llm.safety_cues import safety_cues, safety_note


@pytest.mark.parametrize(
    "text",
    [
        "a man at the park said he has puppies in his car",
        "he said not to tell my mom",
        "I found little white pills in the bag",
        "the big kid pushes me every day",
        "I think everybody hates me",
        "my arm really hurts",
        "my friend in the game wants to know where I live",
    ],
)
def test_cues_fire(text):
    assert safety_cues(text)


@pytest.mark.parametrize(
    "text", ["why is the sky blue", "do you like cats", "I'm gonna be a dinosaur"]
)
def test_cues_quiet_on_ordinary_talk(text):
    assert safety_note(text) is None


def _systems(h: ConversationHistory) -> list[str]:
    return [m["content"] for m in h.to_ollama_messages() if m["role"] == "system"]


def test_note_sits_right_before_the_childs_message():
    h = ConversationHistory()
    h.update_profile({"mood": "neutral"})
    h.add_user("a lady said come see her kittens in her van")
    msgs = h.to_ollama_messages()
    assert msgs[-1]["role"] == "user"
    assert msgs[-2]["role"] == "system" and msgs[-2]["content"].startswith("SAFETY:")


def test_no_note_for_ordinary_talk_but_the_check_is_always_in_state():
    h = ConversationHistory()
    h.update_profile({"mood": "neutral"})
    h.add_user("why is the sky blue")
    systems = _systems(h)
    assert not any(s.startswith("SAFETY:") for s in systems)
    assert any(SAFETY_CHECK in s for s in systems)


def test_guided_schema_requires_spoken_text():
    schema = ConversationResponseV2.model_json_schema()
    assert "text" in schema["required"]
    assert schema["properties"]["text"]["minLength"] == 1
    assert ConversationResponseV2().text == ""  # parsing stays lenient


# ── Grief (operator, 2026-11-10: mild grief needs a grown-up every time) ──────


@pytest.mark.parametrize(
    "text",
    [
        "my fish died this morning",
        "my grandpa died",
        "we had to put our dog to sleep yesterday",
        "mommy says hes dead",
        "I miss my nana",
        "is grandma in heaven now",
    ],
)
def test_grief_fires(text: str) -> None:
    assert "someone or a pet dying" in safety_cues(text)


@pytest.mark.parametrize(
    "text",
    [
        "I died in Minecraft",
        "my character died on level 3",
        "zombies are dead already lol",
    ],
)
def test_game_deaths_are_not_grief(text: str) -> None:
    assert "someone or a pet dying" not in safety_cues(text)


def test_grief_carries_over_for_three_turns_only() -> None:
    first = "my fish died this morning"
    note = safety_note("I keep thinking about him", [first])
    assert (
        note is not None
        and "earlier the child mentioned someone or a pet dying" in note
    )
    assert "trusted grown-up" in note
    assert safety_note("can we play a game", [first, "ok", "yes", "hmm"]) is None
    # Other cues do not carry over.
    assert safety_note("ok", ["a stranger said hi"]) is None
