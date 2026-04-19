"""Tests for the streaming conversation parser.

The parser carries the conversion from an LLM token stream (partial JSON)
to a sequence of (metadata, sentences) events. Failures here would mean
sentence boundaries misaligning or metadata arriving late, both of which
are directly audible as bad pacing or wrong-face-before-speech issues.
"""

from __future__ import annotations

import json

import pytest

from app.llm.stream_parser import (
    ConversationStreamParser,
    MetadataReady,
    Sentence,
)


def _run(parser: ConversationStreamParser, chunks: list[str]) -> list:
    events: list = []
    for ch in chunks:
        events.extend(parser.feed(ch))
    events.extend(parser.close())
    return events


def _full_json(text: str, **overrides) -> str:
    """Build a V2-style JSON with ``text`` last, matching the reordered schema."""
    body = {
        "inner_thought": "thought",
        "emotion": "happy",
        "intensity": 0.6,
        "mood_reason": "because",
        "emotional_arc": "stable",
        "child_affect": "positive",
        "gestures": ["nod"],
        "memory_tags": [{"tag": "likes_x", "category": "topic"}],
        "text": text,
    }
    body.update(overrides)
    # Force field order by manually building — json.dumps preserves dict order in 3.7+.
    return json.dumps(body)


# ── Metadata extraction ───────────────────────────────────────────


def test_metadata_emitted_before_any_sentence() -> None:
    raw = _full_json("Hello there. How are you today?")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])

    assert isinstance(events[0], MetadataReady)
    assert events[0].response.emotion == "happy"
    assert events[0].response.gestures == ["nod"]
    assert events[0].response.memory_tags == [{"tag": "likes_x", "category": "topic"}]
    # Every subsequent event must be a Sentence.
    assert all(isinstance(e, Sentence) for e in events[1:])


def test_metadata_response_text_field_is_empty() -> None:
    """The metadata event must not leak the text (it's streamed separately)."""
    raw = _full_json("This is the spoken answer.")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])

    meta = events[0]
    assert isinstance(meta, MetadataReady)
    assert meta.response.text == ""


def test_false_positive_text_in_inner_thought_is_ignored() -> None:
    """If `"text"` appears inside the inner_thought string, the parser must
    not prematurely transition — it should wait for the real top-level
    text key."""
    body = {
        "inner_thought": 'This mentions "text" but is not the key.',
        "emotion": "curious",
        "intensity": 0.5,
        "mood_reason": "r",
        "emotional_arc": "stable",
        "child_affect": "neutral",
        "gestures": [],
        "memory_tags": [],
        "text": "Real answer here.",
    }
    raw = json.dumps(body)
    parser = ConversationStreamParser()
    events = _run(parser, [raw])

    meta = events[0]
    assert isinstance(meta, MetadataReady)
    assert meta.response.emotion == "curious"
    # Parser accumulated just the real text value.
    assert "Real answer" in parser.full_text()


# ── Sentence segmentation ────────────────────────────────────────


def test_multiple_sentences_emitted_in_order() -> None:
    raw = _full_json("Ooh, that's fun! Tell me more. What else?")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])
    sentences = [e for e in events if isinstance(e, Sentence)]

    assert [s.text for s in sentences] == [
        "Ooh, that's fun!",
        "Tell me more.",
        "What else?",
    ]
    assert [s.index for s in sentences] == [0, 1, 2]


def test_char_by_char_chunks_yield_same_sentences() -> None:
    raw = _full_json("First sentence. Second one here.")
    parser = ConversationStreamParser()
    chunks = list(raw)  # one char per chunk
    events = _run(parser, chunks)
    sentences = [e.text for e in events if isinstance(e, Sentence)]

    assert sentences == ["First sentence.", "Second one here."]


def test_first_sentence_ships_at_lower_threshold() -> None:
    """Sentence 0 uses `first_min_chars=6`; subsequent use `min_chars=12`.

    ``Hi there!`` is 9 chars — passes first threshold, fails mid-stream threshold.
    """
    raw = _full_json("Hi there! I'm super happy to see you today.")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])
    sentences = [e.text for e in events if isinstance(e, Sentence)]

    assert sentences[0] == "Hi there!"
    assert sentences[1] == "I'm super happy to see you today."


def test_short_final_sentence_flushed_on_close() -> None:
    """A trailing fragment shorter than min_chars must still flush at close()."""
    raw = _full_json("A much longer first sentence. Hi!")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])
    sentences = [e.text for e in events if isinstance(e, Sentence)]

    assert "Hi!" in sentences[-1]


def test_ellipsis_counts_as_boundary() -> None:
    raw = _full_json("Hmm... let me think about that for a moment.")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])
    sentences = [e.text for e in events if isinstance(e, Sentence)]

    # The parser should split on the `...` + space.
    assert sentences[0].endswith("...")
    assert sentences[-1].endswith("moment.")


# ── Escape sequences ─────────────────────────────────────────────


def test_escaped_quote_does_not_terminate_text() -> None:
    raw = _full_json('She said "hello" to me. That was nice.')
    parser = ConversationStreamParser()
    _run(parser, [raw])
    assert parser.full_text() == 'She said "hello" to me. That was nice.'


def test_newline_escape_is_decoded() -> None:
    raw = _full_json("Line one. Line two ends here.")
    # Inject an escaped newline inside the text value by rebuilding.
    raw = raw.replace(
        "Line one. Line two ends here.", "Line one.\\nLine two ends here."
    )
    parser = ConversationStreamParser()
    events = _run(parser, [raw])

    text = parser.full_text()
    assert "\n" in text
    sentences = [e.text for e in events if isinstance(e, Sentence)]
    assert sentences[0] == "Line one."


def test_unicode_escape_is_decoded() -> None:
    # json.dumps with default ensure_ascii=True serialises "é" as `\u00e9`
    # in the wire format, which the parser must decode back.
    raw = _full_json("Café is nice here. Warm bread smells good.")
    assert "\\u00e9" in raw  # confirm the JSON actually contains the escape
    parser = ConversationStreamParser()
    _run(parser, [raw])

    assert "Café" in parser.full_text()


# ── Empty text / abstention ──────────────────────────────────────


def test_empty_text_emits_metadata_no_sentences() -> None:
    raw = _full_json("")
    parser = ConversationStreamParser()
    events = _run(parser, [raw])

    assert len(events) == 1
    assert isinstance(events[0], MetadataReady)
    assert parser.full_text() == ""


# ── Robustness ───────────────────────────────────────────────────


def test_chunk_boundary_inside_text_key() -> None:
    """The `"text":"` pattern can split across chunks; the parser must wait."""
    raw = _full_json("Hello world today.")
    # Split exactly between `"tex` and `t":"...`
    split_point = raw.find('"text"')
    a, b = raw[: split_point + 3], raw[split_point + 3 :]
    parser = ConversationStreamParser()
    events = _run(parser, [a, b])

    # Parser should have located the boundary and emitted everything.
    assert any(isinstance(e, MetadataReady) for e in events)
    assert parser.full_text() == "Hello world today."


def test_full_text_accumulates_across_sentences() -> None:
    raw = _full_json("One sentence here. Two sentences here now.")
    parser = ConversationStreamParser()
    _run(parser, [raw])
    assert parser.full_text() == "One sentence here. Two sentences here now."


def test_metadata_stays_available_after_close() -> None:
    raw = _full_json("Done.")
    parser = ConversationStreamParser()
    _run(parser, [raw])
    meta = parser.metadata()
    assert meta is not None
    assert meta.emotion == "happy"
    # After close(), metadata().text reflects full accumulated text.
    assert meta.text == "Done."


@pytest.mark.parametrize("chunk_size", [1, 2, 5, 13, 64])
def test_stable_across_chunk_sizes(chunk_size: int) -> None:
    raw = _full_json(
        "Ooh, dinosaurs! The T-Rex was really big. "
        "Did you know they had tiny arms? That's funny!"
    )
    chunks = [raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)]
    parser = ConversationStreamParser()
    events = _run(parser, chunks)
    sentences = [e.text for e in events if isinstance(e, Sentence)]
    assert sentences == [
        "Ooh, dinosaurs!",
        "The T-Rex was really big.",
        "Did you know they had tiny arms?",
        "That's funny!",
    ]
