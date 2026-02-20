"""TTS worker — pure audio I/O (speech playback + mic capture).

Absorbs v1 audio_orchestrator.py + lip_sync.py.  Never calls face_client —
reports energy to Core, which sends face commands.

Mode A (direct): Mic PCM → rb-mic socket, TTS PCM ← rb-spk socket.
Mode B (relay):  Mic PCM → NDJSON events, TTS PCM ← NDJSON actions.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import socket
import struct
import time
from typing import Any

from supervisor_v2.messages.envelope import Envelope
from supervisor_v2.messages.types import (
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
    TTS_CMD_CANCEL,
    TTS_CMD_SPEAK,
    TTS_CMD_START_MIC,
    TTS_CMD_STOP_MIC,
    TTS_CMD_PLAY_AUDIO,
    TTS_CONFIG_INIT,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_ENERGY,
    TTS_EVENT_ERROR,
    TTS_EVENT_FINISHED,
    TTS_EVENT_MIC_DROPPED,
    TTS_EVENT_STARTED,
)
from supervisor_v2.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

# Audio constants (Appendix C)
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit signed LE
CHANNELS = 1
CHUNK_BYTES = 320  # 10ms

# Energy emission rate limit
_ENERGY_MIN_INTERVAL_S = 1.0 / 20  # 20 Hz max

# Mic ring buffer size (200ms)
_MIC_RING_FRAMES = int(0.2 * SAMPLE_RATE / (CHUNK_BYTES // SAMPLE_WIDTH))

# Socket connect retry
_SOCKET_RETRY_INTERVAL_S = 0.1
_SOCKET_RETRY_TIMEOUT_S = 30.0


def compute_rms_energy(pcm_chunk: bytes, *, gain: float = 220.0) -> int:
    """Convert PCM chunk to 0-255 energy for lip sync."""
    if len(pcm_chunk) < 2:
        return 0
    n_samples = len(pcm_chunk) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_chunk[:n_samples * 2])
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
        self._mic_socket_path = ""
        self._spk_socket_path = ""
        self._speaker_device = "default"
        self._mic_device = "default"
        self._tts_endpoint = ""

        # State
        self._speaking = False
        self._mic_active = False
        self._cancel_event = asyncio.Event()
        self._lip_sync = LipSyncTracker()
        self._last_energy_t = 0.0
        self._configured = asyncio.Event()

        # Speech queue
        self._speech_queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=5)

        # Socket connections (Mode A)
        self._mic_sock: socket.socket | None = None
        self._spk_sock: socket.socket | None = None

        # Playback process
        self._aplay_proc: asyncio.subprocess.Process | None = None
        self._arecord_proc: asyncio.subprocess.Process | None = None

        # Stats
        self._chunks_played = 0
        self._mic_dropped = 0

    async def on_message(self, envelope: Envelope) -> None:
        t = envelope.type
        p = envelope.payload

        if t == TTS_CONFIG_INIT:
            self._audio_mode = str(p.get("audio_mode", "direct"))
            self._mic_socket_path = str(p.get("mic_socket_path", ""))
            self._spk_socket_path = str(p.get("spk_socket_path", ""))
            self._speaker_device = str(p.get("speaker_device", "default"))
            self._mic_device = str(p.get("mic_device", "default"))
            self._tts_endpoint = str(p.get("tts_endpoint", ""))
            log.info("configured: mode=%s", self._audio_mode)
            self._configured.set()

        elif t == TTS_CMD_SPEAK:
            await self._speech_queue.put(dict(p))

        elif t == TTS_CMD_CANCEL:
            self._cancel_event.set()
            # Drain queue
            while not self._speech_queue.empty():
                try:
                    self._speech_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            await self._kill_aplay()
            if self._speaking:
                self._speaking = False
                self.send(TTS_EVENT_CANCELLED)

        elif t == TTS_CMD_START_MIC:
            if not self._mic_active:
                self._mic_active = True
                asyncio.create_task(self._mic_capture_loop())

        elif t == TTS_CMD_STOP_MIC:
            self._mic_active = False
            await self._kill_arecord()

        elif t == TTS_CMD_PLAY_AUDIO:
            # Mode B: audio relay from Core
            if self._audio_mode == "relay":
                data_b64 = p.get("data_b64", "")
                if data_b64:
                    pcm = base64.b64decode(data_b64)
                    await self._play_pcm_chunk(pcm)

    def health_payload(self) -> dict[str, Any]:
        return {
            "speaking": self._speaking,
            "mic_active": self._mic_active,
            "queue_depth": self._speech_queue.qsize(),
            "audio_mode": self._audio_mode,
        }

    async def run(self) -> None:
        """Main TTS loop — wait for config, connect sockets, process speech."""
        # Wait for config
        try:
            await asyncio.wait_for(self._configured.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.error("no config received within 10s")
            return

        # Connect audio sockets (Mode A)
        if self._audio_mode == "direct":
            asyncio.create_task(self._connect_socket("mic", self._mic_socket_path))
            asyncio.create_task(self._connect_socket("spk", self._spk_socket_path))

        # Speech playback loop
        while self.running:
            try:
                req = await asyncio.wait_for(self._speech_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if req is None:
                continue

            self._cancel_event.clear()
            await self._play_tts(req)

    async def _play_tts(self, req: dict) -> None:
        """Stream TTS audio from server and play via aplay."""
        text = req.get("text", "")
        emotion = req.get("emotion", "neutral")
        ref_seq = req.get("ref_seq", 0)

        if not text or not self._tts_endpoint:
            return

        self._speaking = True
        self._chunks_played = 0
        self._lip_sync.reset()
        self.send(TTS_EVENT_STARTED, {"ref_seq": ref_seq, "text": text})

        try:
            import httpx
        except ImportError:
            self.send(TTS_EVENT_ERROR, {"error": "httpx not installed"})
            self._speaking = False
            return

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "text": text,
                    "emotion": emotion,
                    "stream": True,
                    "robot_id": "",
                    "seq": ref_seq,
                }
                async with client.stream("POST", self._tts_endpoint, json=payload) as resp:
                    if resp.status_code != 200:
                        self.send(TTS_EVENT_ERROR, {"error": f"TTS HTTP {resp.status_code}"})
                        self._speaking = False
                        return

                    # Start aplay subprocess
                    await self._start_aplay()
                    t0 = time.monotonic()

                    async for chunk in resp.aiter_bytes(CHUNK_BYTES):
                        if self._cancel_event.is_set():
                            break

                        await self._play_pcm_chunk(chunk)
                        self._chunks_played += 1

                        # Energy for lip sync (coalesced to 20 Hz)
                        energy = self._lip_sync.update_chunk(chunk)
                        now = time.monotonic()
                        if now - self._last_energy_t >= _ENERGY_MIN_INTERVAL_S:
                            self._last_energy_t = now
                            self.send(TTS_EVENT_ENERGY, {"energy": energy})

                    # Wait for aplay to finish
                    await self._drain_aplay()
                    duration_ms = int((time.monotonic() - t0) * 1000)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.send(TTS_EVENT_ERROR, {"error": str(e)})
            log.exception("TTS playback error")
        finally:
            self._speaking = False
            await self._kill_aplay()
            if not self._cancel_event.is_set():
                self.send(TTS_EVENT_FINISHED, {
                    "ref_seq": ref_seq,
                    "duration_ms": int((time.monotonic() - t0) * 1000) if 't0' in dir() else 0,
                    "chunks_played": self._chunks_played,
                })

    async def _start_aplay(self) -> None:
        """Start aplay subprocess for audio playback."""
        await self._kill_aplay()
        self._aplay_proc = await asyncio.create_subprocess_exec(
            "aplay", "-D", self._speaker_device,
            "-r", str(SAMPLE_RATE), "-f", "S16_LE", "-c", str(CHANNELS),
            "-t", "raw", "-q",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def _play_pcm_chunk(self, pcm: bytes) -> None:
        """Write a PCM chunk to the aplay subprocess."""
        if self._aplay_proc and self._aplay_proc.stdin:
            try:
                self._aplay_proc.stdin.write(pcm)
                await self._aplay_proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def _drain_aplay(self) -> None:
        """Close stdin and wait for aplay to finish."""
        if self._aplay_proc and self._aplay_proc.stdin:
            try:
                self._aplay_proc.stdin.close()
                await self._aplay_proc.wait()
            except Exception:
                pass

    async def _kill_aplay(self) -> None:
        if self._aplay_proc:
            try:
                self._aplay_proc.kill()
                await self._aplay_proc.wait()
            except Exception:
                pass
            self._aplay_proc = None

    # ── Mic capture ──────────────────────────────────────────────

    async def _mic_capture_loop(self) -> None:
        """Capture mic audio via arecord and forward to AI worker."""
        self._arecord_proc = await asyncio.create_subprocess_exec(
            "arecord", "-D", self._mic_device,
            "-r", str(SAMPLE_RATE), "-f", "S16_LE", "-c", str(CHANNELS),
            "-t", "raw", "-q",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            while self._mic_active and self._arecord_proc.stdout:
                data = await self._arecord_proc.stdout.read(CHUNK_BYTES)
                if not data:
                    break

                if self._audio_mode == "direct" and self._mic_sock:
                    try:
                        # Binary framed PCM: [chunk_len:u16-LE][pcm_data]
                        frame = struct.pack("<H", len(data)) + data
                        self._mic_sock.sendall(frame)
                    except (BrokenPipeError, OSError):
                        self._mic_dropped += 1
                        if self._mic_dropped % 100 == 1:
                            self.send(TTS_EVENT_MIC_DROPPED, {"count": self._mic_dropped})
                elif self._audio_mode == "relay":
                    # Mode B: send via NDJSON
                    self.send("tts.event.audio_chunk", {
                        "data_b64": base64.b64encode(data).decode(),
                    })
        except asyncio.CancelledError:
            pass
        finally:
            await self._kill_arecord()

    async def _kill_arecord(self) -> None:
        if self._arecord_proc:
            try:
                self._arecord_proc.kill()
                await self._arecord_proc.wait()
            except Exception:
                pass
            self._arecord_proc = None

    # ── Socket connection (Mode A) ───────────────────────────────

    async def _connect_socket(self, name: str, path: str) -> None:
        """Connect to an audio unix domain socket (client role)."""
        if not path:
            return

        t0 = time.monotonic()
        while self.running and (time.monotonic() - t0) < _SOCKET_RETRY_TIMEOUT_S:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(path)
                sock.setblocking(False)
                if name == "mic":
                    self._mic_sock = sock
                elif name == "spk":
                    self._spk_sock = sock
                self.send(SYSTEM_AUDIO_LINK_UP, {"socket": name})
                log.info("connected to %s socket: %s", name, path)

                # For speaker socket, start reading loop
                if name == "spk":
                    asyncio.create_task(self._spk_read_loop())
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
                await asyncio.sleep(_SOCKET_RETRY_INTERVAL_S)

        log.error("failed to connect %s socket after %.0fs", name, _SOCKET_RETRY_TIMEOUT_S)

    async def _spk_read_loop(self) -> None:
        """Read TTS audio from speaker socket and play via aplay."""
        loop = asyncio.get_running_loop()
        sock = self._spk_sock
        if not sock:
            return

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
                if chunk_len == 0 or chunk_len > 4096:
                    continue

                # Read PCM data
                pcm = b""
                while len(pcm) < chunk_len:
                    data = await loop.sock_recv(sock, chunk_len - len(pcm))
                    if not data:
                        raise ConnectionError("speaker socket closed")
                    pcm += data

                await self._play_pcm_chunk(pcm)

                # Energy
                energy = self._lip_sync.update_chunk(pcm)
                now = time.monotonic()
                if now - self._last_energy_t >= _ENERGY_MIN_INTERVAL_S:
                    self._last_energy_t = now
                    self.send(TTS_EVENT_ENERGY, {"energy": energy})

        except (ConnectionError, OSError) as e:
            self.send(SYSTEM_AUDIO_LINK_DOWN, {"socket": "spk", "reason": str(e)})
            log.warning("speaker socket disconnected: %s", e)
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    worker_main(TTSWorker)
