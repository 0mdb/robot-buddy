"""Tests for ConversationManager audio chunking and mic queue behavior."""

from __future__ import annotations

import base64
import sys
import types
import asyncio

import pytest

from supervisor.devices.conversation_manager import (
    CHUNK_BYTES,
    RECONNECT_BACKOFF_S,
    ConversationManager,
)


class FakeFace:
    def __init__(self) -> None:
        self.talking_calls: list[tuple[bool, int]] = []
        self.audio_chunks: list[bytes] = []

    def send_talking(self, talking: bool, energy: int = 0) -> None:
        self.talking_calls.append((talking, energy))

    def send_audio_data(self, pcm_chunk: bytes) -> None:
        self.audio_chunks.append(pcm_chunk)


def test_handle_audio_splits_to_10ms_chunks():
    face = FakeFace()
    cm = ConversationManager("http://127.0.0.1:8100", face=face)

    pcm = bytes([i % 256 for i in range(CHUNK_BYTES * 3 + 40)])
    msg = {"type": "audio", "data": base64.b64encode(pcm).decode("ascii")}
    cm._handle_audio(msg)

    assert len(face.audio_chunks) == 4
    assert len(face.audio_chunks[0]) == CHUNK_BYTES
    assert len(face.audio_chunks[1]) == CHUNK_BYTES
    assert len(face.audio_chunks[2]) == CHUNK_BYTES
    assert len(face.audio_chunks[3]) == 40
    assert face.talking_calls
    assert face.talking_calls[0][0] is True


def test_submit_mic_audio_chunk_trims_odd_length():
    cm = ConversationManager("http://127.0.0.1:8100")
    cm.submit_mic_audio_chunk(b"\x01\x02\x03")
    queued = cm._mic_queue.get_nowait()
    assert queued == b"\x01\x02"


def test_submit_mic_audio_chunk_drops_oldest_when_full():
    cm = ConversationManager("http://127.0.0.1:8100")
    chunk = b"\x00\x00" * (CHUNK_BYTES // 2)
    for _ in range(300):
        cm.submit_mic_audio_chunk(chunk)
    assert cm._mic_drop_count > 0
    assert cm._mic_queue.qsize() == cm._mic_queue.maxsize


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
