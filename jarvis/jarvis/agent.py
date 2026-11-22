"""One owner turn: history + text in, tool loop on Ollama, text out."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from .config import Settings
from .store import AuditLog
from .tools import ToolError, ToolRegistry

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Jarvis, a private assistant for the owner of this house. You are not \
Buddy, the children's robot, and you never talk like it.

Style: direct and terse. Answer first, in one or two short sentences, plain text \
suitable for speaking aloud. No markdown, no lists unless asked, no filler.

{abilities} If something is not available, say so plainly. You cannot change \
anything in the house yet; if asked to, say that changes are not enabled.

Now: {now}.
"""

_WITH_TOOLS = (
    "Facts: use your tools to look things up; never guess a device's state, and say "
    "so if a tool fails."
)
_NO_TOOLS = (
    "You have no tools connected right now: no house status, no accounts. Do not "
    "claim or guess anything about the house."
)

_TOOL_RESULT_MAX_CHARS = 6000


class LlmError(Exception):
    pass


@dataclass
class TurnResult:
    text: str
    speak: bool
    tools_used: list[str] = field(default_factory=list)
    latency_ms: int = 0


class Agent:
    def __init__(
        self,
        settings: Settings,
        tools: ToolRegistry,
        audit: AuditLog,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.tools = tools
        self.audit = audit
        self._http = http or httpx.AsyncClient(timeout=settings.llm_timeout_s)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "think": self.settings.ollama_think,
        }
        if self.tools.list():
            body["tools"] = self.tools.schemas()
        try:
            resp = await self._http.post(
                f"{self.settings.ollama_url}/api/chat", json=body
            )
        except httpx.HTTPError as exc:
            raise LlmError(
                f"Ollama unreachable at {self.settings.ollama_url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise LlmError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
        msg = resp.json().get("message")
        if not isinstance(msg, dict):
            raise LlmError("Ollama reply had no message")
        return msg

    async def turn(
        self,
        text: str,
        *,
        identity: str,
        device: str,
        history: list[dict[str, Any]] | None = None,
    ) -> TurnResult:
        t0 = time.monotonic()
        now = datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M %Z")
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    now=now, abilities=_WITH_TOOLS if self.tools.list() else _NO_TOOLS
                ),
            }
        ]
        for rec in history or []:
            messages.append({"role": "user", "content": rec["user"]})
            messages.append({"role": "assistant", "content": rec["reply"]})
        messages.append({"role": "user", "content": text})

        used: list[str] = []
        speak = True
        for _round in range(self.settings.max_tool_rounds + 1):
            msg = await self._chat(messages)
            calls = msg.get("tool_calls") or []
            if not calls or _round == self.settings.max_tool_rounds:
                reply = (msg.get("content") or "").strip()
                if not reply:
                    reply = (
                        "I couldn't work that out." if calls else "I have no answer."
                    )
                return TurnResult(
                    text=reply,
                    speak=speak,
                    tools_used=used,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": calls,
                }
            )
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name", ""))
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool = self.tools.get(name)
                ok = True
                try:
                    result: Any = await self.tools.call(name, args)
                except ToolError as exc:
                    ok, result = False, {"error": str(exc)}
                except Exception as exc:  # a tool bug must not kill the turn
                    log.exception("tool %s crashed", name)
                    ok, result = False, {"error": f"tool failed: {type(exc).__name__}"}
                self.audit.write(
                    "tool_call",
                    device=device,
                    identity=identity,
                    tool=name,
                    tier=tool.tier if tool else None,
                    args=args,
                    ok=ok,
                )
                used.append(name)
                if tool is not None and tool.personal:
                    speak = False
                content = json.dumps(result, ensure_ascii=False, default=str)
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": content[:_TOOL_RESULT_MAX_CHARS],
                    }
                )
        raise AssertionError("unreachable")  # pragma: no cover
