"""Tests for conversation history, context budget, and response parsing."""

from __future__ import annotations

import json

import pytest

from app.llm.conversation import (
    PERSONALITY_ANCHOR,
    ConversationHistory,
    ConversationResponseV2,
    _build_current_state_block,
    _compress_turns,
    parse_conversation_response_content,
)


# ── Context Budget ─────────────────────────────────────────────────────


class TestContextBudget:
    """ConversationHistory context-budget compression (PE spec §12.6)."""

    def test_few_turns_no_compression(self):
        h = ConversationHistory(max_turns=20)
        h.add_user("hello")
        h.add_assistant("hi there", emotion="happy")
        msgs = h.to_ollama_messages()
        # system + user + assistant = 3
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert msgs[1]["content"] == "hello"
        assert msgs[2]["content"] == "hi there"

    def test_compression_kicks_in_beyond_8_turns(self):
        h = ConversationHistory(max_turns=30)
        # Add 9 turns (18 messages) — exceeds 8-turn recent window.
        # Use 9 (not 10) to avoid the personality anchor at every-5-turn boundary.
        for i in range(9):
            h.add_user(f"question {i}")
            h.add_assistant(f"answer {i}", emotion="happy")

        msgs = h.to_ollama_messages()
        # Should have: system + summary + 16 recent messages
        roles = [m["role"] for m in msgs]
        assert roles[0] == "system"
        # Second message should be the summary (also system role)
        assert roles[1] == "system"
        assert "Earlier conversation" in msgs[1]["content"]
        # Recent window: 8 turns × 2 = 16 messages
        assert len(msgs) == 2 + 16  # system + summary + 16 recent

    def test_summary_includes_topic_and_emotion(self):
        h = ConversationHistory(max_turns=30)
        for i in range(10):
            h.add_user(f"Tell me about dinosaurs topic {i}")
            h.add_assistant(f"Dinosaurs are cool {i}", emotion="curious")

        msgs = h.to_ollama_messages()
        summary = msgs[1]["content"]
        assert "dinosaurs" in summary.lower()
        assert "curious" in summary

    def test_emotion_stored_with_assistant(self):
        h = ConversationHistory(max_turns=5)
        h.add_user("hello")
        h.add_assistant("hi!", emotion="happy")
        assert h._messages[-1].emotion == "happy"

    def test_token_budget_enforcement(self):
        """Very long messages should be trimmed to fit budget."""
        # Budget 2048: system prompt ~800 tokens + 512 reserve = ~1536 usable.
        # The long message (~2000 tokens) should be dropped to stay within budget.
        h = ConversationHistory(max_turns=20, max_context_tokens=2048)
        long_text = "x" * 8000  # ~2000 tokens
        h.add_user(long_text)
        h.add_assistant("ok", emotion="neutral")
        h.add_user("short follow-up")
        msgs = h.to_ollama_messages()
        # The long user message should have been dropped to fit budget
        contents = [m["content"] for m in msgs if m["role"] != "system"]
        assert long_text not in contents
        assert "short follow-up" in contents

    def test_turn_count_correct(self):
        h = ConversationHistory(max_turns=20)
        assert h.turn_count == 0
        h.add_user("a")
        assert h.turn_count == 1
        h.add_assistant("b", emotion="neutral")
        assert h.turn_count == 1
        h.add_user("c")
        assert h.turn_count == 2


class TestCompressTurns:
    """Tests for _compress_turns helper."""

    def test_empty(self):
        assert _compress_turns([]) == ""

    def test_single_turn(self):
        from app.llm.conversation import ConversationMessage

        msgs = [
            ConversationMessage(role="user", content="Why is the sky blue?"),
            ConversationMessage(
                role="assistant", content="Because of scattering", emotion="curious"
            ),
        ]
        result = _compress_turns(msgs)
        assert "turn 1" in result
        assert "sky blue" in result.lower()
        assert "curious" in result

    def test_long_topic_truncated(self):
        from app.llm.conversation import ConversationMessage

        msgs = [
            ConversationMessage(
                role="user",
                content="A" * 60,
            ),
            ConversationMessage(role="assistant", content="ok", emotion="neutral"),
        ]
        result = _compress_turns(msgs)
        assert "..." in result


# ── Response Parsing ───────────────────────────────────────────────────


class TestParseV2Response:
    """parse_conversation_response_content with v2 fields."""

    def test_v2_fields_parsed(self):
        content = json.dumps(
            {
                "inner_thought": "Science question",
                "emotion": "curious",
                "intensity": 0.6,
                "mood_reason": "child asking about science",
                "emotional_arc": "rising",
                "child_affect": "positive",
                "text": "Great question!",
                "gestures": ["nod"],
                "memory_tags": [{"tag": "interested_in_science", "category": "topic"}],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.emotion == "curious"
        assert resp.mood_reason == "child asking about science"
        assert resp.memory_tags == [
            {"tag": "interested_in_science", "category": "topic"}
        ]

    def test_v1_response_still_works(self):
        content = json.dumps(
            {
                "emotion": "happy",
                "intensity": 0.8,
                "text": "Hello!",
                "gestures": [],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.emotion == "happy"
        assert resp.mood_reason == ""
        assert resp.memory_tags == []

    def test_unknown_emotion_defaults_to_neutral(self):
        content = json.dumps(
            {
                "emotion": "terrified",
                "intensity": 0.5,
                "text": "Oh no",
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.emotion == "neutral"

    def test_legacy_string_memory_tags(self):
        """Legacy v2 responses with bare string memory_tags are upgraded."""
        content = json.dumps(
            {
                "emotion": "happy",
                "intensity": 0.5,
                "text": "Hi",
                "memory_tags": ["likes_dinosaurs", "child_name_emma"],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.memory_tags == [
            {"tag": "likes_dinosaurs", "category": "topic"},
            {"tag": "child_name_emma", "category": "topic"},
        ]

    def test_invalid_memory_tags_ignored(self):
        content = json.dumps(
            {
                "emotion": "happy",
                "intensity": 0.5,
                "text": "Hi",
                "memory_tags": [123, "", {"tag": "valid_tag", "category": "topic"}],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.memory_tags == [{"tag": "valid_tag", "category": "topic"}]

    def test_invalid_category_defaults_to_topic(self):
        content = json.dumps(
            {
                "emotion": "happy",
                "intensity": 0.5,
                "text": "Hi",
                "memory_tags": [{"tag": "some_tag", "category": "invalid_tier"}],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.memory_tags == [{"tag": "some_tag", "category": "topic"}]

    def test_confused_emotion_round_trip(self):
        """'confused' is a canonical emotion — should not be defaulted to neutral."""
        content = json.dumps(
            {
                "emotion": "confused",
                "intensity": 0.5,
                "text": "Hmm, I'm not sure about that.",
                "mood_reason": "child asked ambiguous question",
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.emotion == "confused"
        assert resp.mood_reason == "child asked ambiguous question"

    def test_v2_full_payload_parses_without_error(self):
        """A full v2 payload (with emotional_arc/child_affect) parses gracefully.

        emotional_arc and child_affect live on the Pydantic ConversationResponseV2
        model for guided decoding; parse_conversation_response_content extracts the
        subset that ConversationResponse carries — ensure no crash on extra fields.
        """
        content = json.dumps(
            {
                "inner_thought": "They seem upset",
                "emotion": "sad",
                "intensity": 0.4,
                "mood_reason": "child expressed frustration",
                "emotional_arc": "falling",
                "child_affect": "negative",
                "text": "I'm sorry you feel that way.",
                "gestures": [],
                "memory_tags": [],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.emotion == "sad"
        assert resp.mood_reason == "child expressed frustration"


# ── ConversationResponseV2 Schema ──────────────────────────────────────


class TestConversationResponseV2:
    """Pydantic model validation."""

    def test_schema_has_all_fields(self):
        schema = ConversationResponseV2.model_json_schema()
        props = schema["properties"]
        assert "inner_thought" in props
        assert "emotion" in props
        assert "intensity" in props
        assert "mood_reason" in props
        assert "emotional_arc" in props
        assert "child_affect" in props
        assert "text" in props
        assert "gestures" in props
        assert "memory_tags" in props

    def test_defaults(self):
        r = ConversationResponseV2()
        assert r.emotion == "neutral"
        assert r.intensity == 0.5
        assert r.emotional_arc == "stable"
        assert r.child_affect == "neutral"

    def test_intensity_clamped(self):
        with pytest.raises(Exception):
            ConversationResponseV2(intensity=1.5)

    def test_emotional_arc_literals(self):
        for arc in ("rising", "stable", "falling", "peak", "recovery"):
            r = ConversationResponseV2(emotional_arc=arc)
            assert r.emotional_arc == arc

    def test_guided_decoding_schema_structure(self):
        """JSON schema has all 9 v2 fields with correct types for guided decoding."""
        schema = ConversationResponseV2.model_json_schema()
        props = schema["properties"]
        # All 9 fields present
        expected_fields = {
            "inner_thought",
            "emotion",
            "intensity",
            "mood_reason",
            "emotional_arc",
            "child_affect",
            "text",
            "gestures",
            "memory_tags",
        }
        assert expected_fields.issubset(set(props.keys()))
        # Type spot-checks
        assert props["emotion"]["type"] == "string"
        assert props["intensity"]["type"] == "number"
        assert props["text"]["type"] == "string"
        assert props["gestures"]["type"] == "array"
        assert props["memory_tags"]["type"] == "array"


# ── Personality Profile Injection (PE spec S2 §12.5, §12.7) ────────────


class TestBuildCurrentStateBlock:
    """Test the CURRENT STATE system block builder."""

    def test_basic_output(self):
        block = _build_current_state_block(
            {"mood": "curious", "intensity": 0.4, "turn_id": 5, "valence": 0.3}
        )
        assert "CURRENT STATE" in block
        assert "curious" in block
        assert "0.4" in block
        assert "turn: 5" in block

    def test_positive_valence_arc(self):
        block = _build_current_state_block({"valence": 0.5})
        assert "gently positive" in block

    def test_negative_valence_arc(self):
        block = _build_current_state_block({"valence": -0.5})
        assert "slightly tense" in block

    def test_neutral_valence_arc(self):
        block = _build_current_state_block({"valence": 0.0})
        assert "calm and neutral" in block

    def test_negative_mood_continuity(self):
        block = _build_current_state_block({"mood": "sad", "valence": -0.3})
        assert "recovery" in block

    def test_positive_mood_continuity(self):
        block = _build_current_state_block({"mood": "happy", "valence": 0.3})
        assert "positive trajectory" in block

    def test_memory_context_included(self):
        block = _build_current_state_block(
            {
                "mood": "happy",
                "intensity": 0.5,
                "turn_id": 3,
                "valence": 0.2,
                "memory_tags": ["likes_dinosaurs", "child_name_emma"],
            }
        )
        assert "Known about this child" in block
        assert "likes dinosaurs" in block
        assert "child name emma" in block

    def test_no_memory_tags_no_memory_line(self):
        block = _build_current_state_block(
            {"mood": "neutral", "intensity": 0.3, "turn_id": 1, "valence": 0.0}
        )
        assert "Known about this child" not in block

    def test_defaults_for_missing_fields(self):
        block = _build_current_state_block({})
        assert "CURRENT STATE" in block
        assert "neutral" in block


class TestProfileInjection:
    """Test profile injection into ConversationHistory messages."""

    def test_no_profile_no_injection(self):
        h = ConversationHistory(max_turns=20)
        h.add_user("hello")
        h.add_assistant("hi", emotion="happy")
        msgs = h.to_ollama_messages()
        # No CURRENT STATE block when no profile set
        assert not any("CURRENT STATE" in m["content"] for m in msgs)

    def test_profile_injected_before_last_user_message(self):
        h = ConversationHistory(max_turns=20)
        h.update_profile(
            {"mood": "curious", "intensity": 0.4, "turn_id": 1, "valence": 0.2}
        )
        h.add_user("why is the sky blue?")
        msgs = h.to_ollama_messages()
        # Find the CURRENT STATE block
        state_msgs = [m for m in msgs if "CURRENT STATE" in m["content"]]
        assert len(state_msgs) == 1
        # Should be a system message
        assert state_msgs[0]["role"] == "system"
        # Should appear before the user message
        state_idx = msgs.index(state_msgs[0])
        user_idx = next(i for i, m in enumerate(msgs) if m["role"] == "user")
        assert state_idx < user_idx

    def test_profile_updated_between_turns(self):
        h = ConversationHistory(max_turns=20)
        h.update_profile(
            {"mood": "neutral", "intensity": 0.3, "turn_id": 1, "valence": 0.0}
        )
        h.add_user("hello")
        h.add_assistant("hi!", emotion="happy")
        # Update profile before second turn
        h.update_profile(
            {"mood": "happy", "intensity": 0.6, "turn_id": 2, "valence": 0.4}
        )
        h.add_user("tell me a joke")
        msgs = h.to_ollama_messages()
        state_msgs = [m for m in msgs if "CURRENT STATE" in m["content"]]
        assert len(state_msgs) == 1
        # Should reflect the latest profile
        assert "happy" in state_msgs[0]["content"]


class TestPersonalityAnchor:
    """Test the personality anchor injection every 5 turns (§12.7)."""

    def test_no_anchor_before_5_turns(self):
        h = ConversationHistory(max_turns=20)
        for i in range(1, 4):  # 3 turns
            h.add_user(f"message {i}")
            h.add_assistant(f"response {i}", emotion="happy")
        h.add_user("message 4")
        msgs = h.to_ollama_messages()
        assert not any(PERSONALITY_ANCHOR in m["content"] for m in msgs)

    def test_anchor_at_5_turns(self):
        h = ConversationHistory(max_turns=20)
        for i in range(1, 6):  # 5 turns
            h.add_user(f"message {i}")
            h.add_assistant(f"response {i}", emotion="happy")
        # turn_count is now 5 — next to_ollama_messages should include anchor
        msgs = h.to_ollama_messages()
        anchor_msgs = [m for m in msgs if PERSONALITY_ANCHOR in m["content"]]
        assert len(anchor_msgs) == 1
        assert anchor_msgs[0]["role"] == "system"

    def test_anchor_at_10_turns(self):
        h = ConversationHistory(max_turns=20)
        for i in range(1, 11):  # 10 turns
            h.add_user(f"message {i}")
            h.add_assistant(f"response {i}", emotion="happy")
        msgs = h.to_ollama_messages()
        anchor_msgs = [m for m in msgs if PERSONALITY_ANCHOR in m["content"]]
        assert len(anchor_msgs) == 1

    def test_anchor_and_profile_both_present(self):
        h = ConversationHistory(max_turns=20)
        h.update_profile(
            {"mood": "curious", "intensity": 0.4, "turn_id": 5, "valence": 0.2}
        )
        for i in range(1, 6):  # 5 turns
            h.add_user(f"message {i}")
            h.add_assistant(f"response {i}", emotion="happy")
        msgs = h.to_ollama_messages()
        # Both should be present
        assert any("CURRENT STATE" in m["content"] for m in msgs)
        assert any(PERSONALITY_ANCHOR in m["content"] for m in msgs)
