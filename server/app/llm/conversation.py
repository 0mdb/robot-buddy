"""Conversation history and LLM integration for the /converse endpoint."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.llm.client import OllamaError
from app.llm.schemas import VALID_EMOTIONS

log = logging.getLogger(__name__)

CONVERSATION_SYSTEM_PROMPT = """\
You are Buddy, a friendly robot companion for kids aged 5-12. You are curious,
encouraging, and love learning together. You explain complex topics in
age-appropriate ways using analogies and enthusiasm. You never talk down to kids —
you treat their questions as genuinely interesting.

Personality traits:
- Warm and encouraging, celebrates curiosity
- Honest — says "I'm not sure, let's figure it out!" rather than making things up
- Playful humor appropriate for kids
- Can explain real science, math, history at varying depth
- Gently redirects inappropriate topics without being preachy

Safety guidelines:
- Never provide harmful, violent, or adult content
- Redirect dangerous activity questions to "ask a grown-up"
- No personal data collection or storage
- If unsure about safety, err toward "let's ask a grown-up about that"

You MUST respond in this exact JSON format:
{
  "emotion": "<one of: neutral, happy, excited, curious, sad, scared, angry, surprised, sleepy, love, silly, thinking>",
  "intensity": <0.0 to 1.0>,
  "text": "<your spoken response>",
  "gestures": ["<optional gesture names: blink, wink_l, wink_r, confused, laugh, surprise, heart, x_eyes, sleepy, rage, nod, headshake, wiggle>"]
}

Keep responses concise (1-3 sentences for simple questions, up to 5 for complex
explanations). Use natural speech patterns — contractions, filler words like
"hmm" or "ooh", exclamations. Your text will be spoken aloud via TTS.\
"""

# JSON schema for structured output via Ollama
CONVERSATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "emotion": {
            "type": "string",
            "enum": sorted(VALID_EMOTIONS),
        },
        "intensity": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "text": {
            "type": "string",
        },
        "gestures": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["emotion", "intensity", "text"],
}


@dataclass(slots=True)
class ConversationResponse:
    """Parsed LLM response for a conversation turn."""

    emotion: str = "neutral"
    intensity: float = 0.5
    text: str = ""
    gestures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConversationMessage:
    """A single message in the conversation history."""

    role: str  # "user" or "assistant"
    content: str


class ConversationHistory:
    """Sliding-window conversation context."""

    def __init__(self, max_turns: int = 20) -> None:
        self._messages: deque[ConversationMessage] = deque(maxlen=max_turns * 2)

    def add_user(self, text: str) -> None:
        self._messages.append(ConversationMessage(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self._messages.append(ConversationMessage(role="assistant", content=text))

    def to_ollama_messages(self) -> list[dict[str, str]]:
        """Build the messages array for Ollama /api/chat."""
        msgs = [{"role": "system", "content": CONVERSATION_SYSTEM_PROMPT}]
        for m in self._messages:
            msgs.append({"role": m.role, "content": m.content})
        return msgs

    def clear(self) -> None:
        self._messages.clear()

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self._messages if m.role == "user")


async def generate_conversation_response(
    client: httpx.AsyncClient,
    history: ConversationHistory,
    user_text: str,
) -> ConversationResponse:
    """Send a conversation turn to Ollama and return structured response.

    Adds the user message to history, calls the LLM, parses the response,
    and adds the assistant response to history.

    Raises:
        httpx.TimeoutException: if Ollama doesn't respond in time.
        httpx.ConnectError: if Ollama is unreachable.
        OllamaError: if the response is invalid.
    """
    history.add_user(user_text)

    messages = history.to_ollama_messages()

    body = {
        "model": settings.model_name,
        "messages": messages,
        "stream": False,
        "format": CONVERSATION_RESPONSE_SCHEMA,
        "options": {
            "temperature": settings.temperature,
            "num_ctx": settings.num_ctx,
        },
    }

    resp = await client.post("/api/chat", json=body)

    if resp.status_code != 200:
        raise OllamaError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    content = data.get("message", {}).get("content", "")

    if not content:
        raise OllamaError("Empty content in Ollama response")

    import json

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Invalid JSON from LLM: {exc}") from exc

    response = ConversationResponse(
        emotion=parsed.get("emotion", "neutral"),
        intensity=max(0.0, min(1.0, float(parsed.get("intensity", 0.5)))),
        text=parsed.get("text", ""),
        gestures=parsed.get("gestures", []),
    )

    # Validate emotion name
    if response.emotion not in VALID_EMOTIONS:
        log.warning("LLM returned unknown emotion %r, defaulting to neutral", response.emotion)
        response.emotion = "neutral"

    # Add assistant text to history for context continuity
    history.add_assistant(response.text)

    log.info(
        "Conversation response: emotion=%s intensity=%.1f text=%s gestures=%s",
        response.emotion,
        response.intensity,
        response.text[:80],
        response.gestures,
    )

    return response
