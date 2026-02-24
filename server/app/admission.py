"""Admission control helpers for plan and conversation endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


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


@dataclass(slots=True)
class _StashedHistory:
    """A conversation history saved after WebSocket disconnect."""

    history: Any  # ConversationHistory (avoid circular import)
    stashed_mono: float  # time.monotonic() when stashed
    turn_count: int


# Default TTL for stashed session histories (30 minutes).
_STASH_TTL_S = 30 * 60

# Max stashed sessions to prevent unbounded memory growth.
_MAX_STASHED = 50


class ConverseSessionRegistry:
    """Tracks active /converse sessions keyed by robot_id.

    Also maintains a TTL'd stash of conversation histories so that
    reconnecting within the TTL window restores prior context.
    """

    def __init__(self, *, stash_ttl_s: float = _STASH_TTL_S) -> None:
        self._sessions: dict[str, _ConverseSession] = {}
        self._stash: dict[str, _StashedHistory] = {}
        self._stash_ttl_s = stash_ttl_s
        self._registered = 0
        self._preempted = 0
        self._unregistered = 0
        self._stash_hits = 0
        self._stash_expired = 0
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

    async def unregister(
        self,
        *,
        robot_id: str,
        websocket: Any,
        history: Any | None = None,
    ) -> None:
        """Unregister a session, optionally stashing its conversation history."""
        rid = robot_id.strip()
        if not rid:
            return
        async with self._lock:
            existing = self._sessions.get(rid)
            if existing is not None and existing.websocket is websocket:
                del self._sessions[rid]
                self._unregistered += 1

            # Stash history for later reconnect if it has content.
            if (
                history is not None
                and hasattr(history, "turn_count")
                and history.turn_count > 0
            ):
                self._stash[rid] = _StashedHistory(
                    history=history,
                    stashed_mono=time.monotonic(),
                    turn_count=history.turn_count,
                )
                log.info(
                    "Stashed conversation history for %s (%d turns, TTL=%ds)",
                    rid,
                    history.turn_count,
                    int(self._stash_ttl_s),
                )
                # Evict oldest if over capacity.
                if len(self._stash) > _MAX_STASHED:
                    oldest_key = min(
                        self._stash, key=lambda k: self._stash[k].stashed_mono
                    )
                    del self._stash[oldest_key]

            # Opportunistic cleanup of expired stash entries.
            self._expire_stale_locked()

    def take_stashed_history(self, robot_id: str) -> Any | None:
        """Return and remove stashed history if it exists and hasn't expired.

        Must be called while NOT holding self._lock (it's a plain method
        for use outside the lock, since the caller decides what to do).
        """
        rid = robot_id.strip()
        stashed = self._stash.pop(rid, None)
        if stashed is None:
            return None

        age = time.monotonic() - stashed.stashed_mono
        if age > self._stash_ttl_s:
            self._stash_expired += 1
            log.info(
                "Stashed history for %s expired (age=%.0fs > TTL=%ds)",
                rid,
                age,
                int(self._stash_ttl_s),
            )
            return None

        self._stash_hits += 1
        log.info(
            "Restored stashed history for %s (%d turns, age=%.0fs)",
            rid,
            stashed.turn_count,
            age,
        )
        return stashed.history

    def _expire_stale_locked(self) -> int:
        """Remove expired stash entries (caller must hold lock or be safe)."""
        now = time.monotonic()
        expired_keys = [
            k
            for k, v in self._stash.items()
            if now - v.stashed_mono > self._stash_ttl_s
        ]
        for k in expired_keys:
            del self._stash[k]
        self._stash_expired += len(expired_keys)
        return len(expired_keys)

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_sessions": len(self._sessions),
            "registered": self._registered,
            "preempted": self._preempted,
            "unregistered": self._unregistered,
            "stashed": len(self._stash),
            "stash_hits": self._stash_hits,
            "stash_expired": self._stash_expired,
            "robots": sorted(self._sessions.keys()),
        }
