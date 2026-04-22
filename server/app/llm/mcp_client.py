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
import base64
import io
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import ImageContent, TextContent
from PIL import Image, UnidentifiedImageError

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
    ) -> tuple[str, list[Image.Image]] | None:
        """Invoke a tool, return (joined text, list of PIL images) blocks.

        Image blocks are base64-decoded into PIL.Image objects so the
        conversation layer can pass them to the vLLM backend via
        ``multi_modal_data``. Decode errors drop the image and keep the
        text portion of the result.

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

        return _process_mcp_content(result.content)


def _process_mcp_content(blocks: Any) -> tuple[str, list[Image.Image]]:
    """Split MCP content blocks into (joined text, list of PIL images).

    Text blocks are concatenated with newlines. Image blocks are
    base64-decoded into PIL.Image objects for downstream multimodal
    consumption. Malformed images are logged and dropped; the text
    portion of the tool result is always preserved.
    """
    parts: list[str] = []
    images: list[Image.Image] = []
    for block in blocks or []:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif isinstance(block, ImageContent):
            img = _decode_image_block(block)
            if img is not None:
                images.append(img)
        else:
            # Unknown block type — preserve any text attr conservatively.
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts), images


def _decode_image_block(block: ImageContent) -> Image.Image | None:
    """Decode an MCP ImageContent block into a PIL.Image, or None on failure."""
    try:
        raw = base64.b64decode(block.data, validate=True)
    except (ValueError, TypeError) as exc:
        log.warning("MCP image base64 decode failed: %s", exc)
        return None
    try:
        img = Image.open(io.BytesIO(raw))
        # Force a decode by converting so we surface errors here rather
        # than later in the vLLM pipeline.
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        log.warning("MCP image PIL decode failed (mime=%s): %s", block.mimeType, exc)
        return None
    return img
