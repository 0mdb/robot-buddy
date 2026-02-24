"""Tests for /converse robot session ownership, preemption, and history stash."""

from __future__ import annotations

import asyncio

import pytest

from app.admission import ConverseSessionRegistry
from app.llm.conversation import ConversationHistory
from app.routers.converse import converse


class _FakeWebSocket:
    def __init__(self, *, query_params: dict[str, str] | None = None) -> None:
        self.query_params = query_params or {}
        self.close_code: int | None = None
        self.close_reason: str | None = None

    async def close(self, *, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code
        self.close_reason = reason


class _CloseCapturingWebSocket:
    def __init__(self) -> None:
        self.closed: list[tuple[int, str | None]] = []

    async def close(self, *, code: int = 1000, reason: str | None = None) -> None:
        self.closed.append((code, reason))


@pytest.mark.asyncio
async def test_converse_requires_robot_id():
    ws = _FakeWebSocket()
    await converse(ws)  # type: ignore[arg-type]
    assert ws.close_code == 4400
    assert ws.close_reason == "missing_robot_id"


@pytest.mark.asyncio
async def test_registry_register_same_robot_preempts_older_session():
    reg = ConverseSessionRegistry()

    ws1 = _CloseCapturingWebSocket()
    assert await reg.register(robot_id="robot-1", websocket=ws1) is None

    ws2 = _CloseCapturingWebSocket()
    old_ws = await reg.register(robot_id="robot-1", websocket=ws2)
    assert old_ws is ws1

    await old_ws.close(code=4001, reason="replaced_by_newer_session")
    assert ws1.closed == [(4001, "replaced_by_newer_session")]
    assert reg.snapshot()["preempted"] == 1


# ── History stash unit tests (ConverseSessionRegistry) ────────────────


@pytest.mark.asyncio
async def test_stash_and_restore_history():
    """History is stashed on unregister and restored on next take."""
    reg = ConverseSessionRegistry()
    ws = object()

    await reg.register(robot_id="r1", websocket=ws)

    history = ConversationHistory(max_turns=20)
    history.add_user("hello")
    history.add_assistant("hi", emotion="happy")
    assert history.turn_count == 1

    await reg.unregister(robot_id="r1", websocket=ws, history=history)

    restored = reg.take_stashed_history("r1")
    assert restored is history
    assert restored.turn_count == 1

    snap = reg.snapshot()
    assert snap["stash_hits"] == 1
    assert snap["stashed"] == 0  # taken, no longer stashed


@pytest.mark.asyncio
async def test_stash_empty_history_not_stored():
    """An empty history (0 turns) should not be stashed."""
    reg = ConverseSessionRegistry()
    ws = object()

    await reg.register(robot_id="r1", websocket=ws)
    await reg.unregister(robot_id="r1", websocket=ws, history=ConversationHistory())

    assert reg.take_stashed_history("r1") is None
    assert reg.snapshot()["stashed"] == 0


@pytest.mark.asyncio
async def test_stash_ttl_expiry():
    """Stashed history expires after TTL."""
    reg = ConverseSessionRegistry(stash_ttl_s=0.05)  # 50ms TTL
    ws = object()

    await reg.register(robot_id="r1", websocket=ws)
    history = ConversationHistory(max_turns=20)
    history.add_user("test")
    history.add_assistant("reply")
    await reg.unregister(robot_id="r1", websocket=ws, history=history)

    # Wait for TTL to expire.
    await asyncio.sleep(0.1)

    assert reg.take_stashed_history("r1") is None
    assert reg.snapshot()["stash_expired"] >= 1


@pytest.mark.asyncio
async def test_stash_no_history_kwarg():
    """Unregister without history kwarg works (backward-compatible)."""
    reg = ConverseSessionRegistry()
    ws = object()

    await reg.register(robot_id="r1", websocket=ws)
    await reg.unregister(robot_id="r1", websocket=ws)

    assert reg.take_stashed_history("r1") is None


@pytest.mark.asyncio
async def test_stash_overwrite_on_new_disconnect():
    """A newer disconnect replaces the stashed history."""
    reg = ConverseSessionRegistry()

    h1 = ConversationHistory(max_turns=20)
    h1.add_user("first")
    h1.add_assistant("a1")

    h2 = ConversationHistory(max_turns=20)
    h2.add_user("second")
    h2.add_assistant("a2")
    h2.add_user("third")
    h2.add_assistant("a3")

    ws1, ws2 = object(), object()

    await reg.register(robot_id="r1", websocket=ws1)
    await reg.unregister(robot_id="r1", websocket=ws1, history=h1)

    await reg.register(robot_id="r1", websocket=ws2)
    await reg.unregister(robot_id="r1", websocket=ws2, history=h2)

    restored = reg.take_stashed_history("r1")
    assert restored is h2
    assert restored.turn_count == 2


@pytest.mark.asyncio
async def test_snapshot_includes_stash_fields():
    """Snapshot includes stash metrics."""
    reg = ConverseSessionRegistry()
    snap = reg.snapshot()
    assert "stashed" in snap
    assert "stash_hits" in snap
    assert "stash_expired" in snap


# ── Max-turns overflow (B6) ──────────────────────────────────────────


def test_converse_history_survives_max_turns_overflow():
    """History compresses rather than crashing when turns exceed max_turns."""
    h = ConversationHistory(max_turns=5)
    # Add more turns than the max — should not raise
    for i in range(10):
        h.add_user(f"question {i}")
        h.add_assistant(f"answer {i}", emotion="happy")

    msgs = h.to_ollama_messages()
    # Should have system + summary + recent window — not crash
    assert len(msgs) >= 3
    assert msgs[0]["role"] == "system"


# ── Disconnect cleanup (B6) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_disconnect_cleanup_leaves_clean_state():
    """After unregister, the robot_id slot is free for a new connection."""
    reg = ConverseSessionRegistry()
    ws = object()

    await reg.register(robot_id="r1", websocket=ws)
    snap = reg.snapshot()
    assert snap["active_sessions"] == 1

    await reg.unregister(robot_id="r1", websocket=ws)
    snap = reg.snapshot()
    assert snap["active_sessions"] == 0

    # Can register again without preemption
    ws2 = object()
    await reg.register(robot_id="r1", websocket=ws2)
    snap = reg.snapshot()
    assert snap["active_sessions"] == 1
