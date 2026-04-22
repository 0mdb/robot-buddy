"""Unit tests for McpClient.

The MCP SDK's ClientSession talks over a transport we don't own, so these
tests focus on the lifecycle + failure-handling logic we wrote (the
connect guard, close idempotency, text joining, image stripping). The
live integration test is `just run-server` + `python -m app.eval` against
the running Pi, not a pytest.
"""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.llm.mcp_client import McpClient, _join_text_content
from mcp.types import ImageContent, TextContent


class TestJoinTextContent:
    def test_joins_plain_text_blocks(self):
        blocks = [
            TextContent(type="text", text="first"),
            TextContent(type="text", text="second"),
        ]
        assert _join_text_content(blocks) == "first\nsecond"

    def test_strips_image_bytes_but_notes_presence(self):
        blocks = [
            ImageContent(type="image", data="BASE64==", mimeType="image/jpeg"),
            TextContent(type="text", text="meta"),
        ]
        joined = _join_text_content(blocks)
        assert "BASE64" not in joined
        assert "[image/image/jpeg omitted" in joined
        assert "meta" in joined

    def test_empty_list_is_empty(self):
        assert _join_text_content([]) == ""

    def test_none_input_is_empty(self):
        assert _join_text_content(None) == ""

    def test_unknown_block_with_text_attr(self):
        blk = types.SimpleNamespace(text="surprise")
        assert _join_text_content([blk]) == "surprise"


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_close_before_connect_is_safe(self):
        client = McpClient("http://test/mcp/")
        await client.close()
        assert client.connected is False

    @pytest.mark.asyncio
    async def test_call_tool_without_connect_returns_none(self, monkeypatch):
        client = McpClient("http://test/mcp/")

        async def failing_connect() -> bool:
            return False

        monkeypatch.setattr(client, "connect", failing_connect)
        result = await client.call_tool("look", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_call_tool_after_close_returns_none(self):
        client = McpClient("http://test/mcp/")
        await client.close()
        assert await client.call_tool("look", {}) is None

    @pytest.mark.asyncio
    async def test_call_tool_joins_text_blocks_from_session(self):
        """Inject a fake session that returns text blocks; verify joining."""
        client = McpClient("http://test/mcp/")

        class FakeResult:
            def __init__(self, content):
                self.content = content

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            return_value=FakeResult([TextContent(type="text", text='{"ok": true}')])
        )
        client._session = fake_session  # noqa: SLF001 — test fixture

        result = await client.call_tool("get_memory", {"category": "topic"})
        assert result == '{"ok": true}'
        fake_session.call_tool.assert_awaited_once_with(
            "get_memory", {"category": "topic"}
        )

    @pytest.mark.asyncio
    async def test_tool_exception_resets_session(self):
        client = McpClient("http://test/mcp/")
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=RuntimeError("boom"))
        client._session = fake_session  # noqa: SLF001

        result = await client.call_tool("look", {})
        assert result is None
        # Session was reset so the next call will try to reconnect.
        assert client._session is None  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_tool_timeout_returns_none_keeps_session(self):
        client = McpClient("http://test/mcp/")

        async def slow(*_args: Any, **_kwargs: Any) -> None:
            import asyncio

            await asyncio.sleep(10.0)

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(side_effect=slow)
        client._session = fake_session  # noqa: SLF001

        result = await client.call_tool("look", {}, timeout_s=0.05)
        assert result is None
        # Timeout should NOT wipe the session — transient slowness, session
        # itself is still valid.
        assert client._session is fake_session  # noqa: SLF001
