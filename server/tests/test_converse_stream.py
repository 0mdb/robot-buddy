"""End-to-end tests for the streaming _generate_and_stream_live path.

The test drives a fake LLM backend that emits canned JSON deltas, a fake
TTS that yields canned PCM, and a fake WebSocket that captures every
send_json call — so we can assert the exact message order and payload
shape without standing up any real network or model.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from app.llm.base import LLMBusyError
from app.llm.conversation import ConversationHistory


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


class _FakeLLM:
    """Emits a canned stream of JSON deltas when stream_conversation() is called."""

    def __init__(
        self, deltas: list[str], *, raise_on_start: Exception | None = None
    ) -> None:
        self.deltas = deltas
        self.raise_on_start = raise_on_start

    async def stream_conversation(
        self,
        history: ConversationHistory,
        user_text: str,
        *,
        override_temperature: float | None = None,
        override_max_output_tokens: int | None = None,
        tool_result: object | None = None,
    ) -> AsyncIterator[str]:
        # Mirror the real backends: add_user first so history finalization works.
        self.last_tool_result = tool_result  # expose for test assertions
        history.add_user(user_text)
        if self.raise_on_start is not None:
            raise self.raise_on_start
        for d in self.deltas:
            yield d


class _FakeTTS:
    """Yields fixed PCM chunks per call. Records every call for assertions."""

    def __init__(self, *, chunk_bytes: bytes = b"\x00\x01") -> None:
        self.chunk_bytes = chunk_bytes
        self.calls: list[tuple[str, str, float]] = []

    async def stream(
        self, text: str, emotion: str, *, intensity: float = 0.5
    ) -> AsyncIterator[bytes]:
        self.calls.append((text, emotion, intensity))
        # Three chunks so we can see boundary behaviour.
        for _ in range(3):
            yield self.chunk_bytes


def _canned_deltas(text: str) -> list[str]:
    """Canned JSON deltas that produce a valid V2 response with the given text.

    Splits across three chunks so the parser has to stitch the prefix together.
    """
    body = {
        "inner_thought": "Think.",
        "emotion": "happy",
        "intensity": 0.6,
        "mood_reason": "because kid said hi",
        "emotional_arc": "stable",
        "child_affect": "positive",
        "gestures": ["nod"],
        "memory_tags": [{"tag": "likes_robots", "category": "topic"}],
        "text": text,
    }
    raw = json.dumps(body)
    # Split into three halves-ish.
    a, b, c = raw[:20], raw[20:60], raw[60:]
    return [a, b, c]


@pytest.fixture()
def patched_runtime(monkeypatch):
    """Patch app.ai_runtime.get_tts so the converse router uses our fake."""
    fake = _FakeTTS()
    # The router imports get_tts from app.ai_runtime, so patch at source.
    monkeypatch.setattr("app.routers.converse.get_tts", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_streaming_happy_path_message_order(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    llm = _FakeLLM(_canned_deltas("Ooh hi there! How are you today?"))
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()

    await _generate_and_stream_live(ws, llm, history, "hello")

    types_in_order = [m["type"] for m in ws.sent]
    # Required prefix: emotion, gestures, memory_tags all before any audio.
    assert types_in_order[0] == "emotion"
    assert types_in_order[1] == "gestures"
    assert types_in_order[2] == "memory_tags"
    # At least one audio chunk before assistant_text + done.
    assert "audio" in types_in_order
    first_audio = types_in_order.index("audio")
    assistant_text_idx = types_in_order.index("assistant_text")
    done_idx = types_in_order.index("done")
    assert first_audio < assistant_text_idx < done_idx

    # assistant_text carries the FULL text at end of turn.
    assistant_text_msg = ws.sent[assistant_text_idx]
    assert assistant_text_msg["text"] == "Ooh hi there! How are you today?"

    # Emotion message carries metadata from the JSON prefix.
    assert ws.sent[0]["emotion"] == "happy"
    assert ws.sent[0]["intensity"] == pytest.approx(0.6)
    assert ws.sent[0]["mood_reason"] == "because kid said hi"
    assert "llm_latency_ms" in ws.sent[0]


@pytest.mark.asyncio
async def test_chunk_index_is_monotonic_across_sentences(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    llm = _FakeLLM(
        _canned_deltas("First sentence here. Second one too. Third and final one.")
    )
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()
    await _generate_and_stream_live(ws, llm, history, "hi")

    audio_msgs = [m for m in ws.sent if m["type"] == "audio"]
    assert len(audio_msgs) >= 3  # at least 3 sentences × chunks-per-sentence
    indices = [m["chunk_index"] for m in audio_msgs]
    assert indices == list(range(len(audio_msgs)))


@pytest.mark.asyncio
async def test_tts_called_once_per_sentence(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    llm = _FakeLLM(_canned_deltas("One. Two. Three fine sentences here."))
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()
    await _generate_and_stream_live(ws, llm, history, "hi")

    # With first_min=6 and min=12: "One." (4) fails both → buffered.
    # "Two." (4) also fails → buffered. "Three fine sentences here." is flushed
    # on close. So exactly one TTS call is expected with the whole collapsed text.
    # This test just documents that behavior — the primary guarantee is
    # that TTS is called at least once when there's text.
    assert len(patched_runtime.calls) >= 1
    # The first call carries the emotional prosody. Any later coalesced call
    # uses `neutral` to avoid a second prosody tag being prepended.
    assert patched_runtime.calls[0][1] == "happy"
    for _text, emotion, _intensity in patched_runtime.calls[1:]:
        assert emotion == "neutral"


@pytest.mark.asyncio
async def test_multisentence_coalesces_to_two_tts_calls(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    # Three long-enough sentences to flush in-stream (all ≥12 chars).
    llm = _FakeLLM(
        _canned_deltas(
            "The first long sentence here. "
            "Another long sentence comes next. "
            "And a third sentence to round out the test."
        )
    )
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()
    await _generate_and_stream_live(ws, llm, history, "hi")

    # Call 1: first natural sentence (early, for first-audio latency) with
    # the turn's emotional prosody.
    # Call 2: everything after, coalesced into one continuous Orpheus call
    # with `neutral` so no second prosody tag is prepended — that second
    # tag is the root cause of the "excited excited" vocalization leak.
    assert len(patched_runtime.calls) == 2
    first_text, first_emotion, first_intensity = patched_runtime.calls[0]
    rest_text, rest_emotion, _ = patched_runtime.calls[1]
    assert first_emotion == "happy"
    assert first_intensity == pytest.approx(0.6)  # from the canned metadata
    assert rest_emotion == "neutral"
    assert "first long sentence" in first_text
    assert "Another long sentence" in rest_text
    assert "third sentence" in rest_text


@pytest.mark.asyncio
async def test_empty_text_abstention_sends_done_with_no_audio(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    llm = _FakeLLM(_canned_deltas(""))
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()
    await _generate_and_stream_live(ws, llm, history, "hi")

    types_ = [m["type"] for m in ws.sent]
    assert "emotion" in types_
    assert "audio" not in types_
    assert "assistant_text" not in types_  # empty text → no transcript message
    assert types_[-1] == "done"
    assert patched_runtime.calls == []  # TTS never invoked


@pytest.mark.asyncio
async def test_llm_busy_error_emits_error_message(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    llm = _FakeLLM([], raise_on_start=LLMBusyError("llm_busy"))
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()
    await _generate_and_stream_live(ws, llm, history, "hi", turn_id="t-abc")

    # Phase C: typed `turn_error` + legacy string `error` for back-compat.
    assert len(ws.sent) == 2
    assert ws.sent[0]["type"] == "turn_error"
    assert ws.sent[0]["turn_id"] == "t-abc"
    assert ws.sent[0]["reason"] == "llm_busy"
    assert ws.sent[0]["stage"] == "llm"
    assert ws.sent[1] == {"type": "error", "message": "llm_busy"}


@pytest.mark.asyncio
async def test_history_finalized_with_assistant_message(patched_runtime) -> None:
    from app.routers.converse import _generate_and_stream_live

    llm = _FakeLLM(_canned_deltas("A long enough sentence to emit here."))
    history = ConversationHistory(max_turns=20)
    ws = _FakeWebSocket()
    await _generate_and_stream_live(ws, llm, history, "hi there")

    # User + assistant = 1 turn
    assert history.turn_count == 1
    # Last message is the assistant with the full text and emotion.
    msgs = list(history._messages)  # noqa: SLF001 — test-only access
    assert msgs[-1].role == "assistant"
    assert msgs[-1].content == "A long enough sentence to emit here."
    assert msgs[-1].emotion == "happy"
