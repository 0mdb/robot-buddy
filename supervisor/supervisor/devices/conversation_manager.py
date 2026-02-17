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
        self._receive_task: asyncio.Task | None = None
        self._connected = False
        self._speaking = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def speaking(self) -> bool:
        return self._speaking

    async def start(self) -> None:
        """Connect to the server's /converse WebSocket."""
        try:
            import websockets

            ws_url = self._server_url.replace("http://", "ws://").replace(
                "https://", "wss://"
            )
            self._ws = await websockets.connect(
                f"{ws_url}/converse",
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            log.info("Conversation connected to %s/converse", ws_url)
        except Exception:
            log.exception("Failed to connect conversation WebSocket")
            self._connected = False

    async def stop(self) -> None:
        """Disconnect from the server."""
        self._connected = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._stop_talking()
        log.info("Conversation disconnected")

    async def send_text(self, text: str) -> None:
        """Send text input directly (bypass STT)."""
        if not self._ws or not self._connected:
            log.warning("Cannot send text: not connected")
            return
        await self._ws.send(json.dumps({"type": "text", "text": text}))

    async def send_audio_chunk(self, pcm_chunk: bytes) -> None:
        """Forward a mic audio chunk (16-bit, 16 kHz, mono) to the server."""
        if not self._ws or not self._connected:
            return
        encoded = base64.b64encode(pcm_chunk).decode("ascii")
        await self._ws.send(json.dumps({"type": "audio", "data": encoded}))

    async def end_utterance(self) -> None:
        """Signal end of speech (VAD silence detected)."""
        if not self._ws or not self._connected:
            return
        await self._ws.send(json.dumps({"type": "end_utterance"}))

    async def cancel(self) -> None:
        """Cancel the current utterance."""
        if not self._ws or not self._connected:
            return
        await self._ws.send(json.dumps({"type": "cancel"}))
        self._stop_talking()

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
            self._connected = False

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

        if not self._speaking:
            self._speaking = True
            if self._face:
                self._face.send_talking(True, 128)

        # Compute energy for eye animation
        energy = _compute_rms_energy(pcm_chunk)
        if self._face:
            self._face.send_talking(True, energy)
            self._face.send_audio_data(pcm_chunk)

    def _stop_talking(self) -> None:
        """End talking animation."""
        if self._speaking:
            self._speaking = False
            if self._face:
                self._face.send_talking(False, 0)
