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
    assert "AUDIENCE: kid, 7, speaking. Speak for children aged 4-8." in block


def test_member_ids_never_reach_the_prompt():
    raw = {
        "present": [
            {"kind": "kid", "member": "kid_a", "name": "X-NAME", "confidence": 1.0}
        ]
    }
    block = render_audience_block(parse_audience(raw))
    assert "kid_a" not in block and "X-NAME" not in block


@pytest.mark.parametrize(
    "present",
    [
        [
            {"kind": "adult", "confidence": 0.95},
            {"kind": "kid", "confidence": 0.9},
        ],  # rule 2
        [{"kind": "adult", "confidence": 0.3}],  # rule 1: low confidence is a kid
        [{"kind": "unknown", "confidence": 1.0}],  # rule 1
        [{"kind": "animal", "confidence": 0.9}],
        [],
    ],
)
def test_fallbacks_land_on_the_child_profile(present):
    assert (
        resolve_profile(parse_audience({"present": present})).id == DEFAULT_PROFILE_ID
    )


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
