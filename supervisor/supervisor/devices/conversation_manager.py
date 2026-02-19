"""Conversation manager — bridges planner server with local USB audio + face."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import math
import shutil
import struct

from supervisor.devices.expressions import (
    EMOTION_TO_FACE_MOOD,
    GESTURE_TO_FACE_ID,
    normalize_emotion_name,
    normalize_face_gesture_name,
)
from supervisor.devices.face_client import FaceClient

log = logging.getLogger(__name__)

# Audio format constants (planner server stream + local USB audio)
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit signed
CHANNELS = 1
CHUNK_MS = 10
CHUNK_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * CHUNK_MS // 1000  # 320 bytes per 10ms
PLAYBACK_QUEUE_MAX_CHUNKS = 512
RECONNECT_BACKOFF_S = 1.5


def _compute_rms_energy(pcm_chunk: bytes) -> int:
    """Compute RMS energy of a PCM chunk, returned as 0-255."""
    if len(pcm_chunk) < 2:
        return 0
    n_samples = len(pcm_chunk) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_chunk[: n_samples * 2])
    rms = math.sqrt(sum(s * s for s in samples) / n_samples)
    return min(255, int(rms / 128))


class ConversationManager:
    """Manages emotion + speech flow between server and local robot clients."""

    def __init__(
        self,
        server_url: str,
        face: FaceClient | None = None,
        speaker_device: str = "default",
        mic_device: str = "default",
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._face = face
        self._speaker_device = speaker_device
        self._mic_device = mic_device
        self._ws = None
        self._reconnect_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._playback_task: asyncio.Task | None = None
        self._mic_forward_task: asyncio.Task | None = None
        self._playback_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=PLAYBACK_QUEUE_MAX_CHUNKS
        )
        self._speaker_proc: asyncio.subprocess.Process | None = None
        self._mic_proc: asyncio.subprocess.Process | None = None
        self._connected = False
        self._speaking = False
        self._run = False
        self._ptt_enabled = False
        self._logged_missing_aplay = False
        self._logged_missing_arecord = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def speaking(self) -> bool:
        return self._speaking

    @property
    def ptt_enabled(self) -> bool:
        return self._ptt_enabled

    async def start(self) -> None:
        """Start background connection management for /converse WebSocket."""
        if self._run:
            return
        self._run = True
        if self._playback_task is None or self._playback_task.done():
            self._playback_task = asyncio.create_task(self._playback_loop())
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Disconnect from server and stop local audio I/O."""
        self._run = False
        self._connected = False
        await self.set_ptt_enabled(False)

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        await self._stop_talking()

        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._playback_task
            self._playback_task = None

        await self._stop_speaker_playback()

        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

        log.info("Conversation disconnected")

    async def set_ptt_enabled(self, enabled: bool) -> None:
        """Enable/disable local USB mic streaming to /converse."""
        enabled = bool(enabled)
        if enabled == self._ptt_enabled:
            return
        self._ptt_enabled = enabled
        if enabled:
            await self._start_mic_capture()
        else:
            await self._stop_mic_capture(send_end_utterance=True)

    async def send_text(self, text: str) -> None:
        """Send text input directly (bypass STT)."""
        if not self._ws or not self._connected:
            log.warning("Cannot send text: not connected")
            return
        try:
            await self._ws.send(json.dumps({"type": "text", "text": text}))
        except Exception:
            self._mark_disconnected("send_text")
            log.exception("Conversation send_text failed")

    async def send_audio_chunk(self, pcm_chunk: bytes) -> None:
        """Forward one PCM chunk to server."""
        if not self._ws or not self._connected:
            return
        try:
            encoded = base64.b64encode(pcm_chunk).decode("ascii")
            await self._ws.send(json.dumps({"type": "audio", "data": encoded}))
        except Exception:
            self._mark_disconnected("send_audio")
            log.exception("Conversation send_audio_chunk failed")

    async def end_utterance(self) -> None:
        """Signal end of speech."""
        if not self._ws or not self._connected:
            return
        try:
            await self._ws.send(json.dumps({"type": "end_utterance"}))
        except Exception:
            self._mark_disconnected("end_utterance")
            log.exception("Conversation end_utterance failed")

    async def cancel(self) -> None:
        """Cancel the current utterance."""
        if not self._ws or not self._connected:
            return
        try:
            await self._ws.send(json.dumps({"type": "cancel"}))
        except Exception:
            self._mark_disconnected("cancel")
            log.exception("Conversation cancel failed")
        await self._stop_talking()

    # -- server receive ------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Process messages from the server."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "emotion":
                    self._handle_emotion(msg)
                elif msg_type == "gestures":
                    self._handle_gestures(msg)
                elif msg_type == "audio":
                    self._handle_audio(msg)
                elif msg_type == "transcription":
                    log.info("User said: %s", msg.get("text", "")[:120])
                elif msg_type == "done":
                    await self._stop_talking()
                elif msg_type == "listening":
                    pass
                elif msg_type == "error":
                    log.warning("Server error: %s", msg.get("message", ""))
                    await self._stop_talking()

        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Conversation receive loop error")
            self._mark_disconnected("receive")
        finally:
            self._mark_disconnected("receive_done")

    async def _connection_loop(self) -> None:
        """Maintain websocket connection and auto-reconnect on errors."""
        while self._run:
            if not self._connected:
                await self._connect_once()
                if not self._connected:
                    await asyncio.sleep(RECONNECT_BACKOFF_S)
                    continue
            await asyncio.sleep(0.2)

    async def _connect_once(self) -> None:
        ws_url = self._server_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        try:
            import websockets

            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()
                self._ws = None

            self._ws = await websockets.connect(
                f"{ws_url}/converse",
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True
            if self._receive_task is None or self._receive_task.done():
                self._receive_task = asyncio.create_task(self._receive_loop())
            if self._ptt_enabled:
                await self._start_mic_capture()
            log.info("Conversation connected to %s/converse", ws_url)
        except Exception as exc:
            self._connected = False
            self._ws = None
            log.warning("Conversation connect failed: %s", exc)

    def _mark_disconnected(self, reason: str) -> None:
        if self._connected:
            log.warning("Conversation disconnected (%s)", reason)
        self._connected = False
        if self._speaking:
            asyncio.create_task(self._stop_talking())
        if self._mic_forward_task and not self._mic_forward_task.done():
            asyncio.create_task(self._stop_mic_capture(send_end_utterance=False))

    # -- face + audio handlers ----------------------------------------------

    def _handle_emotion(self, msg: dict) -> None:
        """Send emotion to face display."""
        raw_emotion = str(msg.get("emotion", "neutral"))
        intensity = msg.get("intensity", 0.5)
        emotion = normalize_emotion_name(raw_emotion) or "neutral"
        mood_id = EMOTION_TO_FACE_MOOD[emotion]

        if self._face:
            self._face.send_state(
                emotion_id=mood_id,
                intensity=float(intensity),
            )
        log.debug("Emotion: %s (%.1f) -> mood_id=%d", emotion, intensity, mood_id)

    def _handle_gestures(self, msg: dict) -> None:
        """Trigger gesture animations on the face."""
        names = msg.get("names", [])
        if not isinstance(names, list):
            return
        for raw_name in names:
            if not isinstance(raw_name, str):
                continue
            name = normalize_face_gesture_name(raw_name)
            if name is None:
                continue
            gesture_id = GESTURE_TO_FACE_ID.get(name)
            if gesture_id is not None and self._face:
                self._face.send_gesture(gesture_id)

    def _handle_audio(self, msg: dict) -> None:
        """Route streamed TTS audio to local USB speaker and face talking animation."""
        data = msg.get("data", "")
        if not data:
            return

        try:
            pcm_chunk = base64.b64decode(data)
        except Exception:
            return
        if not pcm_chunk:
            return

        if not self._speaking:
            self._speaking = True
            if self._face:
                self._face.send_talking(True, 128)

        for off in range(0, len(pcm_chunk), CHUNK_BYTES):
            sub = pcm_chunk[off : off + CHUNK_BYTES]
            if len(sub) % 2:
                sub = sub[:-1]
            if not sub:
                continue
            self._queue_playback_chunk(sub)
            if self._face:
                energy = _compute_rms_energy(sub)
                self._face.send_talking(True, energy)

    async def _stop_talking(self) -> None:
        """End talking animation and flush/stop local playback."""
        if not self._speaking:
            return
        self._speaking = False
        self._clear_playback_queue()
        await self._stop_speaker_playback()
        if self._face:
            self._face.send_talking(False, 0)

    # -- local speaker playback ---------------------------------------------

    def _queue_playback_chunk(self, pcm_chunk: bytes) -> None:
        if self._playback_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._playback_queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self._playback_queue.put_nowait(pcm_chunk)

    def _clear_playback_queue(self) -> None:
        while True:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._playback_queue.get_nowait()
                continue
            break

    async def _playback_loop(self) -> None:
        while True:
            chunk = await self._playback_queue.get()
            await self._play_audio_chunk(chunk)

    async def _play_audio_chunk(self, pcm_chunk: bytes) -> None:
        if not await self._ensure_speaker_proc():
            return
        proc = self._speaker_proc
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(pcm_chunk)
            await proc.stdin.drain()
        except Exception as e:
            log.warning("speaker write failed: %s", e)
            await self._stop_speaker_playback()

    async def _ensure_speaker_proc(self) -> bool:
        if self._speaker_proc and self._speaker_proc.returncode is None:
            return True
        if shutil.which("aplay") is None:
            if not self._logged_missing_aplay:
                self._logged_missing_aplay = True
                log.warning("aplay not found; local speaker playback disabled")
            return False

        cmd = [
            "aplay",
            "-q",
            "-D",
            self._speaker_device,
            "-c",
            str(CHANNELS),
            "-r",
            str(SAMPLE_RATE),
            "-f",
            "S16_LE",
            "-t",
            "raw",
        ]
        try:
            self._speaker_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            log.info("speaker playback started via aplay device=%s", self._speaker_device)
            return True
        except Exception as e:
            log.warning("failed to start aplay (%s): %s", self._speaker_device, e)
            self._speaker_proc = None
            return False

    async def _stop_speaker_playback(self) -> None:
        proc = self._speaker_proc
        if proc is None:
            return
        self._speaker_proc = None

        if proc.stdin:
            with contextlib.suppress(Exception):
                proc.stdin.close()
            with contextlib.suppress(Exception):
                await proc.stdin.wait_closed()
        with contextlib.suppress(Exception):
            proc.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=0.6)
        if proc.returncode is None:
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()

    # -- local mic capture ---------------------------------------------------

    async def _start_mic_capture(self) -> None:
        if not self._run:
            return
        if not self._connected:
            log.info("PTT enabled but /converse is not connected yet")
            return
        if self._mic_forward_task and not self._mic_forward_task.done():
            return
        if shutil.which("arecord") is None:
            if not self._logged_missing_arecord:
                self._logged_missing_arecord = True
                log.warning("arecord not found; local USB mic capture disabled")
            return

        cmd = [
            "arecord",
            "-q",
            "-D",
            self._mic_device,
            "-c",
            str(CHANNELS),
            "-r",
            str(SAMPLE_RATE),
            "-f",
            "S16_LE",
            "-t",
            "raw",
        ]
        try:
            self._mic_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._mic_forward_task = asyncio.create_task(self._mic_forward_loop())
            log.info("PTT mic capture started via arecord device=%s", self._mic_device)
        except Exception as e:
            self._mic_proc = None
            log.warning("failed to start arecord (%s): %s", self._mic_device, e)

    async def _stop_mic_capture(self, send_end_utterance: bool) -> None:
        task = self._mic_forward_task
        self._mic_forward_task = None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        proc = self._mic_proc
        self._mic_proc = None
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=0.5)
            if proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()

        if send_end_utterance:
            await self.end_utterance()

    async def _mic_forward_loop(self) -> None:
        proc = self._mic_proc
        if proc is None or proc.stdout is None:
            return

        try:
            while self._run and self._ptt_enabled and self._connected:
                chunk = await proc.stdout.read(CHUNK_BYTES)
                if not chunk:
                    break
                if len(chunk) % 2:
                    chunk = chunk[:-1]
                if chunk:
                    await self.send_audio_chunk(chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("PTT mic forward loop failed")
        finally:
            if self._ptt_enabled and self._run and self._connected:
                log.warning("PTT mic capture ended unexpectedly")
