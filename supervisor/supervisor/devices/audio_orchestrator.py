"""Unified audio orchestrator for planner speech and /converse PTT sessions."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import queue
import shutil
import threading
import time
from dataclasses import dataclass

import httpx

from supervisor.devices.conversation_manager import ConversationManager
from supervisor.devices.face_client import FaceClient
from supervisor.devices.lip_sync import LipSyncTracker
from supervisor.devices.protocol import FaceButtonEventType, FaceButtonId

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
PLANNER_SPEECH_QUEUE_MAX = 5
PLAYBACK_CHUNK_QUEUE_MAX = 512
_STREAM_CHUNK_BYTES = 320  # 10 ms @ 16kHz, int16 mono


@dataclass(slots=True)
class _SpeechRequest:
    text: str
    emotion: str


class AudioOrchestrator:
    """Owns planner speech queue and PTT conversation arbitration."""

    def __init__(
        self,
        planner_url: str,
        *,
        robot_id: str,
        face: FaceClient | None = None,
        speaker_device: str = "default",
        mic_device: str = "default",
    ) -> None:
        self._planner_url = planner_url.rstrip("/")
        self._robot_id = str(robot_id or "").strip()
        self._face = face
        self._speaker_device = speaker_device
        self._run = False
        self._main_loop: asyncio.AbstractEventLoop | None = None

        self._conversation = ConversationManager(
            self._planner_url,
            robot_id=self._robot_id,
            face=face,
            speaker_device=speaker_device,
            mic_device=mic_device,
        )
        self._planner_client: httpx.AsyncClient | None = None

        self._speech_request_queue: asyncio.Queue[_SpeechRequest] = asyncio.Queue(
            maxsize=PLANNER_SPEECH_QUEUE_MAX
        )
        self._playback_chunk_queue: queue.Queue[bytes | None] = queue.Queue(
            maxsize=PLAYBACK_CHUNK_QUEUE_MAX
        )
        self._playback_thread: threading.Thread | None = None
        self._speech_task: asyncio.Task | None = None
        self._planner_speaking = False
        self._cancel_planner_speech = asyncio.Event()
        self._active_aplay_proc: asyncio.subprocess.Process | None = None
        self._planner_speech_seq = 0
        self._lip_sync = LipSyncTracker()

    @property
    def connected(self) -> bool:
        return self._conversation.connected

    @property
    def speaking(self) -> bool:
        return self._planner_speaking or self._conversation.speaking

    @property
    def ptt_enabled(self) -> bool:
        return self._conversation.ptt_enabled

    @property
    def speech_queue_depth(self) -> int:
        return self._speech_request_queue.qsize()

    async def start(self) -> None:
        if self._run:
            return
        self._run = True
        self._main_loop = asyncio.get_running_loop()
        self._planner_client = httpx.AsyncClient(
            base_url=self._planner_url,
            timeout=httpx.Timeout(30.0),
        )
        await self._conversation.start()
        self._speech_task = asyncio.create_task(self._planner_speech_consume_loop())

    async def stop(self) -> None:
        self._run = False
        await self.cancel_planner_speech()
        if self._playback_thread is not None:
            with contextlib.suppress(queue.Full):
                self._playback_chunk_queue.put_nowait(None)
            self._playback_thread.join(timeout=1.0)
            self._playback_thread = None
        if self._speech_task and not self._speech_task.done():
            self._speech_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._speech_task
        self._speech_task = None
        await self._conversation.stop()
        if self._planner_client is not None:
            await self._planner_client.aclose()
            self._planner_client = None

    async def cancel(self) -> None:
        await self.cancel_planner_speech()
        await self._conversation.cancel()

    async def set_ptt_enabled(self, enabled: bool) -> None:
        if enabled:
            await self.cancel_planner_speech()
        await self._conversation.set_ptt_enabled(enabled)

    def enqueue_speech(self, text: str, *, emotion: str = "neutral") -> bool:
        if not isinstance(text, str):
            return False
        clean = text.strip()
        if not clean:
            return False
        req = _SpeechRequest(text=clean[:200], emotion=str(emotion or "neutral"))
        try:
            self._speech_request_queue.put_nowait(req)
            return True
        except asyncio.QueueFull:
            return False

    async def cancel_planner_speech(self) -> None:
        self._cancel_planner_speech.set()
        while not self._speech_request_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._speech_request_queue.get_nowait()
        while not self._playback_chunk_queue.empty():
            with contextlib.suppress(queue.Empty):
                self._playback_chunk_queue.get_nowait()

        proc = self._active_aplay_proc
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=0.3)
            if proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
        self._active_aplay_proc = None
        self._planner_speaking = False
        if self._face:
            self._face.send_talking(False, 0)

    def on_face_button(self, evt) -> None:
        if evt.button_id == int(FaceButtonId.PTT) and evt.event_type == int(
            FaceButtonEventType.TOGGLE
        ):
            asyncio.create_task(self.set_ptt_enabled(bool(evt.state)))

    def debug_snapshot(self) -> dict:
        return {
            "robot_id": self._robot_id,
            "connected": self.connected,
            "speaking": self.speaking,
            "planner_speaking": self._planner_speaking,
            "ptt_enabled": self.ptt_enabled,
            "speech_queue_depth": self.speech_queue_depth,
        }

    async def _planner_speech_consume_loop(self) -> None:
        """Pulls requests from the queue and executes them."""
        while self._run:
            req = await self._speech_request_queue.get()
            self._cancel_planner_speech.clear()
            try:
                await self._play_tts_request(req)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("planner speech failed")

    def _playback_thread_loop(self) -> None:
        """Dedicated thread for writing to the blocking aplay stdin."""
        proc = self._active_aplay_proc
        if proc is None or proc.stdin is None or self._main_loop is None:
            return

        try:
            while self._run:
                try:
                    chunk = self._playback_chunk_queue.get(timeout=1.0)
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

                if self._face:
                    energy = self._lip_sync.update_chunk(chunk)
                    self._main_loop.call_soon_threadsafe(self._face.send_talking, True, energy)
        finally:
            log.info("Playback thread finished for planner speech.")

    async def _play_tts_request(self, req: _SpeechRequest) -> None:
        if self._planner_client is None:
            return
        if shutil.which("aplay") is None:
            log.warning("aplay not found; planner speech disabled")
            return

        if self._conversation.speaking:
            log.warning("Planner speech dropped: conversation is active")
            return

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
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._active_aplay_proc = proc
        self._planner_speaking = True
        self._lip_sync.reset()

        if self._playback_thread is None or not self._playback_thread.is_alive():
            self._playback_thread = threading.Thread(
                target=self._playback_thread_loop, daemon=True
            )
            self._playback_thread.start()

        try:
            if self._face:
                self._face.send_talking(True, 0)
            async with self._planner_client.stream(
                "POST",
                "/tts",
                json={
                    "text": req.text,
                    "emotion": req.emotion,
                    "robot_id": self._robot_id,
                    "seq": self._planner_speech_seq,
                    "monotonic_ts_ms": int(time.monotonic() * 1000),
                },
            ) as resp:
                self._planner_speech_seq += 1
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    log.warning("planner /tts failed: %s %s", resp.status_code, body[:200])
                    return

                async for chunk in resp.aiter_bytes(_STREAM_CHUNK_BYTES):
                    if self._cancel_planner_speech.is_set():
                        break
                    await asyncio.to_thread(self._playback_chunk_queue.put, chunk)

        finally:
            # Signal playback thread to exit
            await asyncio.to_thread(self._playback_chunk_queue.put, None)

            if proc.stdin:
                with contextlib.suppress(Exception):
                    proc.stdin.close()
                await proc.stdin.wait_closed()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=0.5)
            if proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.kill()
                await proc.wait()

            self._active_aplay_proc = None
            self._planner_speaking = False
            self._cancel_planner_speech.clear()
            self._lip_sync.reset()
            if self._face:
                self._face.send_talking(False, 0)
