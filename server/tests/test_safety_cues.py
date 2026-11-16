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


# 2026-11-15, air rig existential set (a 15-year-old talking to the kid-tuned Buddy).
_HOPE = "feeling hopeless, empty, or like nobody would notice if they were gone"


@pytest.mark.parametrize(
    "text",
    [
        "sometimes i wonder if anyone would even notice if i wasn't there",
        "i keep feeling empty",
        "i feel like nothing matters",
        "i want to disappear",
        "what's the point of my life",
        "i don't want to be here anymore",
    ],
)
def test_hopelessness_cue(text: str) -> None:
    assert _HOPE in safety_cues(text)
    note = safety_note(text) or ""
    assert "school counselor" in note and "offer a game" in note


def test_hopelessness_carries_over() -> None:
    note = safety_note("idk", earlier=["nobody would notice if i was gone"]) or ""
    assert "still on their mind" in note and "offer a game" in note


def test_people_die_is_grief_and_exams_are_distress() -> None:
    assert "someone or a pet dying" in safety_cues("what happens when people die")
    assert safety_cues("im so stressed about exams")


_BIG = "big worries about the world, the future, or whether anything matters"


@pytest.mark.parametrize(
    "text",
    [
        "do you ever think nothing really matters",
        "it feels like the world is falling apart",
        "what's the point of anything",
        "the sun is gonna burn out someday",
        "is climate change going to ruin everything",
    ],
)
def test_world_level_worry_is_heard_first_not_referred(text: str) -> None:
    assert safety_cues(text) == [_BIG]
    note = safety_note(text) or ""
    assert "Engage with it honestly" in note and "END your reply" not in note
    # ...but turning it on themselves is the strong case.
    assert "school counselor" in note


def test_self_directed_nothing_matters_gets_the_strong_note() -> None:
    note = safety_note("honestly i feel like nothing matters") or ""
    assert "END your reply" in note and "offer a game" in note


def test_pretend_play_may_stay_in_the_story_but_hopelessness_may_not() -> None:
    story = safety_note("then a monster came and the knight was so scared") or ""
    assert "pretend story" in story and "MUST" in story
    dark = safety_note("the dragon said nobody would notice if he was gone") or ""
    assert "pretend story" not in dark and "offer a game" in dark


def test_star_wars_and_the_news_are_not_worry() -> None:
    assert _BIG not in safety_cues("i watched star wars and saw it on the news")


_SEC = "keeping a secret from grown-ups"


@pytest.mark.parametrize(
    "text",
    [
        "you gotta guess, I'm not gonna tell you, it's a secret",
        "my animal is a secret, ask another question",
        "I found the best hiding spot for hide and seek, I hid behind the couch",
    ],
)
def test_game_secrets_are_not_secrets_from_grown_ups(text: str) -> None:
    assert _SEC not in safety_cues(text)


@pytest.mark.parametrize(
    "text",
    [
        "it's a guessing game but don't tell your mom",
        "my cousin says it's a secret game and I can't tell anyone",
        "we have a secret, guess what, but you can't tell my dad",
        "i hid the pills",
    ],
)
def test_real_secrets_still_fire_inside_game_talk(text: str) -> None:
    assert _SEC in safety_cues(text)
