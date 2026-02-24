"""TTS worker — speech playback and audio output.

Absorbs v1 audio_orchestrator.py + lip_sync.py.  Never calls face_client —
reports energy to Core, which sends face commands.

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
from pathlib import Path
from typing import Any

from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
    TTS_CMD_CANCEL,
    TTS_CMD_PLAY_AUDIO,
    TTS_CMD_PLAY_CHIME,
    TTS_CMD_SET_MUTE,
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

# Audio constants (Appendix C)
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit signed LE
CHANNELS = 1
CHUNK_BYTES = 320  # 10ms

# Energy emission rate limit
_ENERGY_MIN_INTERVAL_S = 1.0 / 20  # 20 Hz max

# Socket connect retry
_SOCKET_RETRY_INTERVAL_S = 0.1
_SOCKET_RETRY_TIMEOUT_S = 30.0

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

        # Volume / mute
        self._volume: float = 0.8  # 80% default; overridden by TTS_CMD_SET_VOLUME
        self._muted: bool = False
        self._mute_chimes: bool = False

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

        # Playback process
        self._aplay_proc: asyncio.subprocess.Process | None = None

        # Stats
        self._chunks_played = 0

    async def on_message(self, envelope: Envelope) -> None:
        t = envelope.type
        p = envelope.payload

        if t == TTS_CONFIG_INIT:
            self._audio_mode = str(p.get("audio_mode", "direct"))
            self._spk_socket_path = str(p.get("spk_socket_path", ""))
            self._speaker_device = str(p.get("speaker_device", "default"))
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

        elif t == TTS_CMD_PLAY_CHIME:
            chime_name = str(p.get("chime", "listening"))
            asyncio.create_task(self._play_chime(chime_name))

        elif t == TTS_CMD_SET_VOLUME:
            vol_int = int(p.get("volume", 80))
            self._volume = max(0.0, min(1.0, vol_int / 100.0))
            log.info("volume set to %d%% (scale=%.3f)", vol_int, self._volume)

        elif t == TTS_CMD_SET_MUTE:
            self._muted = bool(p.get("muted", False))
            self._mute_chimes = bool(p.get("mute_chimes", False))
            log.info("mute=%s mute_chimes=%s", self._muted, self._mute_chimes)

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

        # Connect speaker socket (Mode A)
        if self._audio_mode == "direct":
            asyncio.create_task(self._connect_spk_socket())

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
                async with client.stream(
                    "POST", self._tts_endpoint, json=payload
                ) as resp:
                    if resp.status_code != 200:
                        self.send(
                            TTS_EVENT_ERROR, {"error": f"TTS HTTP {resp.status_code}"}
                        )
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

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.send(TTS_EVENT_ERROR, {"error": str(e)})
            log.warning("TTS playback error: %s", e)
        finally:
            self._speaking = False
            await self._kill_aplay()
            if not self._cancel_event.is_set():
                self.send(
                    TTS_EVENT_FINISHED,
                    {
                        "ref_seq": ref_seq,
                        "duration_ms": int((time.monotonic() - t0) * 1000)
                        if "t0" in dir()
                        else 0,
                        "chunks_played": self._chunks_played,
                    },
                )

    # ── Chime playback ────────────────────────────────────────────

    async def _play_chime(self, name: str) -> None:
        """Play a short chime WAV file via aplay."""
        if self._mute_chimes:
            return
        chime_path = _CHIME_DIR / f"{name}.wav"
        if not chime_path.exists():
            log.warning("chime not found: %s", chime_path)
            return

        try:
            proc = await asyncio.create_subprocess_exec(
                "aplay",
                "-D",
                self._speaker_device,
                "-q",
                str(chime_path),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:
            log.exception("chime playback error")

    # ── aplay lifecycle ───────────────────────────────────────────

    async def _start_aplay(self) -> None:
        """Start aplay subprocess for audio playback."""
        await self._kill_aplay()
        self._aplay_proc = await asyncio.create_subprocess_exec(
            "aplay",
            "-D",
            self._speaker_device,
            "-r",
            str(SAMPLE_RATE),
            "-f",
            "S16_LE",
            "-c",
            str(CHANNELS),
            "-t",
            "raw",
            "-q",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    def _scale_pcm(self, pcm: bytes) -> bytes:
        """Scale S16_LE PCM samples by self._volume (0.0–1.0)."""
        n = len(pcm) // 2
        if n == 0:
            return pcm
        samples = struct.unpack(f"<{n}h", pcm[: n * 2])
        scaled = struct.pack(
            f"<{n}h",
            *(max(-32768, min(32767, int(s * self._volume))) for s in samples),
        )
        return scaled

    async def _play_pcm_chunk(self, pcm: bytes) -> None:
        """Write a PCM chunk to the aplay subprocess (applies volume + mute)."""
        if self._muted:
            return
        if self._volume < 0.999:
            pcm = self._scale_pcm(pcm)
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

    # ── Speaker socket (Mode A) ───────────────────────────────────

    async def _connect_spk_socket(self) -> None:
        """Connect to the rb-spk Unix domain socket (retry loop)."""
        path = self._spk_socket_path
        if not path:
            return

        t0 = time.monotonic()
        while self.running and (time.monotonic() - t0) < _SOCKET_RETRY_TIMEOUT_S:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(path)
                sock.setblocking(False)
                self._spk_sock = sock
                self.send(SYSTEM_AUDIO_LINK_UP, {"socket": "spk"})
                log.info("connected to spk socket: %s", path)
                asyncio.create_task(self._spk_read_loop())
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                await asyncio.sleep(_SOCKET_RETRY_INTERVAL_S)

        log.error("failed to connect spk socket after %.0fs", _SOCKET_RETRY_TIMEOUT_S)

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
