"""Audience profiles and the audience block (SIM-INTERACTION stage 0)."""

from __future__ import annotations

import pytest

from app.llm.audience import (
    DEFAULT_PROFILE_ID,
    available_profiles,
    load_profile,
    parse_audience,
    render_audience_block,
    resolve_profile,
)
from app.llm.conversation import CONVERSATION_SYSTEM_PROMPT, _build_current_state_block
from app.llm.prompts import SYSTEM_PROMPT


def test_both_prompts_take_the_age_from_one_profile():
    who = load_profile(DEFAULT_PROFILE_ID).who
    assert who == "children aged 4-8"
    assert who in CONVERSATION_SYSTEM_PROMPT
    assert who in SYSTEM_PROMPT
    assert "5–12" not in SYSTEM_PROMPT


def test_every_profile_file_loads():
    for pid in available_profiles():
        assert load_profile(pid).id == pid


def test_no_audience_means_todays_prompt():
    profile = {"mood": "happy", "valence": 0.3}
    assert "AUDIENCE" not in _build_current_state_block(profile)
    assert render_audience_block(None) == ""


def test_oracle_audience_is_rendered():
    block = _build_current_state_block(
        {
            "audience": {
                "present": [{"kind": "kid", "age": 7, "confidence": 1.0}],
                "speaking": 0,
            }
        }
    )
    assert "AUDIENCE: kid, 7, speaking. Speak for children aged 6-9." in block


def test_member_ids_never_reach_the_prompt():
    raw = {
        "present": [
            {"kind": "kid", "member": "kid_a", "name": "X-NAME", "confidence": 1.0}
        ]
    }
    block = render_audience_block(parse_audience(raw))
    assert "kid_a" not in block and "X-NAME" not in block


@pytest.mark.parametrize(
    "present,expected",
    [
        ([], "child"),
        ([{"kind": "kid", "confidence": 0.9}], "child"),  # rule 1: age unknown
        ([{"kind": "unknown", "confidence": 1.0}], "child"),  # rule 1
        (
            [{"kind": "adult", "confidence": 0.3}],
            "child",
        ),  # rule 1: low confidence is a kid
        ([{"kind": "kid", "age": 5, "confidence": 0.9}], "kid_5"),
        ([{"kind": "kid", "age": 7, "confidence": 0.9}], "kid_7"),
        ([{"kind": "kid", "age": 2, "confidence": 0.9}], "kid_5"),  # nearest band
        ([{"kind": "kid", "age": 11, "confidence": 0.9}], "kid_7"),
        # rule 2: the youngest present governs; one adult does not switch to adult mode
        (
            [
                {"kind": "kid", "age": 7, "confidence": 0.9},
                {"kind": "kid", "age": 5, "confidence": 0.9},
            ],
            "kid_5",
        ),
        (
            [
                {"kind": "adult", "confidence": 0.95},
                {"kind": "kid", "age": 7, "confidence": 0.9},
            ],
            "kid_7",
        ),
        (
            [{"kind": "adult", "confidence": 0.95}, {"kind": "kid", "confidence": 0.9}],
            "child",
        ),
        ([{"kind": "adult", "confidence": 0.95}], "adult"),
        (
            [
                {"kind": "adult", "confidence": 0.95},
                {"kind": "animal", "confidence": 0.9},
            ],
            "adult",
        ),
        ([{"kind": "animal", "confidence": 0.9}], "animal"),  # rule 3
        (
            [
                {"kind": "animal", "confidence": 0.9},
                {"kind": "unknown", "confidence": 0.9},
            ],
            "child",
        ),
    ],
)
def test_fallback_rules(present, expected):
    assert resolve_profile(parse_audience({"present": present})).id == expected


def test_low_confidence_is_marked_unsure():
    block = render_audience_block(
        parse_audience({"present": [{"kind": "adult", "confidence": 0.2}]})
    )
    assert "adult, unsure" in block


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "kid",
        [],
        {"present": "kid"},
        {"present": [1, None]},
        {"speaking": 5, "present": []},
    ],
)
def test_malformed_audience_is_dropped_not_guessed(raw):
    a = parse_audience(raw)
    assert a is None or (
        all(m.kind in ("kid", "adult", "animal", "unknown") for m in a.present)
    )
    _build_current_state_block({"audience": raw})  # never raises


def test_bad_kind_and_age_are_sanitised():
    a = parse_audience(
        {"present": [{"kind": "robot", "age": True, "confidence": "x"}], "speaking": 0}
    )
    assert a is not None
    (m,) = a.present
    assert (m.kind, m.age, m.confidence) == ("unknown", None, 0.0)


def test_every_profile_prompt_carries_the_same_safety_and_honesty():
    from app.llm.conversation import build_system_prompt

    def section(prompt: str, name: str, until: str) -> str:
        return prompt[prompt.index(name) : prompt.index(until)]

    base = build_system_prompt("child")
    for pid in available_profiles():
        p = build_system_prompt(pid)
        assert section(p, "SAFETY (", "RESPONSE FORMAT") == section(
            base, "SAFETY (", "RESPONSE FORMAT"
        )
        assert (
            'User: "A man said he has kittens' in p
        )  # safety examples are not a profile field
        assert "<<" not in p
        for line in load_profile(pid).speech:
            assert f"- {line}" in p


def test_profiles_differ_where_they_should():
    from app.llm.conversation import build_system_prompt

    assert "about 5" in build_system_prompt("kid_5")
    assert "talking with an adult" in build_system_prompt("adult")
    assert "Do not use words" in build_system_prompt("animal")
    assert build_system_prompt("child") == CONVERSATION_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "kind,has_check", [("kid", True), ("adult", False), ("animal", False)]
)
def test_safety_nudges_are_for_children_only(kind, has_check):
    from app.llm.conversation import SAFETY_CHECK, ConversationHistory

    h = ConversationHistory()
    h.update_profile(
        {"audience": {"present": [{"kind": kind, "age": 7, "confidence": 1.0}]}}
    )
    h.add_user("I'm scared of the pills")
    systems = "\n".join(
        m["content"] for m in h.to_ollama_messages() if m["role"] == "system"
    )
    assert (SAFETY_CHECK in systems) is has_check
    assert ("SAFETY: the child" in systems) is has_check
