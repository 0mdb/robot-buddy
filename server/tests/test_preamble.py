"""Unit tests for the hybrid tool-use preamble (task #7).

Uses fake backend + fake MCP client stubs — no live vLLM or network in
the loop. The integration path (preamble → /eval/select_tool → real
Gemma → real supervisor MCP) is exercised via `just eval-tools` +
the three-path manual verification documented in the plan.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from app.llm.preamble import PreambleResult, ToolResult, run_preamble


class FakeBackend:
    """Stand-in with a settable generate_json_once coroutine."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    async def generate_json_once(
        self,
        system_prompt: str,
        user_text: str,
        *,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 128,
        temperature: float = 0.0,
        request_tag: str = "",
    ) -> str:
        self.calls.append((system_prompt, user_text, schema or {}))
        if not self._responses:
            raise RuntimeError("no more canned responses")
        return self._responses.pop(0)


class FakeMcp:
    """Stand-in for McpClient.call_tool.

    Responses can be:
      - None (tool returned nothing — propagates as failure)
      - str (legacy text-only result — wrapped as (text, []))
      - tuple[str, list[Image]] (full shape matching production client)
      - Exception (raised)
    """

    def __init__(
        self,
        responses: dict[str, str | tuple[str, list[Image.Image]] | None | Exception],
    ):
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(
        self, name: str, arguments: dict | None = None, *, timeout_s: float = 5.0
    ) -> tuple[str, list[Image.Image]] | None:
        self.calls.append((name, arguments or {}))
        if name not in self._responses:
            return None
        r = self._responses[name]
        if isinstance(r, Exception):
            raise r
        if r is None:
            return None
        if isinstance(r, str):
            return (r, [])
        return r


# ── Happy paths ────────────────────────────────────────────────────


class TestNoToolPath:
    @pytest.mark.asyncio
    async def test_returns_no_tool_on_none_selection(self):
        backend = FakeBackend(['{"tool":"none","args":{}}'])
        mcp = FakeMcp({})
        result = await run_preamble(backend, mcp, "Hi!")
        assert isinstance(result, PreambleResult)
        assert result.tool_name is None
        assert result.ok is True
        assert result.reason == "no_tool_needed"
        assert mcp.calls == []


class TestHappyToolPath:
    @pytest.mark.asyncio
    async def test_fires_chosen_tool_and_formats_result(self):
        backend = FakeBackend(['{"tool":"get_memory","args":{"category":"topic"}}'])
        mcp = FakeMcp({"get_memory": '{"entries":[{"tag":"dinos"}]}'})
        result = await run_preamble(
            backend, mcp, "We were talking about space last time."
        )
        assert result.tool_name == "get_memory"
        assert result.tool_args == {"category": "topic"}
        assert mcp.calls == [("get_memory", {"category": "topic"})]
        assert result.tool_result is not None
        assert isinstance(result.tool_result, ToolResult)
        assert "[tool_result]" in result.tool_result.text
        assert "get_memory" in result.tool_result.text
        assert "dinos" in result.tool_result.text
        assert "Do not call tools again." in result.tool_result.text
        assert result.tool_result.images == []  # text-only tool
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_look_tool_carries_image_when_present(self):
        """look() returns text metadata + an image; both should flow through."""
        img = Image.new("RGB", (16, 16), "red")
        backend = FakeBackend(['{"tool":"look","args":{"hint":"drawing"}}'])
        mcp = FakeMcp({"look": ('{"ball_detected":false,"consent":"on"}', [img])})
        result = await run_preamble(backend, mcp, "Look at what I made!")
        assert result.tool_name == "look"
        assert result.tool_result is not None
        assert "ball_detected" in result.tool_result.text
        assert len(result.tool_result.images) == 1
        assert result.tool_result.images[0] is img

    @pytest.mark.asyncio
    async def test_image_list_is_capped_at_one(self):
        imgs = [Image.new("RGB", (4, 4), c) for c in ("red", "green", "blue")]
        backend = FakeBackend(['{"tool":"look","args":{}}'])
        mcp = FakeMcp({"look": ("meta", imgs)})
        result = await run_preamble(backend, mcp, "look")
        assert result.tool_result is not None
        assert len(result.tool_result.images) == 1
        # The first image wins
        assert result.tool_result.images[0] is imgs[0]


# ── Failure modes ──────────────────────────────────────────────────


class TestFailureModes:
    @pytest.mark.asyncio
    async def test_unparseable_selection_returns_no_tool(self):
        backend = FakeBackend(["not json at all"])
        mcp = FakeMcp({})
        result = await run_preamble(backend, mcp, "anything")
        assert result.tool_name is None
        assert result.ok is False
        assert result.reason == "selection_unparseable"

    @pytest.mark.asyncio
    async def test_selection_exception_returns_no_tool(self):
        class Boom(FakeBackend):
            async def generate_json_once(self, *a, **kw):  # type: ignore[override]
                raise RuntimeError("engine died")

        result = await run_preamble(Boom([]), FakeMcp({}), "x")
        assert result.tool_name is None
        assert result.ok is False
        assert result.reason.startswith("selection_error:RuntimeError")

    @pytest.mark.asyncio
    async def test_invalid_tool_name_refused(self):
        backend = FakeBackend(['{"tool":"format_c_drive","args":{}}'])
        mcp = FakeMcp({})
        result = await run_preamble(backend, mcp, "anything")
        assert result.tool_name is None
        assert result.ok is False
        assert "tool_not_allowed" in result.reason
        assert mcp.calls == []

    @pytest.mark.asyncio
    async def test_tool_returns_none_propagates_as_failure(self):
        backend = FakeBackend(['{"tool":"look","args":{}}'])
        mcp = FakeMcp({"look": None})
        result = await run_preamble(backend, mcp, "look here")
        assert result.tool_name == "look"
        assert result.ok is False
        assert result.reason == "tool_returned_none"

    @pytest.mark.asyncio
    async def test_missing_mcp_client_short_circuits(self):
        backend = FakeBackend(['{"tool":"look","args":{}}'])
        result = await run_preamble(backend, None, "look here")
        assert result.tool_name is None
        assert result.ok is False
        assert result.reason == "mcp_client_unavailable"

    @pytest.mark.asyncio
    async def test_budget_timeout_during_selection(self):
        import asyncio

        class SlowBackend(FakeBackend):
            async def generate_json_once(self, *a, **kw):  # type: ignore[override]
                await asyncio.sleep(5.0)
                return '{"tool":"none","args":{}}'

        result = await run_preamble(SlowBackend([]), FakeMcp({}), "x", budget_ms=100)
        assert result.tool_name is None
        assert result.ok is False
        assert result.reason == "selection_timeout"

    @pytest.mark.asyncio
    async def test_backend_without_generate_json_once(self):
        fake = SimpleNamespace()  # no generate_json_once attr
        result = await run_preamble(fake, FakeMcp({}), "x")
        assert result.ok is False
        assert result.reason == "backend_has_no_generate_json_once"
