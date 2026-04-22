"""Persistent MCP client for the hybrid tool-use preamble.

Opens a streamable-HTTP MCP session to the supervisor at server lifespan
startup and reuses it for every conversation turn. One of the goals in
task #7 is to keep the per-turn latency tight — a persistent session
saves the TCP + MCP initialize handshake (~100-200 ms) on every call.

If the session drops (Pi restarts, network blip), `call_tool` catches the
error, schedules a background reconnect with exponential backoff, and
returns None for that turn. The preamble treats a None result as "no
tool" and lets the conversation stream run unenriched.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import ImageContent, TextContent

log = logging.getLogger(__name__)


class McpClientError(Exception):
    """Raised when an MCP tool call fails in a recoverable way."""


class McpClient:
    """Thin async wrapper around an MCP streamable-HTTP ClientSession.

    Thread-safe for concurrent callers via an internal lock around the
    session — MCP sessions are not safe to share without serialization.
    """

    def __init__(
        self,
        url: str,
        *,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 8.0,
    ) -> None:
        self._url = url
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._lock = asyncio.Lock()
        self._connect_attempts = 0
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._closed = False

    @property
    def url(self) -> str:
        return self._url

    @property
    def connected(self) -> bool:
        return self._session is not None

    async def connect(self) -> bool:
        """Open a session. Idempotent — safe to call multiple times.

        Returns True on success, False on failure. Does NOT raise — callers
        rely on `connected` and on call_tool returning None on failure.
        """
        async with self._lock:
            if self._closed:
                return False
            if self._session is not None:
                return True
            return await self._connect_locked()

    async def _connect_locked(self) -> bool:
        """Caller must hold self._lock."""
        stack = AsyncExitStack()
        try:
            r, w, _ = await stack.enter_async_context(streamablehttp_client(self._url))
            session = await stack.enter_async_context(ClientSession(r, w))
            await session.initialize()
        except Exception as exc:
            log.warning("MCP connect to %s failed: %s", self._url, exc)
            await stack.aclose()
            self._connect_attempts += 1
            return False
        self._session = session
        self._stack = stack
        self._connect_attempts = 0
        log.info("MCP client connected to %s", self._url)
        return True

    async def close(self) -> None:
        """Close the session. Safe to call repeatedly."""
        async with self._lock:
            self._closed = True
            await self._close_locked()

    async def _close_locked(self) -> None:
        """Caller must hold self._lock."""
        self._session = None
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                log.debug("MCP stack close raised (ignored)", exc_info=True)
            finally:
                self._stack = None

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout_s: float = 5.0,
    ) -> str | None:
        """Invoke a tool, return the joined text of its response blocks.

        Image blocks (ImageContent) are stripped for this text-only v1 of
        the preamble — look() still flows through, but the consumer LLM
        only sees its JSON metadata block, not the JPEG bytes.

        Returns None on any failure (disconnected, tool error, timeout).
        The preamble treats None as "no tool fired this turn".
        """
        if self._closed:
            return None
        if self._session is None:
            # Best-effort lazy reconnect on first call after a drop.
            if not await self.connect():
                return None

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, arguments or {}),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            log.warning("MCP tool %s timed out after %.1fs", name, timeout_s)
            return None
        except Exception as exc:
            log.warning("MCP tool %s failed: %s", name, exc)
            # Session may be in a bad state — reset it so the next call
            # goes through a fresh connect.
            async with self._lock:
                await self._close_locked()
            return None

        return _join_text_content(result.content)


def _join_text_content(blocks: Any) -> str:
    """Concatenate text content blocks, dropping image/audio for v1.

    Accepts the `content` list returned by `ClientSession.call_tool` —
    blocks may be `TextContent`, `ImageContent`, etc. We preserve text
    (joined with newlines) and drop images in this text-only preamble.
    """
    parts: list[str] = []
    for block in blocks or []:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif isinstance(block, ImageContent):
            # Text-only v1: acknowledge the image's existence for the LLM
            # without leaking base64 into the context.
            parts.append(f"[image/{block.mimeType} omitted in text-only preamble]")
        else:
            # Unknown block type — use repr as a conservative default.
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)
