"""Preamble latency against its budget (Vantage SIM-INTERACTION, stage 1 "Caveats for the robot").

The conversation preamble has ``settings.mcp_tool_budget_ms`` (500 ms) for tool selection plus
the tool call. If it overruns, the turn silently proceeds with no tool: no memory, no camera
frame. The L1 harness allows 10 s over HTTP, so it never measured that budget.

This times the *selection* step, the server's own ``run_preamble`` with the same prompt, schema,
128-token cap, and greedy decoding, over every tool-selection scenario and every scripted persona
turn. The tool call is served instantly by a stub, because the real one is a network hop to the
robot's MCP server that cannot be measured here. Two passes:

- budget lifted (10 s): the true selection latency distribution;
- budget as configured: how many turns would lose their tool.

The model is reached over an OpenAI-compatible endpoint rather than the server's in-process
engine, which adds a few ms of HTTP; and nothing else is using the GPU (in production, Orpheus
and STT share it). Both make these numbers a floor, not a ceiling.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from typing import Any

from app.config import settings
from app.eval.converse_sim import ChatFn, openai_chat
from app.eval.harness import SCENARIOS
from app.eval.personas import PERSONAS
from app.llm.preamble import run_preamble


class _Backend:
    def __init__(self, chat: ChatFn) -> None:
        self._chat = chat

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
        del (
            max_tokens,
            request_tag,
        )  # max_tokens is fixed on the ChatFn (128, as the server)
        return await self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            schema,
            temperature,
        )


class _InstantMcp:
    async def call_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        timeout_s: float = 1.0,
        turn_id: Any = None,
    ) -> tuple[str, list[Any]]:
        del name, args, timeout_s, turn_id
        return json.dumps({"entries": [], "entry_count": 0}), []


def texts() -> list[str]:
    out = [s.user_text for s in SCENARIOS]
    out += [t.text for p in PERSONAS for t in p.turns]
    return out


def _pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


async def _main(args: Any) -> int:
    import httpx

    extra = (
        {"chat_template_kwargs": {"enable_thinking": False}}
        if args.no_thinking
        else None
    )
    budget = settings.mcp_tool_budget_ms
    items = texts()
    lifted: list[float] = []
    outcomes: dict[str, int] = {}
    async with httpx.AsyncClient() as client:
        chat = openai_chat(
            client, args.url, args.model, extra_body=extra, max_tokens=128
        )
        backend, mcp = _Backend(chat), _InstantMcp()
        t0 = time.monotonic()
        cold = (await run_preamble(backend, mcp, items[0], budget_ms=10_000)).latency_ms
        for _ in range(args.reps):
            for text in items:
                r = await run_preamble(backend, mcp, text, budget_ms=10_000)
                lifted.append(r.latency_ms)
        for _ in range(args.reps):
            for text in items:
                r = await run_preamble(backend, mcp, text, budget_ms=budget)
                key = (
                    "within budget"
                    if r.reason != "selection_timeout"
                    else "selection_timeout"
                )
                outcomes[key] = outcomes.get(key, 0) + 1
        wall = time.monotonic() - t0
    over = sum(1 for x in lifted if x > budget)
    lines = [
        f"# Preamble selection latency ({args.model})",
        "",
        f"{len(items)} texts ({len(SCENARIOS)} tool-selection scenarios + persona turns) × "
        f"{args.reps}, greedy, 128-token cap, guided by the selection schema. Budget "
        f"{budget} ms. Tool call stubbed. {wall:.0f} s.",
        "",
        "| | ms |",
        "|---|---|",
        f"| first call (cold) | {cold:.0f} |",
        f"| p50 | {statistics.median(lifted):.0f} |",
        f"| p95 | {_pct(lifted, 0.95):.0f} |",
        f"| p99 | {_pct(lifted, 0.99):.0f} |",
        f"| max | {max(lifted):.0f} |",
        "",
        f"Over budget with it lifted: **{over} / {len(lifted)}**. "
        f"With the budget enforced: {outcomes}.",
    ]
    print("\n".join(lines))
    return 0 if over == 0 else 1


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Preamble selection latency vs its budget")
    ap.add_argument("--url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--no-thinking", action="store_true")
    return asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
