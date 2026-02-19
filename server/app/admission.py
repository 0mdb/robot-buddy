"""Admission control helpers for plan and conversation endpoints."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


class PlanAdmissionGate:
    """Non-blocking inflight limiter for /plan requests."""

    def __init__(self, max_inflight: int = 1) -> None:
        self._max_inflight = max(1, int(max_inflight))
        self._inflight = 0
        self._admitted = 0
        self._rejected = 0
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._inflight >= self._max_inflight:
                self._rejected += 1
                return False
            self._inflight += 1
            self._admitted += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._inflight > 0:
                self._inflight -= 1

    def snapshot(self) -> dict[str, int]:
        return {
            "max_inflight": self._max_inflight,
            "inflight": self._inflight,
            "admitted": self._admitted,
            "rejected": self._rejected,
        }


@dataclass(slots=True)
class _ConverseSession:
    websocket: Any
    connected_mono_ms: int
    session_seq: int | None
    session_monotonic_ts_ms: int | None


class ConverseSessionRegistry:
    """Tracks active /converse sessions keyed by robot_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, _ConverseSession] = {}
        self._registered = 0
        self._preempted = 0
        self._unregistered = 0
        self._lock = asyncio.Lock()

    async def register(
        self,
        *,
        robot_id: str,
        websocket: Any,
        session_seq: int | None = None,
        session_monotonic_ts_ms: int | None = None,
    ) -> Any | None:
        """Register a session and return previous websocket if replaced."""
        rid = robot_id.strip()
        if not rid:
            return None

        async with self._lock:
            old = self._sessions.get(rid)
            self._sessions[rid] = _ConverseSession(
                websocket=websocket,
                connected_mono_ms=int(time.monotonic() * 1000),
                session_seq=session_seq,
                session_monotonic_ts_ms=session_monotonic_ts_ms,
            )
            self._registered += 1
            if old is not None and old.websocket is not websocket:
                self._preempted += 1
                return old.websocket
            return None

    async def unregister(self, *, robot_id: str, websocket: Any) -> None:
        rid = robot_id.strip()
        if not rid:
            return
        async with self._lock:
            existing = self._sessions.get(rid)
            if existing is not None and existing.websocket is websocket:
                del self._sessions[rid]
                self._unregistered += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_sessions": len(self._sessions),
            "registered": self._registered,
            "preempted": self._preempted,
            "unregistered": self._unregistered,
            "robots": sorted(self._sessions.keys()),
        }
