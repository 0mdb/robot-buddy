"""Hybrid tool-use preamble for the conversation pipeline (task #7).

For each /converse turn, before we stream the main ConversationResponseV2
response, we run a short tool-selection pass: Gemma decides whether to
call one MCP tool (look / get_memory / recent_events) or none. If a tool
fires, its text result is injected as a transient system message so the
streamed response can reference it.

Hard constraints:
- 500 ms total budget from call to completion. Enforced via asyncio.wait_for.
  If we blow the budget, we abandon the tool and fall through to a normal
  streaming turn — the user never sees a preamble-induced hang.
- One tool per turn in v1 (max configurable via settings, but chaining is
  out of scope for this phase).
- Absolutely no exceptions escape: any failure returns `PreambleResult(None)`
  and the caller proceeds as if the preamble was off.

The prompt + parser + schema come from `app.eval.harness` so the BFCL-style
eval gate and production share the exact same code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.eval.harness import (
    NO_TOOL,
    TOOL_SCHEMAS,
    TOOL_SELECTION_JSON_SCHEMA,
    build_tool_selection_prompt,
    parse_tool_selection,
)

if TYPE_CHECKING:
    from app.llm.base import PlannerLLMBackend
    from app.llm.mcp_client import McpClient

log = logging.getLogger(__name__)

# Backend-side tool-selection generation should be very fast (128 tokens @
# greedy). This ceiling is applied in addition to the overall budget.
_SELECTION_MAX_TOKENS = 128
_SELECTION_TEMPERATURE = 0.0

# Allow-list of tool names we'll actually dispatch against the MCP client.
_ALLOWED_TOOLS = frozenset(t.name for t in TOOL_SCHEMAS)


@dataclass(slots=True)
class PreambleResult:
    """Outcome of one preamble pass.

    tool_name is None when no tool fired (model picked NO_TOOL, error, or
    budget blown). When a tool fired, `tool_result_msg` holds the system
    message to inject into the conversation pipeline.
    """

    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result_msg: str | None = None
    latency_ms: float = 0.0
    ok: bool = True
    reason: str = ""


async def run_preamble(
    backend: PlannerLLMBackend,
    mcp_client: McpClient | None,
    user_text: str,
    *,
    budget_ms: int = 500,
) -> PreambleResult:
    """Run one tool-selection pass and optionally invoke the chosen tool.

    Never raises. On any failure, returns a PreambleResult with tool_name
    None — the caller proceeds as if the preamble was disabled.
    """
    t0 = time.monotonic()
    deadline = t0 + max(0.1, budget_ms / 1000.0)

    generate_json_once = getattr(backend, "generate_json_once", None)
    if generate_json_once is None:
        return PreambleResult(
            ok=False,
            reason="backend_has_no_generate_json_once",
            latency_ms=_elapsed_ms(t0),
        )

    system_prompt = build_tool_selection_prompt()

    # Step 1: selection — ask Gemma which tool to call (if any).
    try:
        remaining = max(0.05, deadline - time.monotonic())
        raw = await asyncio.wait_for(
            generate_json_once(
                system_prompt,
                user_text,
                schema=TOOL_SELECTION_JSON_SCHEMA,
                max_tokens=_SELECTION_MAX_TOKENS,
                temperature=_SELECTION_TEMPERATURE,
                request_tag="preamble-select",
            ),
            timeout=remaining,
        )
    except asyncio.TimeoutError:
        return PreambleResult(
            ok=False,
            reason="selection_timeout",
            latency_ms=_elapsed_ms(t0),
        )
    except Exception as exc:
        log.warning("preamble selection failed: %s", exc)
        return PreambleResult(
            ok=False,
            reason=f"selection_error:{type(exc).__name__}",
            latency_ms=_elapsed_ms(t0),
        )

    parsed = parse_tool_selection(raw)
    if parsed is None:
        return PreambleResult(
            ok=False,
            reason="selection_unparseable",
            latency_ms=_elapsed_ms(t0),
        )

    tool_name = parsed["tool"]
    tool_args = parsed["args"]

    if tool_name == NO_TOOL:
        return PreambleResult(
            tool_name=None,
            ok=True,
            reason="no_tool_needed",
            latency_ms=_elapsed_ms(t0),
        )

    if tool_name not in _ALLOWED_TOOLS:
        return PreambleResult(
            ok=False,
            reason=f"tool_not_allowed:{tool_name}",
            latency_ms=_elapsed_ms(t0),
        )

    if mcp_client is None:
        return PreambleResult(
            ok=False,
            reason="mcp_client_unavailable",
            latency_ms=_elapsed_ms(t0),
        )

    # Step 2: execution — call the MCP tool against the remaining budget.
    remaining = max(0.05, deadline - time.monotonic())
    try:
        tool_text = await asyncio.wait_for(
            mcp_client.call_tool(tool_name, tool_args, timeout_s=remaining),
            timeout=remaining,
        )
    except asyncio.TimeoutError:
        return PreambleResult(
            tool_name=tool_name,
            tool_args=tool_args,
            ok=False,
            reason="tool_timeout",
            latency_ms=_elapsed_ms(t0),
        )
    except Exception as exc:
        log.warning("preamble tool %s raised: %s", tool_name, exc)
        return PreambleResult(
            tool_name=tool_name,
            tool_args=tool_args,
            ok=False,
            reason=f"tool_error:{type(exc).__name__}",
            latency_ms=_elapsed_ms(t0),
        )

    if tool_text is None:
        return PreambleResult(
            tool_name=tool_name,
            tool_args=tool_args,
            ok=False,
            reason="tool_returned_none",
            latency_ms=_elapsed_ms(t0),
        )

    msg = _format_tool_result_msg(tool_name, tool_args, tool_text)
    return PreambleResult(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result_msg=msg,
        ok=True,
        reason="ok",
        latency_ms=_elapsed_ms(t0),
    )


def _format_tool_result_msg(tool: str, args: dict, result_text: str) -> str:
    """Build the system-message text injected before the user turn."""
    args_json = json.dumps(args, separators=(",", ":"), sort_keys=True)
    return (
        f"[tool_result]\n"
        f"tool: {tool}\n"
        f"args: {args_json}\n"
        f"result: {result_text}\n"
        f"[/tool_result]\n"
        "Use this result to ground your next response. Do not call tools again."
    )


def _elapsed_ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000.0, 1)
