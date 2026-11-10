"""TTS worker — speech playback and audio output.

Absorbs v1 audio_orchestrator.py + lip_sync.py.  Never calls face_client —
reports energy to Core, which sends face commands.

All sound goes through one always-open ``PlaybackStream`` (audio/playback.py):
speech on the voice source, chimes on the fx source, mixed. With the reSpeaker
Flex that stream is the echo canceller's reference, so nothing else may open
the speaker. Lip-sync energy and TTS_EVENT_FINISHED follow the mixer clock,
not the arrival of audio.

Mic capture has moved to the ear worker (ear_worker.py).
Mode A (direct): TTS PCM ← rb-spk socket.
Mode B (relay):  TTS PCM ← NDJSON actions.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import socket
import struct
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from supervisor.audio.format import (
    CHUNK_BYTES,
    MAX_FRAME_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    SOCKET_RETRY_INTERVAL_S,
    SOCKET_RETRY_TIMEOUT_S,
)
from supervisor.audio.playback import AplaySink, PcmSink, PlaybackStream
from supervisor.devices.alsa_device import resolve_alsa_device
from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
    TTS_CMD_CANCEL,
    TTS_CMD_PLAY_AUDIO,
    TTS_CMD_PLAY_CHIME,
    TTS_CMD_SET_MUTE,
    TTS_CMD_SET_RING_MOD,
    TTS_CMD_SET_VOLUME,
    TTS_CMD_SPEAK,
    TTS_CONFIG_INIT,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_ENERGY,
    TTS_EVENT_ERROR,
    TTS_EVENT_FINISHED,
    TTS_EVENT_STARTED,
)
from supervisor.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

__all__ = ["SAMPLE_RATE", "TTSWorker", "LipSyncTracker", "compute_rms_energy"]

# Energy emission rate limit
_ENERGY_MIN_INTERVAL_S = 1.0 / 20  # 20 Hz max

# Spk socket stream idle detection — gap > this ends the current playback stream.
# Conversation audio arrives as a burst from the server; primarily terminated
# by an explicit zero-length frame sent by ai_worker on WS `done`, with the
# idle watchdog as a safety net for WS drops or crashes. 2 s gives the
# streaming path headroom across sentence boundaries (~200–500 ms of TTS
# first-chunk latency plus LLM stall jitter).
_SPK_IDLE_END_S = 2.0

# Chime assets directory
_CHIME_DIR = Path(__file__).parent.parent / "assets" / "chimes"


def compute_rms_energy(pcm_chunk: bytes, *, gain: float = 220.0) -> int:
    """Convert PCM chunk to 0-255 energy for lip sync."""
    if len(pcm_chunk) < 2:
        return 0
    n_samples = len(pcm_chunk) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_chunk[: n_samples * 2])
    rms = math.sqrt(sum(s * s for s in samples) / n_samples) if n_samples else 0
    return min(255, int(rms / 32768.0 * gain))


class LipSyncTracker:
    """Asymmetric exponential smoothing for lip sync energy."""

    __slots__ = ("_energy", "_attack", "_release")

    def __init__(self, attack: float = 0.55, release: float = 0.25) -> None:
        self._energy = 0.0
        self._attack = attack
        self._release = release

    def reset(self) -> None:
        self._energy = 0.0

    def update_chunk(self, pcm_chunk: bytes) -> int:
        raw = compute_rms_energy(pcm_chunk)
        alpha = self._attack if raw > self._energy else self._release
        self._energy = alpha * raw + (1 - alpha) * self._energy
        return int(self._energy)


class TTSWorker(BaseWorker):
    domain = "tts"

    def __init__(self) -> None:
        super().__init__()
        # Config (from tts.config.init)
        self._audio_mode = "direct"
        self._spk_socket_path = ""
        self._speaker_device = "default"
        self._tts_endpoint = ""

        # Volume / mute. _max_volume is the hard cap (tts.config.init only).
        self._volume: float = 0.8  # 80% default; overridden by TTS_CMD_SET_VOLUME
        self._max_volume: float = 1.0
        self._muted: bool = False
        self._mute_chimes: bool = False

        # Ring modulator (Dalek-ish robot voice). hz=0 disables the effect.
        # Phase is stored as normalised cycles in [0, 1) for precision across
        # long streams and is carried across chunks for sample-accurate continuity.
        self._ring_mod_hz: float = 0.0
        self._ring_mod_mix: float = 1.0
        self._ring_mod_phase: float = 0.0

        # State
        self._speaking = False
        self._cancel_event = asyncio.Event()
        self._lip_sync = LipSyncTracker()
        self._last_energy_t = 0.0
        self._configured = asyncio.Event()

        # Speech queue
        self._speech_queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=5)

        # Socket connection (Mode A — speaker only)
        self._spk_sock: socket.socket | None = None
        self._spk_sock_up = False
        self._spk_link_sent: bool | None = None
        # After a cancel, drop the rest of the conversation stream until its
        # end-of-stream marker (or the idle gap) so it does not restart.
        self._spk_discard = False
        self._spk_stream_open = False

        # Playback: one stream for everything (built at config time)
        self._playback: PlaybackStream | None = None
        self._sink_factory: Any = AplaySink  # tests swap in a fake sink
        self._chimes: dict[str, bytes] = {}

        # Persistent HTTP client — reused across utterances to avoid TCP setup
        self._http_client: Any = None  # httpx.AsyncClient once created

        # Stats
        self._chunks_played = 0

    async def on_message(self, envelope: Envelope) -> None:
        t = envelope.type
        p = envelope.payload

        if t == TTS_CONFIG_INIT:
            self._audio_mode = str(p.get("audio_mode", "direct"))
            self._spk_socket_path = str(p.get("spk_socket_path", ""))
            spec = str(p.get("speaker_device", "default"))
            resolved = resolve_alsa_device(spec)
            if resolved is None:
                # Echo cancellation needs playback through the XVF3800 card
                # (its USB playback is the AEC reference): say so loudly.
                log.warning("no ALSA card matches %r, using 'default'", spec)
                resolved = "default"
            self._speaker_device = resolved
            self._tts_endpoint = str(p.get("tts_endpoint", ""))
            if "max_volume" in p:
                self._max_volume = max(0.0, min(1.0, int(p["max_volume"]) / 100.0))
            if "volume" in p:
                self._volume = max(0.0, min(1.0, int(p["volume"]) / 100.0))
            if "ring_mod_hz" in p:
                self._ring_mod_hz = max(0.0, float(p.get("ring_mod_hz", 0.0)))
            if "ring_mod_mix" in p:
                self._ring_mod_mix = max(
                    0.0, min(1.0, float(p.get("ring_mod_mix", 1.0)))
                )
            log.info(
                "configured: mode=%s device=%s max_volume=%.0f%% ring_mod=%.1fHz mix=%.2f",
                self._audio_mode,
                self._speaker_device,
                self._max_volume * 100,
                self._ring_mod_hz,
                self._ring_mod_mix,
            )
            self._configured.set()

        elif t == TTS_CMD_SPEAK:
            await self._speech_queue.put(dict(p))

        elif t == TTS_CMD_CANCEL:
            self._cancel()

        elif t == TTS_CMD_PLAY_CHIME:
            self._play_chime(str(p.get("chime", "listening")))

        elif t == TTS_CMD_SET_VOLUME:
            vol_int = int(p.get("volume", 80))
            self._volume = max(0.0, min(1.0, vol_int / 100.0))
            log.info("volume set to %d%% (scale=%.3f)", vol_int, self._volume)

        elif t == TTS_CMD_SET_MUTE:
            self._muted = bool(p.get("muted", False))
            self._mute_chimes = bool(p.get("mute_chimes", False))
            log.info("mute=%s mute_chimes=%s", self._muted, self._mute_chimes)

        elif t == TTS_CMD_SET_RING_MOD:
            self._ring_mod_hz = max(0.0, float(p.get("hz", 0.0)))
            self._ring_mod_mix = max(0.0, min(1.0, float(p.get("mix", 1.0))))
            # Reset phase so toggling on/off starts from a clean sin(0)=0.
            self._ring_mod_phase = 0.0
            log.info(
                "ring_mod: hz=%.1f mix=%.2f", self._ring_mod_hz, self._ring_mod_mix
            )

        elif t == TTS_CMD_PLAY_AUDIO:
            # Mode B: audio relay from Core
            if self._audio_mode == "relay":
                data_b64 = p.get("data_b64", "")
                if data_b64 and self._playback is not None:
                    self._playback.queue_voice(base64.b64decode(data_b64))

    def health_payload(self) -> dict[str, Any]:
        pb = self._playback
        return {
            "speaking": self._speaking,
            "queue_depth": self._speech_queue.qsize(),
            "audio_mode": self._audio_mode,
            "speaker_device": self._speaker_device,
            "max_volume": round(self._max_volume * 100),
            "volume": round(self._volume * 100),
            "playback": {
                "link_up": pb.link_up if pb else False,
                "voice_pending_ms": pb.voice_pending_ms if pb else 0,
                "frames": pb.frames_written if pb else 0,
                "underruns": pb.underruns if pb else 0,
            },
        }

    # ── playback stream ───────────────────────────────────────────

    def _start_playback(self) -> PlaybackStream:
        sink: PcmSink = self._sink_factory(self._speaker_device)
        self._playback = PlaybackStream(
            sink,
            max_volume=self._max_volume,
            voice_fx=self._voice_frame,
            fx_gain=lambda: 0.0 if self._mute_chimes else self._volume,
            on_link=self._on_playback_link,
        )
        self._playback.start()
        return self._playback

    def _voice_frame(self, frame: bytes) -> bytes:
        """Runs as each voice frame is played: lip sync, mute, ring mod, volume."""
        energy = 0
        for i in range(0, len(frame), CHUNK_BYTES):
            energy = self._lip_sync.update_chunk(frame[i : i + CHUNK_BYTES])
        now = time.monotonic()
        if now - self._last_energy_t >= _ENERGY_MIN_INTERVAL_S:
            self._last_energy_t = now
            self.send(TTS_EVENT_ENERGY, {"energy": energy})
        if self._muted:
            return bytes(len(frame))
        if self._ring_mod_hz > 0.0 and self._ring_mod_mix > 0.0:
            frame = self._apply_ring_mod(frame)
        if self._volume < 0.999:
            frame = self._scale_pcm(frame)
        return frame

    def _on_playback_link(self, up: bool, reason: str) -> None:
        if not up:
            log.warning("playback down (%s) on %s", reason, self._speaker_device)
        else:
            log.info("playback up on %s", self._speaker_device)
        self._update_spk_link(reason)

    def _update_spk_link(self, reason: str = "") -> None:
        """spk link = speaker socket connected AND the playback device open."""
        up = self._spk_sock_up and bool(self._playback and self._playback.link_up)
        if up == self._spk_link_sent:
            return
        self._spk_link_sent = up
        if up:
            self.send(SYSTEM_AUDIO_LINK_UP, {"socket": "spk"})
        else:
            self.send(
                SYSTEM_AUDIO_LINK_DOWN, {"socket": "spk", "reason": reason or "down"}
            )

    def _cancel(self) -> None:
        self._cancel_event.set()
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._playback is not None:
            self._playback.flush_voice()
        if self._speaking:
            self._speaking = False
            if self._spk_stream_open:
                self._spk_discard = True
            self.send(TTS_EVENT_CANCELLED)

    async def run(self) -> None:
        """Main TTS loop — wait for config, connect sockets, process speech."""
        # Wait for config
        try:
            await asyncio.wait_for(self._configured.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.error("no config received within 10s")
            return

        self._start_playback()

        # Connect speaker socket (Mode A)
        if self._audio_mode == "direct":
            asyncio.create_task(self._connect_spk_socket())

        # Speech playback loop
        try:
            while self.running:
                try:
                    req = await asyncio.wait_for(self._speech_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if req is None:
                    continue

                self._cancel_event.clear()
                await self._play_tts(req)
        finally:
            if self._http_client is not None:
                await self._http_client.aclose()
                self._http_client = None
            if self._playback is not None:
                await self._playback.stop()

    async def _play_tts(self, req: dict) -> None:
        """Stream TTS audio from the server into the voice source."""
        text = req.get("text", "")
        emotion = req.get("emotion", "neutral")
        ref_seq = req.get("ref_seq", 0)

        if not text or not self._tts_endpoint:
            return

        self._speaking = True
        self._chunks_played = 0
        self._lip_sync.reset()
        t0 = time.monotonic()
        self.send(TTS_EVENT_STARTED, {"ref_seq": ref_seq, "text": text})

        try:
            import httpx
        except ImportError:
            self.send(TTS_EVENT_ERROR, {"error": "httpx not installed"})
            self._speaking = False
            return

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        try:
            payload = {
                "text": text,
                "emotion": emotion,
                "stream": True,
                "robot_id": "",
                "seq": ref_seq,
            }
            async with self._http_client.stream(
                "POST", self._tts_endpoint, json=payload
            ) as resp:
                if resp.status_code != 200:
                    self.send(
                        TTS_EVENT_ERROR, {"error": f"TTS HTTP {resp.status_code}"}
                    )
                    self._speaking = False
                    return

                async for chunk in resp.aiter_bytes(CHUNK_BYTES):
                    if self._cancel_event.is_set():
                        break
                    if self._playback is not None:
                        self._playback.queue_voice(chunk)
                    self._chunks_played += 1

                # Return once the speech has actually been played.
                if self._playback is not None and not self._cancel_event.is_set():
                    await self._playback.drain_voice()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.send(TTS_EVENT_ERROR, {"error": str(e)})
            log.warning("TTS playback error: %s", e)
        finally:
            self._speaking = False
            if not self._cancel_event.is_set():
                self.send(
                    TTS_EVENT_FINISHED,
                    {
                        "ref_seq": ref_seq,
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                        "chunks_played": self._chunks_played,
                    },
                )

    # ── Chime playback ────────────────────────────────────────────

    def _load_chime(self, name: str) -> bytes | None:
        """Read a chime WAV once; it must be mono S16_LE at SAMPLE_RATE."""
        if name in self._chimes:
            return self._chimes[name]
        path = _CHIME_DIR / f"{name}.wav"
        if not path.exists():
            log.warning("chime not found: %s", path)
            return None
        try:
            with wave.open(str(path)) as w:
                fmt = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                if fmt != (1, SAMPLE_WIDTH, SAMPLE_RATE):
                    log.warning(
                        "chime %s is %s, need mono S16 %d Hz", path, fmt, SAMPLE_RATE
                    )
                    return None
                pcm = w.readframes(w.getnframes())
        except (OSError, wave.Error) as e:
            log.warning("cannot read chime %s: %s", path, e)
            return None
        self._chimes[name] = pcm
        return pcm

    def _play_chime(self, name: str) -> None:
        """Mix a chime over whatever is playing."""
        if self._mute_chimes or self._playback is None:
            return
        pcm = self._load_chime(name)
        if pcm:
            self._playback.queue_fx(pcm)

    def _scale_pcm(self, pcm: bytes) -> bytes:
        """Scale S16_LE PCM samples by self._volume (0.0–1.0)."""
        if len(pcm) < 2:
            return pcm
        # Load as int16, convert to float32 for scaling
        arr = np.frombuffer(pcm, dtype=np.int16).copy().astype(np.float32)
        # Apply volume scale and clip to int16 range
        arr *= self._volume
        arr = np.clip(arr, -32768, 32767)
        # Convert back to int16 and ensure C-contiguous for tobytes()
        return arr.astype(np.int16, copy=False).tobytes()

    def _apply_ring_mod(self, pcm: bytes) -> bytes:
        """Multiply PCM by a phase-continuous sine carrier (ring modulator).

        mix=0 → dry (unchanged), mix=1 → pure ring mod (audio * sin).
        Phase is tracked in normalised cycles so it stays accurate across
        thousands of chunks without drifting.
        """
        if self._ring_mod_hz <= 0.0 or self._ring_mod_mix <= 0.0 or len(pcm) < 2:
            return pcm

        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        n = arr.shape[0]
        cycles_per_sample = self._ring_mod_hz / SAMPLE_RATE
        # Phase (in cycles) for each sample in this chunk.
        phase = self._ring_mod_phase + cycles_per_sample * np.arange(
            n, dtype=np.float32
        )
        sine = np.sin(2.0 * np.pi * phase)

        mix = self._ring_mod_mix
        if mix >= 1.0:
            arr *= sine
        else:
            arr *= (1.0 - mix) + mix * sine

        # Advance phase for the next chunk and wrap to keep it in [0, 1).
        self._ring_mod_phase = float(
            (self._ring_mod_phase + cycles_per_sample * n) % 1.0
        )

        np.clip(arr, -32768.0, 32767.0, out=arr)
        return arr.astype(np.int16, copy=False).tobytes()

    # ── Speaker socket (Mode A) ───────────────────────────────────

    async def _connect_spk_socket(self) -> None:
        """Connect to the rb-spk Unix domain socket (retry loop)."""
        path = self._spk_socket_path
        if not path:
            return

        t0 = time.monotonic()
        while self.running and (time.monotonic() - t0) < SOCKET_RETRY_TIMEOUT_S:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(path)
                sock.setblocking(False)
                self._spk_sock = sock
                log.info("connected to spk socket: %s", path)
                self._spk_sock_up = True
                self._update_spk_link()
                asyncio.create_task(self._spk_read_loop())
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                await asyncio.sleep(SOCKET_RETRY_INTERVAL_S)

        log.error("failed to connect spk socket after %.0fs", SOCKET_RETRY_TIMEOUT_S)

    async def _spk_read_loop(self) -> None:
        """Read conversation audio from the speaker socket into the voice source.

        Audio arrives from the AI worker (forwarded from server /converse),
        often faster than real time. End-of-stream is an explicit zero-length
        frame (``chunk_len == 0``) sent by ai_worker on the server's WS
        ``done``; the idle watchdog at ``_SPK_IDLE_END_S`` is a safety net for
        crashes or WS drops. TTS_EVENT_STARTED/FINISHED bracket the stream;
        FINISHED waits until the queued audio has actually been played.
        """
        loop = asyncio.get_running_loop()
        sock = self._spk_sock
        if not sock:
            return

        stream_t0 = 0.0
        stream_chunks = 0
        idle_task: asyncio.Task[None] | None = None

        async def _end_stream() -> None:
            nonlocal stream_chunks
            self._spk_discard = False
            if not self._spk_stream_open:
                return
            self._spk_stream_open = False
            chunks_played = stream_chunks
            stream_chunks = 0
            if self._playback is not None:
                await self._playback.drain_voice()
            if not self._speaking:
                return  # cancelled while draining; CANCELLED already sent
            self._speaking = False
            self.send(
                TTS_EVENT_FINISHED,
                {
                    "ref_seq": 0,
                    "duration_ms": int((time.monotonic() - stream_t0) * 1000),
                    "chunks_played": chunks_played,
                },
            )

        async def _idle_watchdog() -> None:
            try:
                await asyncio.sleep(_SPK_IDLE_END_S)
                await _end_stream()
            except asyncio.CancelledError:
                pass

        try:
            while self.running and sock:
                # Read frame header: u16-LE chunk_len
                header = b""
                while len(header) < 2:
                    data = await loop.sock_recv(sock, 2 - len(header))
                    if not data:
                        raise ConnectionError("speaker socket closed")
                    header += data

                chunk_len = struct.unpack("<H", header)[0]
                if chunk_len == 0:
                    # Explicit end-of-stream marker from ai_worker.
                    if idle_task and not idle_task.done():
                        idle_task.cancel()
                    await _end_stream()
                    continue

                # Read PCM data (always consume it to keep the framing)
                pcm = b""
                while len(pcm) < chunk_len:
                    data = await loop.sock_recv(sock, chunk_len - len(pcm))
                    if not data:
                        raise ConnectionError("speaker socket closed")
                    pcm += data
                if chunk_len > MAX_FRAME_BYTES:
                    continue

                # A new chunk resets the idle watchdog.
                if idle_task and not idle_task.done():
                    idle_task.cancel()
                idle_task = asyncio.create_task(_idle_watchdog())

                if self._spk_discard:
                    continue  # rest of a cancelled stream

                if not self._spk_stream_open:
                    self._spk_stream_open = True
                    stream_t0 = time.monotonic()
                    stream_chunks = 0
                    self._speaking = True
                    self._lip_sync.reset()
                    self.send(TTS_EVENT_STARTED, {"ref_seq": 0, "text": ""})

                if self._playback is not None:
                    self._playback.queue_voice(pcm)
                stream_chunks += 1

        except (ConnectionError, OSError) as e:
            if idle_task and not idle_task.done():
                idle_task.cancel()
            await _end_stream()
            self._spk_sock_up = False
            self._update_spk_link(str(e))
            log.warning("speaker socket disconnected: %s", e)
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    worker_main(TTSWorker)
