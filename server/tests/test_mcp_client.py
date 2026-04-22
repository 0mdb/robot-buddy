"""Unit tests for McpClient.

The MCP SDK's ClientSession talks over a transport we don't own, so these
tests focus on the lifecycle + failure-handling logic we wrote (the
connect guard, close idempotency, text joining, image decoding). The
live integration test is `just run-server` + `python -m app.eval` against
the running Pi, not a pytest.
"""

from __future__ import annotations

import base64
import io
import types
from typing import Any
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.llm.mcp_client import McpClient, _process_mcp_content
from mcp.types import ImageContent, TextContent


def _make_b64_jpeg(color: str = "red") -> str:
    """Generate a tiny solid-color JPEG as base64 string."""
    img = Image.new("RGB", (16, 16), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


class TestProcessMcpContent:
    def test_joins_plain_text_blocks(self):
        blocks = [
            TextContent(type="text", text="first"),
            TextContent(type="text", text="second"),
        ]
        text, images = _process_mcp_content(blocks)
        assert text == "first\nsecond"
        assert images == []

    def test_preserves_and_decodes_image(self):
        data = _make_b64_jpeg("red")
        blocks = [
            ImageContent(type="image", data=data, mimeType="image/jpeg"),
            TextContent(type="text", text="meta"),
        ]
        text, images = _process_mcp_content(blocks)
        assert text == "meta"
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)
        assert images[0].size == (16, 16)

    def test_base64_decode_failure_drops_image_keeps_text(self):
        blocks = [
            ImageContent(type="image", data="not-base64!!", mimeType="image/jpeg"),
            TextContent(type="text", text="fallback"),
        ]
        text, images = _process_mcp_content(blocks)
        assert text == "fallback"
        assert images == []  # malformed base64 silently dropped

    def test_garbage_image_payload_dropped(self):
        # Valid base64 but not a real image
        garbage = base64.b64encode(b"hello world not a jpeg").decode()
        blocks = [
            ImageContent(type="image", data=garbage, mimeType="image/jpeg"),
            TextContent(type="text", text="ok"),
        ]
        text, images = _process_mcp_content(blocks)
        assert text == "ok"
        assert images == []

    def test_empty_list_is_empty(self):
        assert _process_mcp_content([]) == ("", [])

    def test_none_input_is_empty(self):
        assert _process_mcp_content(None) == ("", [])

    def test_unknown_block_with_text_attr(self):
        blk = types.SimpleNamespace(text="surprise")
        text, images = _process_mcp_content([blk])
        assert text == "surprise"
        assert images == []


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
    async def test_call_tool_returns_text_and_images_tuple(self):
        """Inject a fake session returning text+image; verify shape."""
        client = McpClient("http://test/mcp/")

        class FakeResult:
            def __init__(self, content):
                self.content = content

        data = _make_b64_jpeg("blue")
        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            return_value=FakeResult(
                [
                    ImageContent(type="image", data=data, mimeType="image/jpeg"),
                    TextContent(type="text", text='{"ok": true}'),
                ]
            )
        )
        client._session = fake_session  # noqa: SLF001 — test fixture

        result = await client.call_tool("look", {"hint": "sky"})
        assert result is not None
        text, images = result
        assert text == '{"ok": true}'
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)
        fake_session.call_tool.assert_awaited_once_with("look", {"hint": "sky"})

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
