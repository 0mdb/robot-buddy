"""AI worker side of a late resume: the dropped turn's messages are discarded until the
next end of utterance."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import AI_CMD_LATE_RESUME
from supervisor.workers.ai_worker import AIWorker


class _WS:
    def __init__(self, msgs: list[dict[str, Any]]) -> None:
        self._msgs = [json.dumps(m) for m in msgs]

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._msgs:
            raise StopAsyncIteration
        return self._msgs.pop(0)


_TURN = [
    {"type": "transcription", "text": "a dog"},
    {"type": "emotion", "emotion": "happy", "intensity": 0.5},
    {"type": "done"},
]


def _worker() -> tuple[AIWorker, list[str]]:
    w = AIWorker()
    sent: list[str] = []
    w.send = lambda t, p=None, **_: sent.append(t)  # type: ignore[method-assign]
    w._ws_send = AsyncMock()  # type: ignore[method-assign]
    return w, sent


@pytest.mark.asyncio
async def test_messages_of_the_dropped_turn_are_discarded() -> None:
    w, sent = _worker()
    await w.on_message(make_envelope(AI_CMD_LATE_RESUME, "core", 1, {}))
    w._ws = _WS(_TURN)
    await w._ws_read_loop()
    assert not [t for t in sent if t.startswith("ai.conversation")]
    w._ws_send.assert_any_call({"type": "resume"})


@pytest.mark.asyncio
async def test_the_next_end_of_utterance_listens_again() -> None:
    w, sent = _worker()
    await w.on_message(make_envelope(AI_CMD_LATE_RESUME, "core", 1, {}))
    await w._end_utterance()
    w._ws = _WS(_TURN)
    await w._ws_read_loop()
    assert "ai.conversation.transcription" in sent and "ai.conversation.done" in sent
