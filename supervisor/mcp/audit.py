"""Audit log + WebSocket broadcaster for MCP tool calls.

Every MCP tool invocation emits an McpAuditEntry that is:
  1. Appended to an in-memory ring buffer (for dashboard snapshot queries).
  2. Broadcast on the /ws/mcp WebSocket channel to any connected dashboards.
  3. Counted toward per-tool success/fail stats for the Phase 0 reliability gate.

Mirrors the broadcaster pattern used by WebSocketLogBroadcaster in
supervisor/api/http_server.py so the dashboard plumbing stays uniform.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(slots=True)
class McpAuditEntry:
    ts_mono: float
    tool: str
    args: dict
    ok: bool
    latency_ms: float
    result_summary: str = ""
    error: str = ""
    client: str = ""

    def to_dict(self) -> dict:
        return {
            "ts_mono": self.ts_mono,
            "tool": self.tool,
            "args": self.args,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "result_summary": self.result_summary,
            "error": self.error,
            "client": self.client,
        }


class McpAuditBroadcaster:
    """Ring buffer + fan-out for MCP tool-call audit entries."""

    def __init__(self, *, queue_maxsize: int = 256, ring_size: int = 200) -> None:
        self._clients: set[asyncio.Queue[str]] = set()
        self._queue_maxsize = queue_maxsize
        self._ring: list[McpAuditEntry] = []
        self._ring_size = ring_size
        self._tool_success: dict[str, int] = {}
        self._tool_fail: dict[str, int] = {}

    def add_client(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._clients.add(q)
        return q

    def remove_client(self, q: asyncio.Queue[str]) -> None:
        self._clients.discard(q)

    def record(self, entry: McpAuditEntry) -> None:
        self._ring.append(entry)
        if len(self._ring) > self._ring_size:
            self._ring = self._ring[-self._ring_size :]
        if entry.ok:
            self._tool_success[entry.tool] = self._tool_success.get(entry.tool, 0) + 1
        else:
            self._tool_fail[entry.tool] = self._tool_fail.get(entry.tool, 0) + 1

        payload = json.dumps(entry.to_dict())
        for q in list(self._clients):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                log.debug("mcp audit client queue full; dropping one entry")

    def snapshot(self, n: int = 50) -> list[dict]:
        return [e.to_dict() for e in self._ring[-n:]]

    def success_rate(self) -> dict[str, dict[str, float | int]]:
        out: dict[str, dict[str, float | int]] = {}
        for tool in set(self._tool_success) | set(self._tool_fail):
            s = self._tool_success.get(tool, 0)
            f = self._tool_fail.get(tool, 0)
            total = s + f
            out[tool] = {
                "success": s,
                "fail": f,
                "total": total,
                "rate": (s / total) if total else 0.0,
            }
        return out
