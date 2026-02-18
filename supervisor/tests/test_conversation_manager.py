"""Tests for ConversationManager server/face integration behavior."""

from __future__ import annotations

import asyncio
import base64
import sys
import types

import pytest

from supervisor.devices.conversation_manager import (
    CHUNK_BYTES,
    RECONNECT_BACKOFF_S,
    ConversationManager,
)


class FakeFace:
    def __init__(self) -> None:
        self.talking_calls: list[tuple[bool, int]] = []

    def send_talking(self, talking: bool, energy: int = 0) -> None:
        self.talking_calls.append((talking, energy))


def test_handle_audio_updates_talking_energy():
    face = FakeFace()
    cm = ConversationManager("http://127.0.0.1:8100", face=face)

    pcm = bytes([i % 256 for i in range(CHUNK_BYTES * 2 + 40)])
    msg = {"type": "audio", "data": base64.b64encode(pcm).decode("ascii")}
    cm._handle_audio(msg)

    assert face.talking_calls
    assert face.talking_calls[0][0] is True
    assert len(face.talking_calls) >= 2  # initial start + chunk energy updates


@pytest.mark.asyncio
async def test_start_reconnects_after_initial_connect_failure(monkeypatch):
    attempts = {"count": 0}

    class FakeWebSocket:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(10)
            raise StopAsyncIteration

        async def close(self):
            return None

    async def fake_connect(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("initial connect failure")
        return FakeWebSocket()

    monkeypatch.setitem(sys.modules, "websockets", types.SimpleNamespace(connect=fake_connect))

    cm = ConversationManager("http://127.0.0.1:8100")
    await cm.start()

    await asyncio.sleep(RECONNECT_BACKOFF_S + 0.4)
    assert attempts["count"] >= 2
    assert cm.connected

    await cm.stop()


@pytest.mark.asyncio
async def test_set_ptt_enabled_toggles_mic_capture(monkeypatch):
    cm = ConversationManager("http://127.0.0.1:8100")
    calls: list[tuple[str, bool | None]] = []

    async def fake_start_mic_capture():
        calls.append(("start", None))

    async def fake_stop_mic_capture(send_end_utterance: bool):
        calls.append(("stop", send_end_utterance))

    monkeypatch.setattr(cm, "_start_mic_capture", fake_start_mic_capture)
    monkeypatch.setattr(cm, "_stop_mic_capture", fake_stop_mic_capture)

    await cm.set_ptt_enabled(True)
    await cm.set_ptt_enabled(True)  # no-op on repeated state
    await cm.set_ptt_enabled(False)
    await cm.set_ptt_enabled(False)  # no-op on repeated state

    assert cm.ptt_enabled is False
    assert calls == [("start", None), ("stop", True)]


def test_playback_queue_drops_oldest_when_full():
    cm = ConversationManager("http://127.0.0.1:8100")
    cm._playback_queue = asyncio.Queue(maxsize=2)

    cm._queue_playback_chunk(b"a")
    cm._queue_playback_chunk(b"b")
    cm._queue_playback_chunk(b"c")

    first = cm._playback_queue.get_nowait()
    second = cm._playback_queue.get_nowait()
    assert first == b"b"
    assert second == b"c"


def test_handle_audio_splits_into_pcm_frames():
    cm = ConversationManager("http://127.0.0.1:8100")
    chunks: list[bytes] = []

    def capture(chunk: bytes) -> None:
        chunks.append(chunk)

    cm._queue_playback_chunk = capture  # type: ignore[method-assign]

    pcm = bytes([i % 256 for i in range(CHUNK_BYTES + CHUNK_BYTES // 2 + 1)])
    msg = {"type": "audio", "data": base64.b64encode(pcm).decode("ascii")}
    cm._handle_audio(msg)

    assert len(chunks) == 2
    assert len(chunks[0]) == CHUNK_BYTES
    assert len(chunks[1]) == CHUNK_BYTES // 2
