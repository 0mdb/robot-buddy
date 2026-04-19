"""Streaming parser for Orpheus-bound LLM conversation responses.

The V2 schema (``ConversationResponseV2``) places ``text`` as the LAST field
so a streaming converse path can:

1. Accumulate tokens until the opening ``"`` of the text value is seen.
2. Parse everything before that as a complete metadata JSON prefix.
3. Stream the characters *inside* the text value into a sentence segmenter.
4. Emit each sentence as soon as it's complete so TTS can start early.

The parser is single-threaded and feed/close-style so any async driver
can wrap an LLM token stream and push deltas in.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from app.llm.base import LLMError
from app.llm.conversation import (
    ConversationResponse,
    parse_conversation_response_content,
)

log = logging.getLogger(__name__)


# JSON single-character escape table. ``\u`` is handled separately (4 hex chars).
_SIMPLE_ESCAPE: dict[str, str] = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
}

_SENTENCE_TERMINATORS = frozenset(".!?…")


@dataclass(slots=True)
class MetadataReady:
    """Fired once, when the JSON prefix up to the opening quote of ``text`` parses.

    ``response.text`` is always the empty string at this point — the text is
    streamed afterwards via ``Sentence`` events.
    """

    response: ConversationResponse


@dataclass(slots=True)
class Sentence:
    """Fired each time the segmenter finds a complete sentence in the text field."""

    text: str
    index: int


ParserEvent = MetadataReady | Sentence


class ConversationStreamParser:
    """Consume LLM token deltas, emit metadata + sentences.

    State machine:
      * ``PRE``  — scanning JSON until we locate ``"text":"``.
      * ``TEXT`` — consuming the text value character by character.
      * ``DONE`` — seen closing ``"`` of text; further input is discarded.

    The ``first_min_chars`` / ``min_chars`` thresholds protect TTS prosody
    quality on mid-stream sentences while letting the very first sentence
    ship aggressively (it's the latency win). A sentence shorter than the
    threshold is held until the next boundary or the final ``close()``.
    """

    _PRE = 0
    _TEXT = 1
    _DONE = 2

    def __init__(self, *, first_min_chars: int = 6, min_chars: int = 12) -> None:
        self._state = self._PRE
        self._first_min = first_min_chars
        self._min = min_chars

        # PRE-state scratch.
        self._buf = ""
        self._scan_pos = 0
        self._brace = 0
        self._in_string = False
        self._pre_escape = False

        # TEXT-state scratch.
        self._text_accum = ""
        self._seg_buf = ""
        self._text_escape = False
        self._unicode_remaining = 0
        self._unicode_buf = ""

        self._emitted_count = 0
        self._metadata_response: ConversationResponse | None = None

    @property
    def metadata_ready(self) -> bool:
        return self._state != self._PRE

    @property
    def done(self) -> bool:
        return self._state == self._DONE

    def full_text(self) -> str:
        return self._text_accum

    def metadata(self) -> ConversationResponse | None:
        """The parsed metadata, populated with the accumulated text so far."""
        if self._metadata_response is None:
            return None
        # Callers may want the up-to-date text, so patch it in.
        self._metadata_response.text = self._text_accum
        return self._metadata_response

    def feed(self, chunk: str) -> Iterator[ParserEvent]:
        if not chunk:
            return
        if self._state == self._PRE:
            yield from self._feed_pre(chunk)
        elif self._state == self._TEXT:
            yield from self._feed_text(chunk)
        # DONE: discard.

    def close(self) -> Iterator[ParserEvent]:
        """Flush any buffered text as a final sentence (even if shorter than the threshold)."""
        if self._state == self._TEXT:
            remaining = self._seg_buf.strip()
            self._seg_buf = ""
            if remaining:
                yield Sentence(text=remaining, index=self._emitted_count)
                self._emitted_count += 1

    # ── PRE state ──────────────────────────────────────────────────

    def _feed_pre(self, chunk: str) -> Iterator[ParserEvent]:
        self._buf += chunk
        buf = self._buf
        i = self._scan_pos
        n = len(buf)
        while i < n:
            ch = buf[i]
            if self._in_string:
                if self._pre_escape:
                    self._pre_escape = False
                elif ch == "\\":
                    self._pre_escape = True
                elif ch == '"':
                    self._in_string = False
                i += 1
                continue
            if ch == "{":
                self._brace += 1
                i += 1
            elif ch == "}":
                self._brace -= 1
                i += 1
            elif ch == '"':
                # Potential key. Only match `"text"` as the TOP-LEVEL text value
                # (brace depth 1) — this keeps `"text"` appearing inside nested
                # objects or string contents from false-firing.
                if self._brace == 1:
                    remaining_in_buf = n - i
                    if remaining_in_buf < 6:
                        # Not enough data to decide. If the partial matches
                        # a prefix of `"text"` we must wait; otherwise treat
                        # as a regular string literal.
                        if '"text"'.startswith(buf[i:]):
                            self._scan_pos = i
                            return
                    elif buf.startswith('"text"', i):
                        j = i + 6  # past the closing `"` of the key
                        while j < n and buf[j].isspace():
                            j += 1
                        if j >= n:
                            self._scan_pos = i
                            return
                        if buf[j] != ":":
                            # Not actually the `text` key.
                            self._in_string = True
                            i += 1
                            continue
                        j += 1
                        while j < n and buf[j].isspace():
                            j += 1
                        if j >= n:
                            self._scan_pos = i
                            return
                        if buf[j] != '"':
                            log.debug(
                                "`text` value does not start with a string literal"
                            )
                            self._in_string = True
                            i += 1
                            continue
                        # Hit! `j` is the opening quote of the text string literal.
                        yield from self._enter_text(j)
                        leftover = buf[j + 1 :]
                        if leftover:
                            yield from self._feed_text(leftover)
                        return
                # Regular string literal start.
                self._in_string = True
                i += 1
            else:
                i += 1
        self._scan_pos = i

    def _enter_text(self, opening_quote_pos: int) -> Iterator[ParserEvent]:
        """Called once we've located the opening ``"`` of the text value."""
        synthetic = self._buf[: opening_quote_pos + 1] + '"}'
        try:
            response = parse_conversation_response_content(synthetic)
            response.text = ""
        except LLMError as exc:
            log.warning("Streaming parser: metadata prefix unparsable: %s", exc)
            response = ConversationResponse()
        self._metadata_response = response
        self._state = self._TEXT
        # Free the pre-state buffer — no longer needed.
        self._buf = ""
        yield MetadataReady(response=response)

    # ── TEXT state ─────────────────────────────────────────────────

    def _feed_text(self, chunk: str) -> Iterator[ParserEvent]:
        for ch in chunk:
            if self._state != self._TEXT:
                return
            if self._unicode_remaining > 0:
                self._unicode_buf += ch
                self._unicode_remaining -= 1
                if self._unicode_remaining == 0:
                    try:
                        actual = chr(int(self._unicode_buf, 16))
                    except ValueError:
                        actual = ""
                    self._unicode_buf = ""
                    if actual:
                        self._text_accum += actual
                        yield from self._on_text_char(actual)
                continue
            if self._text_escape:
                self._text_escape = False
                if ch == "u":
                    self._unicode_remaining = 4
                    self._unicode_buf = ""
                    continue
                actual = _SIMPLE_ESCAPE.get(ch, ch)
                self._text_accum += actual
                yield from self._on_text_char(actual)
                continue
            if ch == "\\":
                self._text_escape = True
                continue
            if ch == '"':
                self._state = self._DONE
                remaining = self._seg_buf.strip()
                self._seg_buf = ""
                if remaining:
                    yield Sentence(text=remaining, index=self._emitted_count)
                    self._emitted_count += 1
                return
            self._text_accum += ch
            yield from self._on_text_char(ch)

    def _on_text_char(self, ch: str) -> Iterator[ParserEvent]:
        self._seg_buf += ch
        if not ch.isspace():
            return
        trimmed = self._seg_buf.rstrip()
        if not trimmed:
            self._seg_buf = ""
            return
        if trimmed[-1] not in _SENTENCE_TERMINATORS:
            return
        min_len = self._first_min if self._emitted_count == 0 else self._min
        if len(trimmed) < min_len:
            return
        self._seg_buf = ""
        yield Sentence(text=trimmed, index=self._emitted_count)
        self._emitted_count += 1
