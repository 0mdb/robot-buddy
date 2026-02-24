"""Tests for conversation history, context budget, and response parsing."""

from __future__ import annotations

import json

import pytest

from app.llm.conversation import (
    ConversationHistory,
    ConversationResponseV2,
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
        # Add 10 turns (20 messages) — exceeds 8-turn recent window
        for i in range(10):
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
                "memory_tags": ["interested_in_science"],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.emotion == "curious"
        assert resp.mood_reason == "child asking about science"
        assert resp.memory_tags == ["interested_in_science"]

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

    def test_invalid_memory_tags_ignored(self):
        content = json.dumps(
            {
                "emotion": "happy",
                "intensity": 0.5,
                "text": "Hi",
                "memory_tags": [123, "", "valid_tag"],
            }
        )
        resp = parse_conversation_response_content(content)
        assert resp.memory_tags == ["valid_tag"]


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
