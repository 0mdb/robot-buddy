"""/converse speculative turns: start on a tentative end of utterance, hold the output
until the real one confirms it, drop it (and its history) if the speaker resumes."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import WebSocketDisconnect

from app.admission import ConverseSessionRegistry
from app.routers import converse as conv


class _ScriptedWS:
    """Feeds client messages from a queue; records what the server sends and when."""

    def __init__(self, robot_id: str = "spec-test") -> None:
        self.query_params = {"robot_id": robot_id}
        self.inbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                converse_registry=ConverseSessionRegistry(),
                llm=object(),
                mcp_client=None,
            )
        )

    async def accept(self) -> None:
        pass

    async def close(self, **_: Any) -> None:
        pass

    async def receive_json(self) -> dict[str, Any]:
        msg = await self.inbox.get()
        if msg is None:
            raise WebSocketDisconnect()
        return msg

    async def send_json(self, msg: dict[str, Any]) -> None:
        self.sent.append(msg)

    def types(self) -> list[str]:
        return [m["type"] for m in self.sent if m["type"] != "listening"]


def _audio(n: int = 3200) -> dict[str, Any]:
    return {"type": "audio", "data": base64.b64encode(b"\x01\x00" * (n // 2)).decode()}


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"stt": [], "histories": []}

    async def stt(pcm: bytes) -> str:
        seen["stt"].append(len(pcm))
        await asyncio.sleep(0.01)
        return f"words {len(pcm)}"

    async def gen(ws: Any, llm: Any, history: Any, user_text: str, **_: Any) -> None:
        history.add_user(user_text)
        await ws.send_json({"type": "emotion", "emotion": "happy"})
        await asyncio.sleep(0.01)
        await ws.send_json({"type": "audio", "data": ""})
        history.add_assistant("reply", emotion="happy")
        await ws.send_json({"type": "done"})
        seen["histories"].append(history)

    monkeypatch.setattr(conv, "_transcribe_audio", stt)
    monkeypatch.setattr(conv, "_generate_and_stream", gen)
    return seen


async def _run(ws: _ScriptedWS, steps: list[Any]) -> None:
    task = asyncio.create_task(conv.converse(ws))  # type: ignore[arg-type]
    for step in steps:
        if isinstance(step, float):
            await asyncio.sleep(step)
        else:
            await ws.inbox.put(step)
            await asyncio.sleep(0)
    await ws.inbox.put(None)
    await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_commit_releases_the_held_turn(fakes: dict[str, Any]) -> None:
    ws = _ScriptedWS()
    seen_before: list[str] = []

    async def snapshot() -> None:
        seen_before.extend(ws.types())

    task = asyncio.create_task(conv.converse(ws))  # type: ignore[arg-type]
    await ws.inbox.put(_audio())
    await ws.inbox.put({"type": "end_utterance", "tentative": True})
    await asyncio.sleep(0.1)  # the speculation runs to completion, all held
    await snapshot()
    await ws.inbox.put(_audio())  # trailing silence after the pause
    await ws.inbox.put({"type": "end_utterance"})
    await asyncio.sleep(0.05)
    await ws.inbox.put(None)
    await asyncio.wait_for(task, 2)

    assert seen_before == []  # nothing escaped before the real end of utterance
    assert ws.types() == ["transcription", "emotion", "audio", "done"]
    assert fakes["stt"] == [3200]  # transcribed once, at the pause
    assert fakes["histories"][-1].turn_count == 1


@pytest.mark.asyncio
async def test_resume_drops_the_speculation_and_its_history(
    fakes: dict[str, Any],
) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            _audio(),
            {"type": "end_utterance", "tentative": True},
            0.1,
            {"type": "resume"},
            _audio(),  # the rest of the sentence
            {"type": "end_utterance"},
            0.1,
        ],
    )
    # Two transcriptions (the dropped one and the whole utterance); one turn sent.
    assert fakes["stt"] == [3200, 6400]
    assert ws.types() == ["transcription", "emotion", "audio", "done"]
    assert [m["text"] for m in ws.sent if m["type"] == "transcription"] == [
        "words 6400"
    ]
    assert fakes["histories"][-1].turn_count == 1  # the dropped turn was rolled back


@pytest.mark.asyncio
async def test_plain_end_of_utterance_unchanged(fakes: dict[str, Any]) -> None:
    ws = _ScriptedWS()
    await _run(ws, [_audio(), {"type": "end_utterance"}, 0.1])
    assert ws.types() == ["transcription", "emotion", "audio", "done"]


@pytest.mark.asyncio
async def test_gated_ws_keeps_order_across_commit() -> None:
    sent: list[int] = []

    class Sink:
        async def send_json(self, m: dict[str, Any]) -> None:
            sent.append(int(m["n"]))
            await asyncio.sleep(0)

    gate = conv._GatedWS(Sink())  # type: ignore[arg-type]
    for i in range(3):
        await gate.send_json({"n": i})

    async def producer() -> None:
        for i in range(3, 6):
            await gate.send_json({"n": i})
            await asyncio.sleep(0)

    await asyncio.gather(gate.commit(), producer())
    assert sent == list(range(6))


@pytest.mark.parametrize(
    ("heard", "kept"),
    [
        ("Alexa, what's my dog called?", "what's my dog called?"),
        ("alexa what's my dog called", "what's my dog called"),
        ("Hey buddy, can we play?", "can we play?"),
        ("Alexa.", ""),
        ("I like Alexa's voice", "I like Alexa's voice"),
        ("Why is the sky blue?", "Why is the sky blue?"),
    ],
)
def test_strip_wake_word(heard: str, kept: str) -> None:
    assert conv.strip_wake_word(heard) == kept


@pytest.fixture
def slow_gen(fakes: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A reply that takes a while to start, so a late resume can land before its audio."""

    async def gen(ws: Any, llm: Any, history: Any, user_text: str, **_: Any) -> None:
        history.add_user(user_text)
        await asyncio.sleep(0.15)
        await ws.send_json({"type": "audio", "data": ""})
        history.add_assistant("reply", emotion="happy")
        await ws.send_json({"type": "done"})
        fakes["histories"].append(history)

    monkeypatch.setattr(conv, "_generate_and_stream", gen)
    return fakes


@pytest.mark.asyncio
async def test_late_resume_drops_the_committed_turn_and_merges_its_audio(
    slow_gen: dict[str, Any],
) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            _audio(),
            {"type": "end_utterance"},
            0.05,  # transcribed, reply not started
            {"type": "resume"},
            _audio(),  # the child goes on
            {"type": "end_utterance"},
            0.3,
        ],
    )
    assert slow_gen["stt"] == [3200, 6400]  # the second turn hears the whole utterance
    assert [m["text"] for m in ws.sent if m["type"] == "transcription"][-1] == (
        "words 6400"
    )
    assert [m["type"] for m in ws.sent].count("done") == 1
    assert slow_gen["histories"][-1].turn_count == 1  # the dropped turn rolled back


@pytest.mark.asyncio
async def test_late_resume_after_a_committed_speculation(
    slow_gen: dict[str, Any],
) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            _audio(),
            {"type": "end_utterance", "tentative": True},
            0.02,
            {"type": "end_utterance"},  # committed
            0.05,
            {"type": "resume"},
            _audio(),
            {"type": "end_utterance"},
            0.3,
        ],
    )
    assert slow_gen["stt"][-1] == 6400
    assert [m["type"] for m in ws.sent].count("done") == 1
    assert slow_gen["histories"][-1].turn_count == 1


@pytest.mark.asyncio
async def test_audio_heard_while_a_turn_finishes_is_discarded(
    slow_gen: dict[str, Any],
) -> None:
    ws = _ScriptedWS()
    await _run(
        ws,
        [
            _audio(),
            {"type": "end_utterance"},
            _audio(1600),  # noise after the end of utterance, no resume
            0.3,  # the turn finishes
            _audio(),  # the next utterance
            {"type": "end_utterance"},
            0.3,
        ],
    )
    assert slow_gen["stt"] == [3200, 3200]
    assert slow_gen["histories"][-1].turn_count == 2


@pytest.mark.asyncio
async def test_a_long_turn_keeps_its_newest_audio(
    fakes: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the buffer cap the oldest audio goes, not the whole turn: clearing it threw
    away what the child had just said and sent an error that ended the conversation."""
    monkeypatch.setattr(conv, "_MAX_AUDIO_BUFFER_BYTES", 8000)
    ws = _ScriptedWS()
    await _run(ws, [*[_audio() for _ in range(5)], {"type": "end_utterance"}, 0.1])
    assert fakes["stt"] == [8000]
    assert ws.types() == ["transcription", "emotion", "audio", "done"]


def test_trim_oldest_keeps_whole_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conv, "_MAX_AUDIO_BUFFER_BYTES", 10)
    buf = bytearray(range(13))
    conv._trim_oldest(buf)
    assert bytes(buf) == bytes(range(4, 13))  # 3 over → 4 dropped, sample-aligned
