"""Conversation manager — bridges ESP32 mic/speaker with the personality server.

Connects to the server's WS /converse endpoint and coordinates:
- Forwarding mic audio from ESP32 to the server
- Receiving emotion metadata and sending face commands
- Receiving TTS audio and streaming to ESP32 speaker
- Managing talking animation state
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import struct

from supervisor.devices.face_client import FaceClient
from supervisor.devices.protocol import FaceMood

log = logging.getLogger(__name__)

# Map emotion names from server to FaceMood IDs
_EMOTION_TO_MOOD: dict[str, int] = {
    "neutral": int(FaceMood.NEUTRAL),
    "happy": int(FaceMood.HAPPY),
    "excited": int(FaceMood.EXCITED),
    "curious": int(FaceMood.CURIOUS),
    "sad": int(FaceMood.SAD),
    "scared": int(FaceMood.SCARED),
    "angry": int(FaceMood.ANGRY),
    "surprised": int(FaceMood.SURPRISED),
    "sleepy": int(FaceMood.SLEEPY),
    "love": int(FaceMood.LOVE),
    "silly": int(FaceMood.SILLY),
    "thinking": int(FaceMood.THINKING),
}

# Audio format constants
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit signed
CHUNK_MS = 10
CHUNK_BYTES = SAMPLE_RATE * SAMPLE_WIDTH * CHUNK_MS // 1000  # 320 bytes per 10ms
MIC_QUEUE_MAX_CHUNKS = 256
VAD_START_ENERGY = 12
VAD_END_ENERGY = 8
VAD_END_SILENCE_MS = 500
VAD_GAP_END_MS = 300
RECONNECT_BACKOFF_S = 1.5


def _compute_rms_energy(pcm_chunk: bytes) -> int:
    """Compute RMS energy of a PCM chunk, returned as 0-255."""
    if len(pcm_chunk) < 2:
        return 0
    n_samples = len(pcm_chunk) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_chunk[: n_samples * 2])
    rms = math.sqrt(sum(s * s for s in samples) / n_samples)
    # Scale: 32768 max → 255 output, with some headroom
    return min(255, int(rms / 128))


class ConversationManager:
    """Manages bidirectional audio + emotion flow between ESP32 and server.

    Lifecycle:
        1. start() — connect to server WebSocket
        2. send_text() or send_audio() — forward user input
        3. Server responses trigger face commands and audio streaming
        4. stop() — disconnect
    """

    def __init__(
        self,
        server_url: str,
        face: FaceClient | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._face = face
        self._ws = None
        self._reconnect_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._mic_task: asyncio.Task | None = None
        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=MIC_QUEUE_MAX_CHUNKS)
        self._connected = False
        self._speaking = False
        self._mic_drop_count = 0
        self._run = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def speaking(self) -> bool:
        return self._speaking

    async def start(self) -> None:
        """Start background connection management for /converse WebSocket."""
        if self._run:
            return
        self._run = True
        if self._mic_task is None or self._mic_task.done():
            self._mic_task = asyncio.create_task(self._mic_forward_loop())
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Disconnect from the server."""
        self._run = False
        self._connected = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        if self._mic_task and not self._mic_task.done():
            self._mic_task.cancel()
            try:
                await self._mic_task
            except asyncio.CancelledError:
                pass
            self._mic_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        while not self._mic_queue.empty():
            try:
                self._mic_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._stop_talking()
        log.info("Conversation disconnected")

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
        """Forward a mic audio chunk (16-bit, 16 kHz, mono) to the server."""
        if not self._ws or not self._connected:
            return
        try:
            encoded = base64.b64encode(pcm_chunk).decode("ascii")
            await self._ws.send(json.dumps({"type": "audio", "data": encoded}))
        except Exception:
            self._mark_disconnected("send_audio")
            log.exception("Conversation send_audio_chunk failed")

    async def end_utterance(self) -> None:
        """Signal end of speech (VAD silence detected)."""
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
        self._stop_talking()

    def submit_mic_audio_chunk(self, pcm_chunk: bytes) -> None:
        """Queue one 10 ms mic chunk from face telemetry for forwarding to server."""
        if not pcm_chunk:
            return
        if len(pcm_chunk) % 2:
            pcm_chunk = pcm_chunk[:-1]
        if not pcm_chunk:
            return
        if self._mic_queue.full():
            try:
                self._mic_queue.get_nowait()
                self._mic_drop_count += 1
            except asyncio.QueueEmpty:
                pass
        try:
            self._mic_queue.put_nowait(pcm_chunk)
        except asyncio.QueueFull:
            self._mic_drop_count += 1

    # -- Private: receive loop ---------------------------------------------------

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
                    self._stop_talking()
                elif msg_type == "listening":
                    pass
                elif msg_type == "error":
                    log.warning("Server error: %s", msg.get("message", ""))
                    self._stop_talking()

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
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None

            self._ws = await websockets.connect(
                f"{ws_url}/converse",
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True
            if self._receive_task is None or self._receive_task.done():
                self._receive_task = asyncio.create_task(self._receive_loop())
            log.info("Conversation connected to %s/converse", ws_url)
        except Exception as exc:
            self._connected = False
            self._ws = None
            log.warning("Conversation connect failed: %s", exc)

    def _mark_disconnected(self, reason: str) -> None:
        if self._connected:
            log.warning("Conversation disconnected (%s)", reason)
        self._connected = False

    async def _mic_forward_loop(self) -> None:
        """Forward face mic chunks to server and emit end_utterance via simple VAD."""
        utterance_active = False
        silence_ms = 0

        try:
            while True:
                try:
                    pcm_chunk = await asyncio.wait_for(
                        self._mic_queue.get(),
                        timeout=VAD_GAP_END_MS / 1000.0,
                    )
                except TimeoutError:
                    if utterance_active and self._connected:
                        await self.end_utterance()
                        utterance_active = False
                        silence_ms = 0
                    continue

                if not self._connected:
                    utterance_active = False
                    silence_ms = 0
                    continue

                energy = _compute_rms_energy(pcm_chunk)
                is_voice = energy >= (VAD_START_ENERGY if not utterance_active else VAD_END_ENERGY)

                if not utterance_active:
                    if not is_voice:
                        continue
                    utterance_active = True
                    silence_ms = 0

                await self.send_audio_chunk(pcm_chunk)

                if is_voice:
                    silence_ms = 0
                else:
                    silence_ms += CHUNK_MS
                    if silence_ms >= VAD_END_SILENCE_MS:
                        await self.end_utterance()
                        utterance_active = False
                        silence_ms = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Conversation mic forward loop error")

    def _handle_emotion(self, msg: dict) -> None:
        """Send emotion to face display."""
        emotion = msg.get("emotion", "neutral")
        intensity = msg.get("intensity", 0.5)
        mood_id = _EMOTION_TO_MOOD.get(emotion, int(FaceMood.NEUTRAL))

        if self._face:
            self._face.send_state(
                emotion_id=mood_id,
                intensity=float(intensity),
            )
        log.debug("Emotion: %s (%.1f) → mood_id=%d", emotion, intensity, mood_id)

    def _handle_gestures(self, msg: dict) -> None:
        """Trigger gesture animations on the face."""
        from supervisor.devices.protocol import FaceGesture

        gesture_map = {
            "blink": int(FaceGesture.BLINK),
            "wink_l": int(FaceGesture.WINK_L),
            "wink_r": int(FaceGesture.WINK_R),
            "confused": int(FaceGesture.CONFUSED),
            "laugh": int(FaceGesture.LAUGH),
            "surprise": int(FaceGesture.SURPRISE),
            "heart": int(FaceGesture.HEART),
            "x_eyes": int(FaceGesture.X_EYES),
            "sleepy": int(FaceGesture.SLEEPY),
            "rage": int(FaceGesture.RAGE),
            "nod": int(FaceGesture.NOD),
            "headshake": int(FaceGesture.HEADSHAKE),
            "wiggle": int(FaceGesture.WIGGLE),
        }

        for name in msg.get("names", []):
            gesture_id = gesture_map.get(name)
            if gesture_id is not None and self._face:
                self._face.send_gesture(gesture_id)

    def _handle_audio(self, msg: dict) -> None:
        """Stream TTS audio to ESP32 speaker with talking animation."""
        data = msg.get("data", "")
        if not data:
            return

        pcm_chunk = base64.b64decode(data)
        if not pcm_chunk:
            return

        if not self._speaking:
            self._speaking = True
            if self._face:
                self._face.send_talking(True, 128)

        if not self._face:
            return

        for off in range(0, len(pcm_chunk), CHUNK_BYTES):
            sub = pcm_chunk[off : off + CHUNK_BYTES]
            if len(sub) % 2:
                sub = sub[:-1]
            if not sub:
                continue
            energy = _compute_rms_energy(sub)
            self._face.send_talking(True, energy)
            self._face.send_audio_data(sub)

    def _stop_talking(self) -> None:
        """End talking animation."""
        if self._speaking:
            self._speaking = False
            if self._face:
                self._face.send_talking(False, 0)
