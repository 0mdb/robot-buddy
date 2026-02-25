"""Conversation event capture for the /ws/conversation endpoint.

Only captures when at least one WS client is subscribed — zero overhead
in production.  Follows the ProtocolCapture per-client queue pattern.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    AI_CONVERSATION_ASSISTANT_TEXT,
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_FIRST_AUDIO,
    AI_CONVERSATION_GESTURE,
    AI_CONVERSATION_TRANSCRIPTION,
    AI_CONVERSATION_USER_TEXT,
    AI_CONVERSATION_ERROR,
    AI_STATE_CHANGED,
    CONV_BENCHMARK_DONE,
    CONV_BENCHMARK_PROGRESS,
    CONV_SESSION_ENDED,
    CONV_SESSION_STARTED,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_OWW_SCORE,
    EAR_EVENT_WAKE_WORD,
    PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
    PERSONALITY_STATE_SNAPSHOT,
    TTS_BENCHMARK_DONE,
    TTS_BENCHMARK_PROGRESS,
    TTS_EVENT_FINISHED,
    TTS_EVENT_STARTED,
)

log = logging.getLogger(__name__)

# Event types forwarded to conversation dashboard clients
_CONVERSATION_TYPES: frozenset[str] = frozenset(
    {
        AI_CONVERSATION_TRANSCRIPTION,
        AI_CONVERSATION_EMOTION,
        AI_CONVERSATION_GESTURE,
        AI_CONVERSATION_DONE,
        AI_CONVERSATION_FIRST_AUDIO,
        AI_CONVERSATION_ASSISTANT_TEXT,
        AI_CONVERSATION_USER_TEXT,
        AI_CONVERSATION_ERROR,
        AI_STATE_CHANGED,
        EAR_EVENT_WAKE_WORD,
        EAR_EVENT_END_OF_UTTERANCE,
        TTS_EVENT_STARTED,
        TTS_EVENT_FINISHED,
        TTS_BENCHMARK_PROGRESS,
        TTS_BENCHMARK_DONE,
        CONV_BENCHMARK_PROGRESS,
        CONV_BENCHMARK_DONE,
        CONV_SESSION_STARTED,
        CONV_SESSION_ENDED,
        EAR_EVENT_OWW_SCORE,
        PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
        PERSONALITY_STATE_SNAPSHOT,
    }
)


class ConversationCapture:
    """Manages per-client queues for the /ws/conversation endpoint."""

    def __init__(self, maxsize: int = 512) -> None:
        self._clients: set[asyncio.Queue[str]] = set()
        self._maxsize = maxsize

    @property
    def active(self) -> bool:
        return len(self._clients) > 0

    def add_client(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._maxsize)
        self._clients.add(q)
        log.info(
            "conversation capture: client connected (%d total)", len(self._clients)
        )
        return q

    def remove_client(self, q: asyncio.Queue[str]) -> None:
        self._clients.discard(q)
        log.info(
            "conversation capture: client disconnected (%d total)", len(self._clients)
        )

    def capture_envelope(self, env: Envelope) -> None:
        """Capture a worker event if it's conversation-relevant."""
        if not self._clients:
            return
        if env.type not in _CONVERSATION_TYPES:
            return
        entry = json.dumps(
            {
                "ts_mono_ms": round(env.t_ns / 1_000_000, 1),
                "type": env.type,
                **env.payload,
            }
        )
        self._broadcast(entry)

    def capture_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Capture a synthetic event (e.g. session start/end from tick loop)."""
        if not self._clients:
            return
        entry = json.dumps(
            {
                "ts_mono_ms": round(time.monotonic() * 1000.0, 1),
                "type": event_type,
                **payload,
            }
        )
        self._broadcast(entry)

    def _broadcast(self, entry: str) -> None:
        for q in list(self._clients):
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(entry)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
