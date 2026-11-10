"""The TTS worker ends a conversation stream on the explicit zero-length EOS
frame, without waiting for the idle watchdog, and only after the queued audio
has been played through the mixer.

The EOS marker is sent by ai_worker on the server's WS ``done`` event and is
what lets the idle watchdog sit at 2.0 s without feeling laggy between turns.
"""

from __future__ import annotations

import asyncio
import socket
import struct

import pytest

from supervisor.messages.types import (
    SYSTEM_AUDIO_LINK_UP,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_FINISHED,
    TTS_EVENT_STARTED,
)
from supervisor.workers.tts_worker import TTSWorker


class FakeSink:
    def __init__(self, device: str = "fake") -> None:
        self.device = device
        self.frames: list[bytes] = []

    async def open(self) -> bool:
        return True

    async def write(self, pcm: bytes) -> bool:
        self.frames.append(pcm)
        return True

    async def close(self) -> None:
        pass


async def _setup() -> tuple[TTSWorker, socket.socket, list[tuple[str, dict]]]:
    worker = TTSWorker()
    sent: list[tuple[str, dict]] = []

    def _capture(msg_type: str, payload: dict | None = None, **_kw) -> None:
        sent.append((msg_type, dict(payload or {})))

    worker.send = _capture  # type: ignore[assignment]
    worker._sink_factory = FakeSink
    worker._running = True
    worker._start_playback()

    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    a.setblocking(False)
    b.setblocking(False)
    worker._spk_sock = a
    worker._spk_sock_up = True
    return worker, b, sent


async def _cleanup(
    worker: TTSWorker, client: socket.socket, task: asyncio.Task
) -> None:
    worker._running = False
    client.close()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    assert worker._playback is not None
    await worker._playback.stop()


async def _wait_for(sent: list[tuple[str, dict]], t: str, timeout: float = 1.0) -> bool:
    for _ in range(int(timeout / 0.02)):
        if any(x == t for x, _ in sent):
            return True
        await asyncio.sleep(0.02)
    return False


@pytest.mark.asyncio
async def test_zero_length_frame_ends_stream_without_waiting_for_watchdog() -> None:
    worker, client, sent = await _setup()
    task = asyncio.create_task(worker._spk_read_loop())
    loop = asyncio.get_running_loop()

    pcm = bytes(640) * 5  # 100 ms
    await loop.sock_sendall(client, struct.pack("<H", len(pcm)) + pcm)
    assert await _wait_for(sent, TTS_EVENT_STARTED)
    await loop.sock_sendall(client, struct.pack("<H", 0))

    # Well under the 2.0 s watchdog: 100 ms of audio + the mixer lead.
    assert await _wait_for(sent, TTS_EVENT_FINISHED, timeout=1.0), [t for t, _ in sent]
    assert worker._speaking is False
    assert worker._playback is not None and not worker._playback.voice_active
    await _cleanup(worker, client, task)


@pytest.mark.asyncio
async def test_link_up_needs_socket_and_playback() -> None:
    worker, client, sent = await _setup()
    assert await _wait_for(sent, SYSTEM_AUDIO_LINK_UP)  # playback opened, socket up
    task = asyncio.create_task(worker._spk_read_loop())
    await _cleanup(worker, client, task)


@pytest.mark.asyncio
async def test_cancel_discards_rest_of_stream() -> None:
    worker, client, sent = await _setup()
    task = asyncio.create_task(worker._spk_read_loop())
    loop = asyncio.get_running_loop()

    frame = struct.pack("<H", 640) + bytes(640)
    await loop.sock_sendall(client, frame * 25)  # 500 ms queued
    assert await _wait_for(sent, TTS_EVENT_STARTED)
    worker._cancel()
    assert any(t == TTS_EVENT_CANCELLED for t, _ in sent)
    assert worker._playback is not None and worker._playback.voice_pending_ms == 0

    # More of the same stream arrives after the cancel: dropped, no new STARTED.
    await loop.sock_sendall(client, struct.pack("<H", 640) + bytes(640))
    await asyncio.sleep(0.1)
    assert sum(1 for t, _ in sent if t == TTS_EVENT_STARTED) == 1
    assert worker._playback.voice_pending_ms == 0

    # EOS closes the discarded stream; the next stream plays again.
    await loop.sock_sendall(client, struct.pack("<H", 0))
    await asyncio.sleep(0.05)
    await loop.sock_sendall(client, struct.pack("<H", 640) + bytes(640))
    await asyncio.sleep(0.05)
    assert sum(1 for t, _ in sent if t == TTS_EVENT_STARTED) == 2
    assert not any(t == TTS_EVENT_FINISHED for t, _ in sent)
    await _cleanup(worker, client, task)
