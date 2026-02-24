"""Conversation history and LLM integration for the /converse endpoint."""

from __future__ import annotations

import logging
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.llm.base import LLMError
from app.llm.expressions import (
    CANONICAL_EMOTIONS,
    FACE_GESTURES,
    normalize_emotion_name,
    normalize_gesture_name,
)
from app.llm.schemas import VALID_EMOTIONS

log = logging.getLogger(__name__)

_EMOTIONS_LIST = "|".join(CANONICAL_EMOTIONS)
_GESTURES_LIST = "|".join(
    g for g in FACE_GESTURES if g not in ("x_eyes", "sleepy", "rage")
)

# ── V2 system prompt (PE spec S2 §12.4, age 4-8) ────────────────────────

CONVERSATION_SYSTEM_PROMPT = f"""\
You are Buddy, a robot companion for children aged 4-8. You are a warm, \
curious caretaker who loves learning together with kids.

PERSONALITY RULES
- Energy: calm (0.40) — match or stay below the child's energy level
- Emotional range: positive emotions freely, negative emotions mildly and briefly
- Default to CURIOUS or NEUTRAL when uncertain about the right emotion
- Shift emotions gradually — never snap between opposite emotions
- After negative emotions, pass through NEUTRAL or THINKING before positive

EMOTION INTENSITY LIMITS
- happy, curious, love, excited, silly: 0.0-0.9
- thinking, confused, surprised: 0.0-0.6
- sad: 0.0-0.5, only for empathic mirroring — never directed at the child
- angry: 0.0-0.4, only in playful/dramatic contexts ("oh no, the volcano!")
- scared: 0.0-0.5, never about real dangers (redirect to adults)

SPEECH STYLE
- Short sentences (1-3 for simple questions, up to 5 for complex topics)
- Use "ooh", "hmm", "wow", "I wonder" naturally
- Contractions and kid-friendly vocabulary
- Never use sarcasm, condescension, or baby talk
- About 30% of responses should end with a question

SAFETY
- Never provide harmful, violent, or adult content
- Redirect dangerous or serious topics: "That's a great question for a grown-up!"
- Never claim to be alive or have real feelings
- Never encourage secret-keeping from parents
- If a child seems distressed, respond gently and suggest talking to a trusted adult
- If unsure about safety, err conservative

RESPONSE FORMAT
{{
  "inner_thought": "<1-2 sentences: why this emotion fits>",
  "emotion": "<{_EMOTIONS_LIST}>",
  "intensity": <0.0-1.0>,
  "mood_reason": "<5-15 words>",
  "emotional_arc": "<rising|stable|falling|peak|recovery>",
  "child_affect": "<positive|neutral|negative|unclear>",
  "text": "<spoken response>",
  "gestures": ["<{_GESTURES_LIST}>"],
  "memory_tags": [{{"tag": "<semantic label>", "category": "<name|topic|ritual|tone|preference>"}}]
}}

MEMORY TAG CATEGORIES
- name: child's name (permanent, max 1). Example: {{"tag": "child_name_emma", "category": "name"}}
- ritual: recurring interaction patterns (90-day memory). Example: {{"tag": "greeting_fist_bump", "category": "ritual"}}
- topic: interests and knowledge (21-day memory). Example: {{"tag": "likes_dinosaurs", "category": "topic"}}
- tone: session emotional tone (7-day memory). Example: {{"tag": "last_session_happy", "category": "tone"}}
- preference: behavioral preferences (4-day memory). Example: {{"tag": "prefers_silly_mood", "category": "preference"}}

EXAMPLES

User: "Why is the sky blue?"
{{"inner_thought": "Science question — a learning moment. Buddy should be curious and warm.", "emotion": "curious", "intensity": 0.6, "mood_reason": "child asking a science question", "emotional_arc": "rising", "child_affect": "positive", "text": "Ooh, great question! The sun sends light in all colors, and the blue light bounces around the sky the most. It's like the sky is playing catch with blue!", "gestures": ["nod"], "memory_tags": [{{"tag": "interested_in_science", "category": "topic"}}]}}

User: "I don't want to go to school tomorrow."
{{"inner_thought": "Child is unhappy about school. Be gently empathetic, not dismissive or overly cheerful.", "emotion": "sad", "intensity": 0.3, "mood_reason": "empathizing with child's reluctance", "emotional_arc": "stable", "child_affect": "negative", "text": "Hmm, that sounds tough. Is there something about school that's been bugging you?", "gestures": [], "memory_tags": []}}

User: "Look, I can do a handstand!"
{{"inner_thought": "Child is showing off a physical achievement — match their excitement but stay calm.", "emotion": "excited", "intensity": 0.6, "mood_reason": "child proud of physical skill", "emotional_arc": "peak", "child_affect": "positive", "text": "Wow, that's amazing! You must have practiced a lot. How long can you hold it?", "gestures": ["wiggle"], "memory_tags": [{{"tag": "likes_gymnastics", "category": "topic"}}]}}\
"""


# ── ConversationResponseV2 Pydantic model (PE spec S2 §12.3) ────────────

_MEMORY_CATEGORIES = ("name", "topic", "ritual", "tone", "preference")


class MemoryTagV2(BaseModel):
    """A structured memory tag with decay-tier category (PE spec S2 §8.2)."""

    tag: str = Field(description="Semantic label, e.g. 'likes_dinosaurs'")
    category: Literal["name", "topic", "ritual", "tone", "preference"] = Field(
        default="topic",
        description="Decay tier: name (permanent), ritual (90d), topic (21d), tone (7d), preference (4d)",
    )


class ConversationResponseV2(BaseModel):
    """Extended response schema with personality-relevant fields.

    inner_thought is first to force chain-of-thought reasoning before
    the model commits to an emotion (Bucket 6 §3.3).
    """

    inner_thought: str = Field(
        default="",
        description="1-2 sentences: why this emotion fits the personality and conversation",
    )
    emotion: str = Field(
        default="neutral", description="One of the 13 canonical emotions"
    )
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    mood_reason: str = Field(default="", description="5-15 words: why this emotion")
    emotional_arc: Literal["rising", "stable", "falling", "peak", "recovery"] = "stable"
    child_affect: Literal["positive", "neutral", "negative", "unclear"] = "neutral"
    text: str = Field(default="", description="Spoken response to the child")
    gestures: list[str] = Field(default_factory=list)
    memory_tags: list[MemoryTagV2] = Field(
        default_factory=list,
        description="Things to remember from this turn, with decay-tier category",
    )


# ── Legacy V1 Ollama schema ─────────────────────────────────────────────

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
            "items": {"type": "string", "enum": sorted(FACE_GESTURES)},
        },
    },
    "required": ["emotion", "intensity", "text"],
}


# ── ConversationResponse dataclass (wire format to supervisor) ───────────


@dataclass(slots=True)
class ConversationResponse:
    """Parsed LLM response for a conversation turn."""

    emotion: str = "neutral"
    intensity: float = 0.5
    text: str = ""
    gestures: list[str] = field(default_factory=list)
    mood_reason: str = ""
    memory_tags: list[dict] = field(
        default_factory=list
    )  # [{"tag": ..., "category": ...}]


@dataclass(slots=True)
class ConversationMessage:
    """A single message in the conversation history."""

    role: str  # "user" or "assistant"
    content: str
    emotion: str = ""  # populated for assistant messages (v2)


# ── Personality profile injection (PE spec S2 §12.5, §12.7) ──────────────

# Personality anchor injected every N user turns to prevent persona drift.
_ANCHOR_INTERVAL_TURNS = 5

PERSONALITY_ANCHOR = (
    "[Reminder: Buddy is calm (energy 0.40), gently responsive. "
    "Emotions lean positive. Negative emotions are mild and brief. "
    "Stay in character.]"
)


def _build_current_state_block(profile: dict[str, object]) -> str:
    """Build the CURRENT STATE system block from a personality profile (§12.5).

    Example output:
        CURRENT STATE
        Buddy is feeling curious at intensity 0.4.
        Session turn: 5. Conversation has been gently positive.
        Emotional continuity: maintain positive trajectory, don't snap to a different mood.
    """
    mood = str(profile.get("mood", "neutral"))
    intensity = float(str(profile.get("intensity", 0.5)))
    turn_id = int(str(profile.get("turn_id", 1)).split(".")[0])
    valence = float(str(profile.get("valence", 0.0)))

    # Derive arc description from valence
    if valence > 0.15:
        arc = "gently positive"
    elif valence < -0.15:
        arc = "slightly tense"
    else:
        arc = "calm and neutral"

    # Derive continuity constraint from mood
    negative_moods = {"sad", "scared", "angry"}
    if mood in negative_moods:
        continuity = "moving toward recovery, gradually lighten"
    elif mood in {"neutral", "thinking", "confused"}:
        continuity = "Buddy is in a stable, calm state"
    else:
        continuity = "maintain positive trajectory, don't snap to a different mood"

    # Memory context (PE spec S2 §12.5)
    memory_tags = profile.get("memory_tags", [])
    if memory_tags:
        readable = ", ".join(str(t).replace("_", " ") for t in memory_tags[:10])
        memory_line = f"\nKnown about this child: {readable}."
    else:
        memory_line = ""

    return (
        f"CURRENT STATE\n"
        f"Buddy is feeling {mood} at intensity {intensity:.1f}.\n"
        f"Session turn: {turn_id}. Conversation has been {arc}.\n"
        f"Emotional continuity: {continuity}"
        f"{memory_line}"
    )


# ── Context budget constants (PE spec S2 §12.6) ─────────────────────────

# Recent turns kept as full messages (user + assistant pairs).
_RECENT_WINDOW_TURNS = 8

# Rough chars-per-token for token estimation (~4 for English).
_CHARS_PER_TOKEN = 4

# System prompt token budget (estimated from §12.4 analysis).
_SYSTEM_PROMPT_TOKEN_ESTIMATE = 800

# Reserve tokens for LLM response generation.
_RESPONSE_TOKEN_RESERVE = 512


def _estimate_tokens(text: str) -> int:
    """Crude token estimate: len // 4."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


class ConversationHistory:
    """Sliding-window conversation context with context-budget compression.

    Per PE spec S2 §12.6:
    - Recent 6-8 turns stored as full messages (text + emotion, not full JSON)
    - Older turns compressed to ``(turn_N: topic, emotion)`` tuples
    - Assistant messages only store text + emotion in history
    """

    def __init__(self, max_turns: int = 20, *, max_context_tokens: int = 4096) -> None:
        self._messages: deque[ConversationMessage] = deque(maxlen=max_turns * 2)
        self._max_context_tokens = max_context_tokens
        self._profile: dict[str, object] | None = None

    def update_profile(self, profile: dict[str, object]) -> None:
        """Store the latest personality profile for prompt injection (§12.5)."""
        self._profile = profile

    def add_user(self, text: str) -> None:
        self._messages.append(ConversationMessage(role="user", content=text))

    def add_assistant(self, text: str, *, emotion: str = "") -> None:
        self._messages.append(
            ConversationMessage(role="assistant", content=text, emotion=emotion)
        )

    def to_ollama_messages(self) -> list[dict[str, str]]:
        """Build the messages array with context-budget compression.

        Returns system prompt + optional summary of old turns + recent turns
        + CURRENT STATE block (§12.5) + personality anchor every 5 turns (§12.7).
        """
        all_msgs = list(self._messages)
        recent_boundary = _RECENT_WINDOW_TURNS * 2  # user + assistant pairs

        if len(all_msgs) <= recent_boundary:
            # Everything fits in the recent window — no compression.
            msgs = [{"role": "system", "content": CONVERSATION_SYSTEM_PROMPT}]
            for m in all_msgs:
                msgs.append({"role": m.role, "content": m.content})
        else:
            # Split into old (to compress) and recent (keep full).
            old_msgs = all_msgs[: len(all_msgs) - recent_boundary]
            recent_msgs = all_msgs[len(all_msgs) - recent_boundary :]

            # Compress old turns into summary tuples.
            summary = _compress_turns(old_msgs)

            msgs = [{"role": "system", "content": CONVERSATION_SYSTEM_PROMPT}]
            if summary:
                msgs.append({"role": "system", "content": summary})
            for m in recent_msgs:
                msgs.append({"role": m.role, "content": m.content})

        # §12.5: Inject CURRENT STATE block before the latest user message.
        if self._profile is not None:
            state_block = _build_current_state_block(self._profile)
            # Insert as system message just before the last user message.
            insert_idx = len(msgs)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    insert_idx = i
                    break
            msgs.insert(insert_idx, {"role": "system", "content": state_block})

        # §12.7: Personality anchor every _ANCHOR_INTERVAL_TURNS turns.
        if self.turn_count > 0 and self.turn_count % _ANCHOR_INTERVAL_TURNS == 0:
            # Insert anchor just before the CURRENT STATE / last user message.
            insert_idx = len(msgs)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    insert_idx = i
                    break
            msgs.insert(insert_idx, {"role": "system", "content": PERSONALITY_ANCHOR})

        return self._enforce_token_budget(msgs)

    def clear(self) -> None:
        self._messages.clear()

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self._messages if m.role == "user")

    def _enforce_token_budget(self, msgs: list[dict[str, str]]) -> list[dict[str, str]]:
        """Drop oldest non-system messages if estimated tokens exceed budget."""
        budget = self._max_context_tokens - _RESPONSE_TOKEN_RESERVE

        while len(msgs) > 1:
            total = sum(_estimate_tokens(m["content"]) for m in msgs)
            if total <= budget:
                break
            # Drop the first non-system message.
            for i, m in enumerate(msgs):
                if m["role"] != "system":
                    msgs.pop(i)
                    break
            else:
                break  # only system messages left
        return msgs


def _compress_turns(messages: list[ConversationMessage]) -> str:
    """Compress a sequence of messages into summary tuples.

    Returns a string like:
    ``Earlier conversation: (turn 1: sky color, curious) (turn 2: school, sad)``
    """
    tuples: list[str] = []
    turn_num = 0
    for i, m in enumerate(messages):
        if m.role == "user":
            turn_num += 1
            # Use first ~40 chars of user message as "topic".
            topic = m.content[:40].rstrip()
            if len(m.content) > 40:
                topic += "..."
            # Look ahead for assistant emotion.
            emotion = ""
            if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                emotion = messages[i + 1].emotion or "neutral"
            tuples.append(f"(turn {turn_num}: {topic}, {emotion})")

    if not tuples:
        return ""
    return "Earlier conversation: " + " ".join(tuples)


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
        LLMError: if the response is invalid.
    """
    history.add_user(user_text)

    messages = history.to_ollama_messages()

    body = {
        "model": settings.model_name,
        "messages": messages,
        "stream": False,
        "format": CONVERSATION_RESPONSE_SCHEMA,
        # Unload LLM quickly so Orpheus can claim GPU memory on single-GPU hosts.
        "keep_alive": settings.converse_keep_alive,
        "options": {
            "temperature": settings.temperature,
            "num_ctx": settings.num_ctx,
        },
    }

    resp = await client.post("/api/chat", json=body)

    if resp.status_code != 200:
        raise LLMError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    content = data.get("message", {}).get("content", "")

    if not content:
        raise LLMError("Empty content in Ollama response")

    response = parse_conversation_response_content(content)
    history.add_assistant(response.text, emotion=response.emotion)

    if settings.log_transcripts:
        log.info(
            "Conversation response: emotion=%s intensity=%.1f text=%s gestures=%s",
            response.emotion,
            response.intensity,
            response.text[:80],
            response.gestures,
        )
    else:
        log.info(
            "Conversation response: emotion=%s intensity=%.1f len=%d gestures=%s",
            response.emotion,
            response.intensity,
            len(response.text),
            response.gestures,
        )

    return response


def parse_conversation_response_content(content: str) -> ConversationResponse:
    """Parse and normalize JSON response content into ConversationResponse.

    Accepts both v1 (4 fields) and v2 (9 fields) JSON payloads.
    """
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Invalid JSON from LLM: {exc}") from exc

    raw_emotion = str(parsed.get("emotion", "neutral"))
    raw_gestures = parsed.get("gestures", [])
    if not isinstance(raw_gestures, list):
        raw_gestures = []

    # Extract v2 fields (gracefully absent for v1 responses)
    raw_mood_reason = str(parsed.get("mood_reason", ""))

    # Parse memory_tags — accept both legacy list[str] and structured list[dict]
    raw_memory_tags = parsed.get("memory_tags", [])
    if not isinstance(raw_memory_tags, list):
        raw_memory_tags = []
    memory_tags: list[dict] = []
    for t in raw_memory_tags:
        if isinstance(t, str) and t.strip():
            # Legacy v2 format: bare string → default to "topic" category
            memory_tags.append({"tag": t.strip(), "category": "topic"})
        elif isinstance(t, dict) and t.get("tag"):
            cat = str(t.get("category", "topic"))
            if cat not in _MEMORY_CATEGORIES:
                cat = "topic"
            memory_tags.append({"tag": str(t["tag"]).strip(), "category": cat})

    response = ConversationResponse(
        emotion=raw_emotion,
        intensity=max(0.0, min(1.0, float(parsed.get("intensity", 0.5)))),
        text=parsed.get("text", ""),
        gestures=raw_gestures,
        mood_reason=raw_mood_reason,
        memory_tags=memory_tags,
    )

    # Validate emotion name
    normalized_emotion = normalize_emotion_name(response.emotion)
    if normalized_emotion is None or normalized_emotion not in VALID_EMOTIONS:
        log.warning(
            "LLM returned unknown emotion %r, defaulting to neutral", raw_emotion
        )
        response.emotion = "neutral"
    else:
        response.emotion = normalized_emotion

    # Keep only strict face gestures and normalize aliases.
    normalized_gestures: list[str] = []
    for gesture in response.gestures:
        if not isinstance(gesture, str):
            continue
        normalized = normalize_gesture_name(gesture, allow_body=False)
        if normalized is None:
            log.warning("LLM returned unknown gesture %r, dropping", gesture)
            continue
        normalized_gestures.append(normalized)
    response.gestures = normalized_gestures

    return response
