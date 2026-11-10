"""One always-open playback stream with a two-source mixer.

The reSpeaker Flex (XVF3800) cancels echo against its own USB playback, so
every robot sound has to go through one stream on that card, and a hw device
can only be opened once. ``PlaybackStream`` keeps a single ``aplay`` open and
writes a 20 ms frame on a steady clock, silence when idle, so the device clock
and the echo canceller's reference never stop. Two sources are mixed with
int16 saturation:

- **voice**: speech (local TTS or the conversation stream), one at a time.
- **fx**: short effects such as chimes, mixed over speech.

Producers may queue audio faster than real time (HTTP TTS does). Anything that
has to line up with what the listener hears is therefore done at mix time: the
``voice_fx`` callback sees each voice frame as it is played (lip-sync energy,
mute, ring mod, volume), and ``drain_voice()`` returns once queued speech has
actually played.

``max_volume`` is a hard cap applied to the final mix (docs/audio-hardware.md
§5); it is set at start-up and nothing at runtime can raise it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Protocol

import numpy as np

from supervisor.audio.format import BYTES_PER_MS, SAMPLE_RATE

log = logging.getLogger(__name__)

FRAME_MS = 20
FRAME_BYTES = FRAME_MS * BYTES_PER_MS  # 640
# How far ahead of the device we write. Covers scheduler jitter on the Pi;
# it is also the extra latency on cancel and the drain_voice() margin.
LEAD_S = 0.06
# Behind schedule by more than this (device stalled, writer starved): resync.
_RESYNC_S = 0.2
_REOPEN_S = 1.0
_SILENCE = bytes(FRAME_BYTES)


class PcmSink(Protocol):
    """Where mixed frames go. ``open``/``write`` return False on failure."""

    async def open(self) -> bool: ...

    async def write(self, pcm: bytes) -> bool: ...

    async def close(self) -> None: ...


class AplaySink:
    """A long-lived ``aplay`` reading raw PCM on stdin."""

    def __init__(self, device: str, buffer_us: int = 100_000) -> None:
        self.device = device
        self._buffer_us = buffer_us
        self._proc: asyncio.subprocess.Process | None = None

    async def open(self) -> bool:
        await self.close()
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "aplay",
                "-D",
                self.device,
                "-r",
                str(SAMPLE_RATE),
                "-f",
                "S16_LE",
                "-c",
                "1",
                "-t",
                "raw",
                "-q",
                "-B",
                str(self._buffer_us),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as e:
            log.warning("cannot start aplay: %s", e)
            self._proc = None
            return False
        # A missing or busy device makes aplay exit at once.
        await asyncio.sleep(0.15)
        if self._proc.returncode is not None:
            log.warning("aplay exited at start (device %s unavailable?)", self.device)
            self._proc = None
            return False
        return True

    async def write(self, pcm: bytes) -> bool:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            return False
        try:
            proc.stdin.write(pcm)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False
        return True

    async def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
            await proc.wait()
        except (ProcessLookupError, OSError):
            pass


def mix_frames(a: bytes, b: bytes) -> bytes:
    """Sum two equal-length S16_LE frames with saturation."""
    x = np.frombuffer(a, dtype=np.int16).astype(np.int32)
    x += np.frombuffer(b, dtype=np.int16)
    np.clip(x, -32768, 32767, out=x)
    return x.astype(np.int16).tobytes()


def scale_frame(pcm: bytes, gain: float) -> bytes:
    """Scale S16_LE samples by ``gain`` with saturation."""
    if gain >= 0.999:
        return pcm
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    x *= max(0.0, gain)
    np.clip(x, -32768.0, 32767.0, out=x)
    return x.astype(np.int16).tobytes()


class PlaybackStream:
    """Clocked mixer in front of a ``PcmSink``.

    ``voice_fx(frame) -> frame`` runs on each voice frame as it is played.
    ``fx_gain()`` gives the current effects gain (the user volume).
    ``on_link(up, reason)`` reports when the sink opens or fails.
    """

    def __init__(
        self,
        sink: PcmSink,
        *,
        max_volume: float = 1.0,
        voice_fx: Callable[[bytes], bytes] | None = None,
        fx_gain: Callable[[], float] | None = None,
        on_link: Callable[[bool, str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sink = sink
        self.max_volume = max(0.0, min(1.0, max_volume))
        self._voice_fx = voice_fx
        self._fx_gain = fx_gain
        self._on_link = on_link
        self._clock = clock
        self._voice = bytearray()
        self._fx = bytearray()
        self._voice_idle = asyncio.Event()
        self._voice_idle.set()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.link_up = False
        self.frames_written = 0
        self.underruns = 0

    # ── producers ─────────────────────────────────────────────────

    def queue_voice(self, pcm: bytes) -> None:
        if pcm:
            self._voice += pcm
            self._voice_idle.clear()

    def queue_fx(self, pcm: bytes) -> None:
        if pcm:
            self._fx += pcm

    def flush_voice(self) -> None:
        """Drop queued speech now (cancel); effects keep playing."""
        self._voice.clear()
        self._voice_idle.set()

    @property
    def voice_pending_ms(self) -> int:
        return len(self._voice) // BYTES_PER_MS

    @property
    def voice_active(self) -> bool:
        return not self._voice_idle.is_set()

    async def drain_voice(self) -> None:
        """Wait until queued speech has been written, plus the device lead."""
        if self._voice_idle.is_set():
            return
        await self._voice_idle.wait()
        await asyncio.sleep(LEAD_S)

    # ── lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.sink.close()
        self._set_link(False, "stopped")

    # ── mixing ────────────────────────────────────────────────────

    def next_frame(self) -> bytes:
        """Build the next 20 ms frame from both sources (exposed for tests)."""
        voice = None
        if self._voice:
            voice = bytes(self._voice[:FRAME_BYTES])
            del self._voice[:FRAME_BYTES]
            if len(voice) < FRAME_BYTES:
                voice += bytes(FRAME_BYTES - len(voice))
            if self._voice_fx is not None:
                voice = self._voice_fx(voice)
            if not self._voice:
                self._voice_idle.set()
        fx = None
        if self._fx:
            fx = bytes(self._fx[:FRAME_BYTES])
            del self._fx[:FRAME_BYTES]
            if len(fx) < FRAME_BYTES:
                fx += bytes(FRAME_BYTES - len(fx))
            if self._fx_gain is not None:
                fx = scale_frame(fx, self._fx_gain())
        if voice is None and fx is None:
            return _SILENCE
        if voice is None:
            out = fx
        elif fx is None:
            out = voice
        else:
            out = mix_frames(voice, fx)
        return scale_frame(out, self.max_volume)  # type: ignore[arg-type]

    def _set_link(self, up: bool, reason: str) -> None:
        if up != self.link_up:
            self.link_up = up
            if self._on_link is not None:
                self._on_link(up, reason)

    async def _run(self) -> None:
        period = FRAME_MS / 1000.0
        while self._running:
            if not await self.sink.open():
                self._set_link(False, "aplay_failed")
                await asyncio.sleep(_REOPEN_S)
                continue
            self._set_link(True, "")
            t_next = self._clock()
            while self._running:
                now = self._clock()
                if now - t_next > _RESYNC_S:
                    self.underruns += 1
                    t_next = now
                wait = t_next - LEAD_S - now
                if wait > 0:
                    await asyncio.sleep(wait)
                if not await self.sink.write(self.next_frame()):
                    break
                self.frames_written += 1
                t_next += period
            await self.sink.close()
            if self._running:
                self._set_link(False, "aplay_exit")
                await asyncio.sleep(_REOPEN_S)
