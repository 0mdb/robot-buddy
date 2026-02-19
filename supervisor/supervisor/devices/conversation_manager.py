"""Conversation manager — bridges planner server with local USB audio + face."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import queue
import shutil
import threading
import urllib.parse
from typing import AsyncIterator, Protocol, cast

from supervisor.devices.expressions import (
    EMOTION_TO_FACE_MOOD,
    GESTURE_TO_FACE_ID,
    normalize_emotion_name,
    normalize_face_gesture_name,
)
from supervisor.devices.face_client import FaceClient
from supervisor.devices.lip_sync import LipSyncTracker

log = logging.getLogger(__name__)

# Audio format constants (planner server stream + local USB audio)
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit signed
CHANNELS = 1
CHUNK_MS = 10
CHUNK_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * CHUNK_MS // 1000  # 320 bytes per 10ms
PLAYBACK_QUEUE_MAX_CHUNKS = 512
RECONNECT_BACKOFF_S = 1.5


class _WebSocketConn(Protocol):
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[str]: ...


class ConversationManager:
    """Manages emotion + speech flow between server and local robot clients."""

    def __init__(
        self,
        server_url: str,
        robot_id: str,
        face: FaceClient | None = None,
        speaker_device: str = "default",
        mic_device: str = "default",
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._robot_id = str(robot_id or "").strip()
        self._face = face
        self._speaker_device = speaker_device
        self._mic_device = mic_device
        self._ws: _WebSocketConn | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._mic_forward_task: asyncio.Task | None = None
        self._playback_queue: queue.Queue[bytes | None] = queue.Queue(
            maxsize=PLAYBACK_QUEUE_MAX_CHUNKS
        )
        self._playback_thread: threading.Thread | None = None
        self._speaker_proc: asyncio.subprocess.Process | None = None
        self._mic_proc: asyncio.subprocess.Process | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._connected = False
        self._speaking = False
        self._run = False
        self._ptt_enabled = False
        self._logged_missing_aplay = False
        self._logged_missing_arecord = False
        self._session_seq = 0
        self._last_face_mood: int | None = None
        self._last_face_intensity: float = 0.7
        self._lip_sync = LipSyncTracker()

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
        self._main_loop = asyncio.get_running_loop()
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

        if self._playback_thread is not None:
            with contextlib.suppress(queue.Full):
                self._playback_queue.put_nowait(None)
            self._playback_thread.join(timeout=1.0)
            self._playback_thread = None

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
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw in ws:
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
                    await self._handle_audio(msg)
                elif msg_type == "transcription":
                    log.info("User said: %s", msg.get("text", "")[:120])
                elif msg_type == "done":
                    await self._stop_talking(drain=True)
                elif msg_type == "listening":
                    pass
                elif msg_type == "error":
                    log.warning("Server error: %s", msg.get("message", ""))
                    await self._show_thinking_face()
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

            params = urllib.parse.urlencode(
                {
                    "robot_id": self._robot_id,
                    "session_seq": self._session_seq,
                    "session_monotonic_ts_ms": int(
                        asyncio.get_running_loop().time() * 1000
                    ),
                }
            )
            self._session_seq += 1
            self._ws = cast(
                _WebSocketConn,
                await websockets.connect(
                    f"{ws_url}/converse?{params}",
                    ping_interval=20,
                    ping_timeout=10,
                ),
            )
            self._connected = True
            if self._receive_task is None or self._receive_task.done():
                self._receive_task = asyncio.create_task(self._receive_loop())
            if self._ptt_enabled:
                await self._start_mic_capture()
            log.info(
                "Conversation connected to %s/converse (robot_id=%s)",
                ws_url,
                self._robot_id,
            )
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
        self._last_face_mood = mood_id
        self._last_face_intensity = float(intensity)

        if self._face:
            self._face.send_state(
                emotion_id=mood_id,
                intensity=float(intensity),
            )
        log.debug("Emotion: %s (%.1f) -> mood_id=%d", emotion, intensity, mood_id)

    async def _show_thinking_face(self) -> None:
        if self._face is None:
            return
        thinking_mood = EMOTION_TO_FACE_MOOD.get("thinking")
        if thinking_mood is None:
            return

        self._face.send_state(emotion_id=thinking_mood, intensity=0.7)
        await asyncio.sleep(0.6)
        if self._last_face_mood is not None:
            self._face.send_state(
                emotion_id=self._last_face_mood,
                intensity=self._last_face_intensity,
            )

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

    async def _handle_audio(self, msg: dict) -> None:
        """Route streamed TTS audio to local USB speaker and face talking animation."""
        if not await self._ensure_speaker_proc():
            return
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
            self._lip_sync.reset()
            if self._face:
                self._face.send_talking(True, 128)

        for off in range(0, len(pcm_chunk), CHUNK_BYTES):
            sub = pcm_chunk[off : off + CHUNK_BYTES]
            if len(sub) % 2:
                sub = sub[:-1]
            if not sub:
                continue
            self._queue_playback_chunk(sub)

    async def _stop_talking(self, *, drain: bool = False) -> None:
        """End talking animation and flush/stop local playback."""
        if not self._speaking:
            return
        if drain:
            await self._drain_playback_queue()
        else:
            self._clear_playback_queue()

        # The playback thread will stop when the queue is empty.
        # No need to explicitly stop the speaker process here,
        # as the thread manages its lifecycle.

        self._speaking = False
        self._lip_sync.reset()
        if self._face:
            self._face.send_talking(False, 0)

    # -- local speaker playback ---------------------------------------------

    def _queue_playback_chunk(self, pcm_chunk: bytes) -> None:
        try:
            self._playback_queue.put_nowait(pcm_chunk)
        except queue.Full:
            # Drop oldest chunk to make room
            with contextlib.suppress(queue.Empty):
                self._playback_queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self._playback_queue.put_nowait(pcm_chunk)

    def _clear_playback_queue(self) -> None:
        while not self._playback_queue.empty():
            with contextlib.suppress(queue.Empty):
                self._playback_queue.get_nowait()

    def _playback_thread_loop(self) -> None:
        """Dedicated thread for writing to the blocking aplay stdin."""
        proc = self._speaker_proc
        if proc is None or proc.stdin is None or self._main_loop is None:
            return

        while self._run:
            try:
                chunk = self._playback_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if chunk is None:
                break

            try:
                proc.stdin.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            except Exception as e:
                log.warning("aplay stdin write failed: %s", e)
                break

            if self._speaking and self._face:
                coro = self._face.send_talking(True, self._lip_sync.update_chunk(chunk))
                asyncio.run_coroutine_threadsafe(coro, self._main_loop)

        log.info("Playback thread finished.")

    async def _drain_playback_queue(self) -> None:
        """Wait briefly for queued PCM to flush to the speaker pipeline."""
        while not self._playback_queue.empty():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.04)

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
            "--buffer-time=20000",
            "--period-time=10000",
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
            if self._playback_thread is None or not self._playback_thread.is_alive():
                self._playback_thread = threading.Thread(
                    target=self._playback_thread_loop, daemon=True
                )
                self._playback_thread.start()
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