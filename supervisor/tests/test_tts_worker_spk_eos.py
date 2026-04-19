"""Test that the TTS worker ends a playback stream immediately on an
explicit zero-length-frame EOS marker, without waiting for the idle watchdog.

The EOS marker is sent by ai_worker on the server's WS ``done`` event and is
what lets us set the idle watchdog to 2.0 s without feeling laggy between
turns — fast cases tear down promptly, slow cases still have a safety net.
"""

from __future__ import annotations

import asyncio
import socket
import struct

import pytest

from supervisor.messages.types import TTS_EVENT_FINISHED
from supervisor.workers.tts_worker import TTSWorker


class _StubSpeaker:
    """Pretends to be an aplay subprocess so _end_stream has something to drain."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.stdin = None
        self.killed = False

    async def wait(self) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = 0


async def _setup_worker_with_connected_sockets() -> tuple[
    TTSWorker, socket.socket, list[tuple[str, dict]]
]:
    """Build a TTSWorker with a socketpair already wired to _spk_sock."""
    worker = TTSWorker()
    # Capture sent envelopes instead of writing NDJSON to stdout.
    sent: list[tuple[str, dict]] = []

    def _capture(msg_type: str, payload: dict | None = None, **_kw) -> None:
        sent.append((msg_type, dict(payload or {})))

    worker.send = _capture  # type: ignore[assignment]

    # Build a connected AF_UNIX socketpair; give one end to the worker.
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    a.setblocking(False)
    b.setblocking(False)
    worker._spk_sock = a  # the worker reads from `a`
    worker._running = True

    # Pre-seed playback state as if a stream were already underway.
    worker._aplay_proc = _StubSpeaker()  # type: ignore[assignment]
    worker._speaking = True

    # Stub out _drain_aplay so _end_stream doesn't try to close a real stdin.
    async def _fake_drain() -> None:
        return None

    worker._drain_aplay = _fake_drain  # type: ignore[assignment]

    return worker, b, sent


@pytest.mark.asyncio
async def test_zero_length_frame_ends_stream_without_waiting_for_watchdog() -> None:
    worker, client_sock, sent = await _setup_worker_with_connected_sockets()

    # Pre-populate the ``_spk_read_loop`` local state by priming it with one
    # real PCM frame first so the worker has an active stream. We'll do this
    # by scheduling the read loop, then writing frames from the other socket.
    read_task = asyncio.create_task(worker._spk_read_loop())

    loop = asyncio.get_running_loop()
    # Drive a small PCM chunk so the stream is "open".
    pcm = b"\x00\x01\x02\x03"
    await loop.sock_sendall(client_sock, struct.pack("<H", len(pcm)) + pcm)
    await asyncio.sleep(0.05)

    # Now send the zero-length EOS frame.
    await loop.sock_sendall(client_sock, struct.pack("<H", 0))

    # Give the worker a moment to process, but WELL under the 2.0 s watchdog.
    for _ in range(20):
        if any(t == TTS_EVENT_FINISHED for t, _ in sent):
            break
        await asyncio.sleep(0.02)

    assert any(t == TTS_EVENT_FINISHED for t, _ in sent), (
        f"EOS frame did not trigger TTS_EVENT_FINISHED; got: {[t for t, _ in sent]}"
    )

    # Stream state reset: no longer "speaking" and aplay_proc is cleared.
    assert worker._speaking is False
    assert worker._aplay_proc is None

    # Cleanup.
    worker._running = False
    client_sock.close()
    try:
        worker._spk_sock.close()  # type: ignore[union-attr]
    except Exception:
        pass
    read_task.cancel()
    try:
        await read_task
    except (asyncio.CancelledError, Exception):
        pass
