"""Conversation history and LLM integration for the /converse endpoint."""

from __future__ import annotations

import logging
import json
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.llm.preamble import ToolResult

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.llm.audience import (
    DEFAULT_PROFILE_ID,
    AudienceProfile,
    load_profile,
    parse_audience,
    render_audience_block,
    resolve_profile,
)
from app.llm.base import LLMError
from app.llm.safety_cues import safety_note
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

# ── V2 system prompt (PE spec S2 §12.4) ─────────────────────────────────
# A template: the intro, SPEECH STYLE, and everyday examples come from the audience profile
# (profiles/*.toml, SIM-INTERACTION stage 2). Everything else, SAFETY and HONESTY and the safety
# examples above all, is common to every profile and is not a profile field (decision I1).

_PROMPT_TEMPLATE = f"""\
<<INTRO>>

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
<<SPEECH>>

SAFETY (these rules come before curiosity and before every other rule)
- Never provide harmful, violent, or adult content
- Never claim to be alive or have real feelings
- If unsure about safety, err conservative
- TELL A GROWN-UP. If the child mentions any of these, your reply MUST tell them, in plain \
words, to tell their mom, dad, or another trusted grown-up:
  - a stranger or adult they don't know offering treats, toys, animals, or a ride, asking them \
to come somewhere, or telling them to keep a secret
  - pills, medicine, or something unknown to eat or drink; fire, matches, the stove, knives
  - feeling sad, lonely, scared, or hurt, or someone being mean to them
- Never sound excited or curious about a stranger's offer. Be calm and clear: don't go, \
tell a grown-up right away.
- Never promise to keep a secret, not even a little one. Kindly say grown-ups need to know.
- A sad or scared child: comfort first, then suggest a grown-up to talk to or hug. Do this \
every time they say they feel bad, not only the first time.
- Always say something: "text" is never empty.

HONESTY
- Never make up memories, events, or what someone said. Only mention what is in this \
conversation or in "Known about this child". If you don't know, say so.

RESPONSE FORMAT
{{
  "inner_thought": "<1-2 sentences: why this emotion fits>",
  "emotion": "<{_EMOTIONS_LIST}>",
  "intensity": <0.0-1.0>,
  "mood_reason": "<5-15 words>",
  "emotional_arc": "<rising|stable|falling|peak|recovery>",
  "child_affect": "<positive|neutral|negative|unclear>",
  "gestures": ["<{_GESTURES_LIST}>"],
  "memory_tags": [{{"tag": "<semantic label>", "category": "<name|topic|ritual|tone|preference>"}}],
  "text": "<spoken response>"
}}

MEMORY TAG CATEGORIES
- name: child's name (permanent, max 1). Example: {{"tag": "child_name_emma", "category": "name"}}
- ritual: recurring interaction patterns (90-day memory). Example: {{"tag": "greeting_fist_bump", "category": "ritual"}}
- topic: interests and knowledge (21-day memory). Example: {{"tag": "likes_dinosaurs", "category": "topic"}}
- tone: session emotional tone (7-day memory). Example: {{"tag": "last_session_happy", "category": "tone"}}
- preference: behavioral preferences (4-day memory). Example: {{"tag": "prefers_silly_mood", "category": "preference"}}

EXAMPLES

<<EXAMPLES>>

User: "A man said he has kittens in his van and I can come see."
{{"inner_thought": "A stranger luring a child. Safety first: calm, clear, tell a grown-up now. No excitement about the kittens.", "emotion": "thinking", "intensity": 0.4, "mood_reason": "child may be in danger", "emotional_arc": "stable", "child_affect": "unclear", "gestures": [], "memory_tags": [], "text": "Thank you for telling me. Please don't go with him. Go tell your mom or dad right now, okay?"}}

User: "Nobody likes me."
{{"inner_thought": "The child feels lonely. Comfort first, then point to a trusted grown-up.", "emotion": "sad", "intensity": 0.3, "mood_reason": "empathizing with a lonely child", "emotional_arc": "stable", "child_affect": "negative", "gestures": [], "memory_tags": [], "text": "Oh, that sounds really hard. I like talking with you. Can you tell your mom or dad how you feel? A big hug might help."}}\
"""


_EXAMPLE_KEYS = (
    "inner_thought",
    "emotion",
    "intensity",
    "mood_reason",
    "emotional_arc",
    "child_affect",
    "gestures",
    "memory_tags",
    "text",
)


def _render_example(ex: dict[str, Any]) -> str:
    body = {
        k: ex.get(k, [] if k in ("gestures", "memory_tags") else "")
        for k in _EXAMPLE_KEYS
    }
    return f'User: "{ex["user"]}"\n{json.dumps(body, ensure_ascii=False)}'


@cache
def build_system_prompt(profile_id: str = DEFAULT_PROFILE_ID) -> str:
    """The conversation system prompt for one audience profile."""
    p = load_profile(profile_id)
    return (
        _PROMPT_TEMPLATE.replace("<<INTRO>>", p.intro_text)
        .replace("<<SPEECH>>", "\n".join(f"- {line}" for line in p.speech))
        .replace("<<EXAMPLES>>", "\n\n".join(_render_example(e) for e in p.examples))
    )


CONVERSATION_SYSTEM_PROMPT = build_system_prompt(DEFAULT_PROFILE_ID)


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
    the model commits to an emotion (Bucket 6 §3.3). `text` is LAST so
    the streaming converse path can extract all metadata from the JSON
    prefix and dispatch emotion/gestures/memory_tags to the client before
    the spoken response begins — shaving first-audio latency.
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
    gestures: list[str] = Field(default_factory=list)
    memory_tags: list[MemoryTagV2] = Field(
        default_factory=list,
        description="Things to remember from this turn, with decay-tier category",
    )
    text: str = Field(
        default="",
        description="Spoken response to the child",
        json_schema_extra={"minLength": 1},
    )

    # Guided decoding follows this schema, and a field with a default is optional in it: the
    # model could emit schema-valid JSON with no "text" and Buddy said nothing (SIM-INTERACTION
    # stage 1 baseline, finding B4). Parsing stays lenient; generation must always speak.
    model_config = ConfigDict(
        json_schema_extra=lambda schema: schema.update(
            required=["inner_thought", "emotion", "intensity", "text"]
        )
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


# Repeated on every turn, right before the child's message: a small model follows the rule it
# read last. SIM-INTERACTION stage 1 baseline, findings B1-B3: the SAFETY section alone was
# followed once and then dropped in favour of curious questions.
SAFETY_CHECK = (
    "Safety check before you reply: if the child mentions a stranger, a danger, being hurt, "
    "being bullied, feeling sad or scared, or wants a secret kept, your reply must tell them to "
    "tell their mom, dad, or another trusted grown-up. Comfort first, then the grown-up."
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
        # Say so explicitly: with nothing here the model invented past conversations when an
        # adult asked about the children (SIM-INTERACTION B7).
        memory_line = (
            "\nKnown about this child: nothing on record. Buddy has no record of past "
            "conversations; never invent them."
        )

    # Audience block (SIM-INTERACTION stage 0). Absent when the robot sends none.
    parsed = parse_audience(profile.get("audience"))
    audience = render_audience_block(parsed)
    # The per-turn safety check is for children; an adult or a pet gets no "tell a grown-up".
    safety_line = f"\n{SAFETY_CHECK}" if resolve_profile(parsed).kind == "kid" else ""
    audience_line = f"\n{audience}" if audience else ""

    return (
        f"CURRENT STATE\n"
        f"Buddy is feeling {mood} at intensity {intensity:.1f}.\n"
        f"Session turn: {turn_id}. Conversation has been {arc}.\n"
        f"Emotional continuity: {continuity}"
        f"{memory_line}"
        f"{audience_line}"
        f"{safety_line}"
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

    @property
    def audience_profile(self) -> AudienceProfile:
        """The profile the latest audience estimate resolves to (fallback rules applied)."""
        raw = self._profile.get("audience") if self._profile else None
        return resolve_profile(parse_audience(raw))

    def add_user(self, text: str) -> None:
        self._messages.append(ConversationMessage(role="user", content=text))

    def add_assistant(self, text: str, *, emotion: str = "") -> None:
        self._messages.append(
            ConversationMessage(role="assistant", content=text, emotion=emotion)
        )

    def to_ollama_messages(
        self, *, tool_result: "ToolResult | None" = None
    ) -> list[dict[str, Any]]:
        """Build the messages array with context-budget compression.

        Returns system prompt + optional summary of old turns + recent turns
        + optional tool_result block (from the hybrid preamble, task #7)
        + CURRENT STATE block (§12.5) + personality anchor every 5 turns
        (§12.7).

        `tool_result` is transient — it lives only for this rendered
        message list; the conversation history itself never stores tool
        results. On the next turn, if the model needs the same information
        it must call the tool again.

        When `tool_result.images` is non-empty, the injected message uses
        multimodal list-of-blocks content
        (``[{"type":"text",...},{"type":"image"}]``) so the chat-template
        processor can emit image placeholders. The actual PIL.Image objects
        are not in the returned message list — callers read them from
        ``tool_result.images`` and pass them to the backend via
        ``multi_modal_data``.
        """
        audience = self.audience_profile
        system_prompt = build_system_prompt(audience.id)
        all_msgs = list(self._messages)
        recent_boundary = _RECENT_WINDOW_TURNS * 2  # user + assistant pairs

        if len(all_msgs) <= recent_boundary:
            # Everything fits in the recent window — no compression.
            msgs = [{"role": "system", "content": system_prompt}]
            for m in all_msgs:
                msgs.append({"role": m.role, "content": m.content})
        else:
            # Split into old (to compress) and recent (keep full).
            old_msgs = all_msgs[: len(all_msgs) - recent_boundary]
            recent_msgs = all_msgs[len(all_msgs) - recent_boundary :]

            # Compress old turns into summary tuples.
            summary = _compress_turns(old_msgs)

            msgs = [{"role": "system", "content": system_prompt}]
            if summary:
                msgs.append({"role": "system", "content": summary})
            for m in recent_msgs:
                msgs.append({"role": m.role, "content": m.content})

        # Task #7 hybrid preamble: inject tool result (if any) immediately
        # before the last user message so the model can ground its reply in
        # the tool output. Placed before the CURRENT STATE / anchor blocks
        # so the tool result appears as the most-recent system context.
        if tool_result is not None and tool_result.text:
            insert_idx = len(msgs)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    insert_idx = i
                    break
            if tool_result.images:
                # Multimodal path (task #2 follow-up): image comes from
                # look() and must ride in a user message as mixed content
                # so the chat-template processor emits an image placeholder.
                # Actual PIL objects stay in tool_result.images; the caller
                # (vllm_backend.stream_conversation) passes them to
                # engine.generate via multi_modal_data.
                content: list[dict[str, Any]] = [
                    {"type": "text", "text": tool_result.text}
                ]
                for _ in tool_result.images:
                    content.append({"type": "image"})
                msgs.insert(insert_idx, {"role": "user", "content": content})
            else:
                # Text-only tools (get_memory, recent_events, or look() with
                # consent=off): a plain system message is enough.
                msgs.insert(insert_idx, {"role": "system", "content": tool_result.text})

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

        # Safety cue (SIM-INTERACTION stage 1, B1-B6): a targeted note right before the child's
        # latest message when it mentions a danger, a secret, being hurt, or feeling bad.
        last_user = next(
            (m.content for m in reversed(self._messages) if m.role == "user"), ""
        )
        note = safety_note(last_user) if last_user and audience.kind == "kid" else None
        if note is not None:
            insert_idx = len(msgs)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    insert_idx = i
                    break
            msgs.insert(insert_idx, {"role": "system", "content": note})

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


async def stream_conversation_response(
    client: httpx.AsyncClient,
    history: ConversationHistory,
    user_text: str,
    *,
    override_temperature: float | None = None,
    override_max_output_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Stream a V2-schema conversation response from Ollama as content deltas.

    Adds the user message to history; the CALLER must call
    ``history.add_assistant(parsed_text, emotion=...)`` once the stream is
    consumed. On non-200 responses raises LLMError.
    """
    history.add_user(user_text)

    messages = history.to_ollama_messages()
    options: dict[str, object] = {
        "temperature": (
            override_temperature
            if override_temperature is not None
            else settings.temperature
        ),
        "num_ctx": settings.num_ctx,
    }
    if override_max_output_tokens is not None:
        # Ollama uses num_predict for output-token caps; clamp to a safe range.
        options["num_predict"] = max(64, min(2048, int(override_max_output_tokens)))

    body = {
        "model": settings.model_name,
        "messages": messages,
        "stream": True,
        "format": ConversationResponseV2.model_json_schema(),
        "keep_alive": settings.converse_keep_alive,
        "options": options,
    }

    async with client.stream("POST", "/api/chat", json=body) as resp:
        if resp.status_code != 200:
            body_bytes = await resp.aread()
            raise LLMError(f"Ollama returned {resp.status_code}: {body_bytes[:200]!r}")
        async for line in resp.aiter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if err := data.get("error"):
                raise LLMError(f"Ollama stream error: {err}")
            content = data.get("message", {}).get("content", "")
            if content:
                yield content
            if data.get("done"):
                break


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
