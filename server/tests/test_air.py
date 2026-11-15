"""Over-the-air rig (app.eval.air): the parts that run without a robot or a speaker."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.eval import air
from app.eval.converse_sim import _closed_schema, anthropic_chat


def test_wer() -> None:
    assert air.wer("why is the sky blue", "Why is the sky blue?") == 0.0
    assert air.wer("why is the sky blue", "why is the") == pytest.approx(0.4)
    assert air.wer("", "") == 0.0
    assert (
        air.wer("What's your favourite colour?", "What's your favorite color?") == 0.0
    )
    assert air.wer("twenty questions", "20 questions") == 0.0


def test_shape_gain_and_pitch() -> None:
    x = (np.ones(1600) * 1000).astype(np.int16).tobytes()
    assert np.frombuffer(air.shape(x, gain_db=-20), np.int16)[0] == 100
    assert len(air.shape(x, pitch=1.25)) == 2 * int(1600 / 1.25)


def test_wake_report_picks_threshold_above_near_misses() -> None:
    pos = [
        air.WakeClip("alexa", "zoe", 1.0, 0, True, peak=p) for p in (0.9, 0.8, 0.7, 0.4)
    ]
    neg = [air.WakeClip("alaska", "zoe", 1.0, 0, False, peak=p) for p in (0.1, 0.35)]
    _, best = air.wake_report(pos + neg)
    # Margin of 0.1 above the worst near-miss (0.35), keeping the most positives.
    assert best == pytest.approx(0.45)


# ── run_talk against a fake robot ────────────────────────────────────


WAKE_LEVEL, SPEECH_LEVEL = 1000, 2000


class FakeVoices:
    async def say(self, text: str, voice: str = "") -> bytes:
        level = WAKE_LEVEL if text == air.WAKE else SPEECH_LEVEL
        return (np.ones(320) * level).astype(np.int16).tobytes()


class FakeRobot:
    """Emits what the supervisor would: wake opens a session; an utterance gets end of
    utterance -> transcript -> reply -> speech; after the reply a follow-up session opens
    unless `no_follow_up` says otherwise."""

    def __init__(self, *, no_follow_up: set[int] | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.t = 1000.0
        self.turn = 0
        self.no_follow_up = no_follow_up or set()
        self.cancelled = 0

    def emit(self, type_: str, dt: float = 10.0, **kw: Any) -> None:
        self.t += dt
        self.events.append({"type": type_, "ts_mono_ms": self.t, **kw})

    def on_play(self, pcm: bytes) -> None:
        level = int(np.abs(np.frombuffer(pcm, np.int16)).max())
        if level < SPEECH_LEVEL * 0.9:  # the wake word
            self.emit("conv.session.started")
            return
        self.emit("ear.event.end_of_utterance", 800, silence_ms=800)
        self.emit("ai.conversation.transcription", 300, text=f"line {self.turn}")
        self.emit("ai.conversation.assistant_text", 500, text=f"reply {self.turn}")
        self.emit("ai.conversation.first_audio", 1, roundtrip_ms=900)
        self.emit("tts.event.started", 400)
        self.emit("tts.event.finished", 3000)
        if self.turn not in self.no_follow_up:
            self.emit("conv.session.started", 400)
        self.turn += 1

    mark = air.Robot.mark
    since = air.Robot.since

    async def wait(
        self, mark: int, type_: str, timeout: float, where: Any = None
    ) -> Any:
        for e in self.since(mark, type_):
            if where is None or where(e):
                return e
        return None

    async def idle(self, timeout: float = 0) -> bool:
        return True

    async def cancel(self) -> None:
        self.cancelled += 1


class FakeSpeaker:
    def __init__(self, robot: FakeRobot) -> None:
        self.robot = robot

    async def play(self, pcm: bytes) -> None:
        self.robot.on_play(pcm)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    real = asyncio.sleep

    async def fast(_s: float) -> None:
        await real(0)

    monkeypatch.setattr(air.asyncio, "sleep", fast)


@pytest.mark.asyncio
async def test_talk_uses_follow_up_window_and_measures_latency() -> None:
    robot = FakeRobot()
    turns = await air.run_talk(
        robot,  # type: ignore[arg-type]
        FakeVoices(),  # type: ignore[arg-type]
        FakeSpeaker(robot),  # type: ignore[arg-type]
        air.scripted_kid(["one", "two", "three"]),
        voice="zoe",
        pitch=1.0,
    )
    assert [t.reply for t in turns] == ["reply 0", "reply 1", "reply 2"]
    assert [t.follow_up for t in turns] == [None, True, True]
    # end of speech = EoU - 800 ms silence; first sound 300+500+1+400 ms after the EoU.
    assert turns[0].heard_latency_ms == pytest.approx(800 + 300 + 500 + 1 + 400)
    assert turns[0].reply_s == pytest.approx(3.0)
    assert all(not t.failures for t in turns)
    assert robot.cancelled == 1


@pytest.mark.asyncio
async def test_talk_falls_back_to_wake_word_when_window_misses() -> None:
    robot = FakeRobot(no_follow_up={0})
    turns = await air.run_talk(
        robot,  # type: ignore[arg-type]
        FakeVoices(),  # type: ignore[arg-type]
        FakeSpeaker(robot),  # type: ignore[arg-type]
        air.scripted_kid(["one", "two"]),
        voice="zoe",
        pitch=1.0,
        expect=lambda i: ("reply 1",) if i == 1 else ("nope",),
    )
    assert [t.follow_up for t in turns] == [None, False]
    assert turns[0].failures == ["reply lacks nope"]
    assert turns[1].failures == []


# ── Claude ChatFn (no network) ───────────────────────────────────────


class FakeMessages:
    def __init__(self) -> None:
        self.kw: dict[str, Any] = {}

    async def create(self, **kw: Any) -> Any:
        self.kw = kw
        block = SimpleNamespace(type="text", text=" yeah ")
        return SimpleNamespace(stop_reason="end_turn", content=[block])


@pytest.mark.asyncio
async def test_anthropic_chat_shapes_messages() -> None:
    msgs = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=msgs))
    chat = anthropic_chat(client=client)
    out = await chat(
        [
            {"role": "system", "content": "You are a kid."},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "Hello! What's your name?"},
        ],
        {"type": "object", "properties": {"a": {"type": "object", "properties": {}}}},
        0.7,
    )
    assert out == "yeah"
    kw = msgs.kw
    assert kw["system"] == "You are a kid."
    assert [m["role"] for m in kw["messages"]] == ["user", "assistant", "user"]
    assert "temperature" not in kw
    fmt = kw["output_config"]["format"]["schema"]
    assert fmt["additionalProperties"] is False
    assert fmt["properties"]["a"]["additionalProperties"] is False
    assert kw["extra_body"] == {"fallbacks": "default"}


def test_closed_schema_leaves_input_alone() -> None:
    s = {"type": "object", "properties": {}}
    _closed_schema(s)
    assert "additionalProperties" not in s
