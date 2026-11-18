"""Opt-in conversation history: nothing kept while off, robot-local, short-lived, deleted
with the household. Synthetic names and text only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.core.conversation_history import ConversationHistory, history_path
from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import (
    AI_CONVERSATION_ASSISTANT_TEXT,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_TRANSCRIPTION,
)
from supervisor.personality import roster as hh
from supervisor.tests.test_api import FakeTick, FakeWorkers


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def _hist(tmp_path, on=True, days=3.0, present=("Test Kid",)):
    state = {"on": on}
    clock = Clock()
    h = ConversationHistory(
        tmp_path / "conversation_history" / "history.jsonl",
        lambda: state["on"],
        lambda: days,
        lambda: list(present),
        clock=clock,
    )
    return h, state, clock


def _env(t: str, **payload):
    return make_envelope(t, "ai", 1, {"session_id": "s1", "turn_id": 1, **payload})


def _turn(h: ConversationHistory) -> None:
    h.feed(
        _env(
            AI_CONVERSATION_TRANSCRIPTION, text="can we play a game", stt_latency_ms=210
        )
    )
    h.feed(_env(AI_CONVERSATION_EMOTION, emotion="excited"))
    h.feed(_env(AI_CONVERSATION_ASSISTANT_TEXT, text="Yes! Let's play!"))


def test_off_keeps_nothing(tmp_path):
    h, _, _ = _hist(tmp_path, on=False)
    _turn(h)
    h.say("greeter", "Hi, Test Kid!")
    h.reply_timing(1200, 0)
    assert not h.path.exists() and h.read() == []


def test_a_turn_with_who_expression_and_timing(tmp_path):
    h, _, _ = _hist(tmp_path)
    _turn(h)
    h.reply_timing(1234.4, 1)
    h.say("greeter", "Hi, Test Kid!")
    rows = [{k: v for k, v in e.items() if k != "t"} for e in h.read()]
    assert rows == [
        {
            "role": "child",
            "text": "can we play a game",
            "session": "s1",
            "who": ["Test Kid"],
            "stt_ms": 210,
        },
        {
            "role": "buddy",
            "source": "conversation",
            "text": "Yes! Let's play!",
            "session": "s1",
            "emotion": "excited",
        },
        {"role": "timing", "reply_ms": 1234, "late_resumes": 1},
        {"role": "buddy", "source": "greeter", "text": "Hi, Test Kid!"},
    ]


def test_old_entries_expire(tmp_path):
    h, _, clock = _hist(tmp_path, days=1.0)
    h.say("planner", "old line")
    clock.t += 2 * 86400
    h.say("planner", "new line")  # the hourly prune runs on write
    assert [e["text"] for e in h.read()] == ["new line"]
    assert h.path.read_text().count("\n") == 1  # gone from the file, not just hidden


def test_clear_and_forget_everyone(tmp_path):
    roster = tmp_path / "household.toml"
    hh.save(roster, hh.add_member(hh.Roster(), name="Test Kid", kind="kid", age=6))
    h, _, _ = _hist(tmp_path)
    assert h.path == history_path(roster)
    _turn(h)
    h.clear()
    assert h.read() == []
    _turn(h)
    hh.forget_everyone(roster)
    assert not h.path.exists()


def test_api_lists_and_clears(tmp_path):
    h, _, _ = _hist(tmp_path)
    tick = FakeTick()
    tick.conversation_history = h  # type: ignore[attr-defined]
    reg = create_default_registry()
    c = TestClient(
        create_app(
            tick, reg, WsHub(), FakeWorkers(), household_path=tmp_path / "h.toml"
        )
    )
    body = c.get("/api/conversations").json()
    assert body["enabled"] is False and body["days"] == 3 and body["entries"] == []
    _turn(h)
    assert [e["role"] for e in c.get("/api/conversations").json()["entries"]] == [
        "child",
        "buddy",
    ]
    assert c.delete("/api/conversations").json() == {"ok": True}
    assert c.get("/api/conversations").json()["entries"] == []
