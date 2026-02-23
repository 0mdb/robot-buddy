"""Ear worker — always-on microphone with wake word detection + VAD.

Owns the microphone (arecord). Continuously runs OpenWakeWord inference
to detect "Hey Buddy".  During active conversations, forwards PCM to the
AI worker via the rb-mic Unix socket and runs Silero VAD to detect
end-of-utterance silence.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time
from pathlib import Path
from typing import Any

from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    EAR_CMD_PAUSE_VAD,
    EAR_CMD_RESUME_VAD,
    EAR_CMD_START_LISTENING,
    EAR_CMD_STOP_LISTENING,
    EAR_CONFIG_INIT,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_WAKE_WORD,
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
)
from supervisor.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

# Audio constants — must match TTS / AI workers
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit signed LE
CHANNELS = 1
CHUNK_BYTES = 320  # 10 ms at 16 kHz mono

# OpenWakeWord operates on 80 ms frames
_OWW_FRAME_BYTES = int(SAMPLE_RATE * SAMPLE_WIDTH * 0.08)  # 2560

# Silero VAD operates on 30 ms frames (512 samples at 16 kHz)
_VAD_FRAME_SAMPLES = 512
_VAD_FRAME_BYTES = _VAD_FRAME_SAMPLES * SAMPLE_WIDTH  # 1024

# Socket retry
_SOCKET_RETRY_INTERVAL_S = 0.1
_SOCKET_RETRY_TIMEOUT_S = 30.0

# Wake word cooldown — suppress re-triggers during active conversation
_WW_COOLDOWN_S = 3.0


class EarWorker(BaseWorker):
    domain = "ear"

    def __init__(self) -> None:
        super().__init__()
        # Config (from ear.config.init)
        self._mic_device: str = "default"
        self._mic_socket_path: str = ""
        self._wakeword_model_path: str = ""
        self._wakeword_threshold: float = 0.5
        self._vad_silence_ms: int = 1200
        self._vad_min_speech_ms: int = 300
        self._configured = asyncio.Event()

        # State
        self._listening = False  # True when forwarding audio to AI
        self._vad_paused = False  # Suppress VAD during TTS playback

        # Models (loaded lazily in run())
        self._oww_model: Any = None
        self._vad_session: Any = None  # onnxruntime InferenceSession
        self._vad_h: Any = None  # Silero VAD hidden state
        self._vad_c: Any = None  # Silero VAD cell state

        # Buffers
        self._ww_buffer = bytearray()
        self._vad_buffer = bytearray()

        # VAD state machine
        self._speech_detected = False
        self._speech_start_mono: float = 0.0
        self._silence_start_mono: float = 0.0

        # Wake word timing
        self._last_ww_mono: float = 0.0

        # Socket + process
        self._mic_sock: socket.socket | None = None
        self._arecord_proc: asyncio.subprocess.Process | None = None

    # ── Message handling ──────────────────────────────────────────

    async def on_message(self, envelope: Envelope) -> None:
        t = envelope.type
        p = envelope.payload

        if t == EAR_CONFIG_INIT:
            self._mic_device = str(p.get("mic_device", "default"))
            self._mic_socket_path = str(p.get("mic_socket_path", ""))
            self._wakeword_model_path = str(p.get("wakeword_model_path", ""))
            self._wakeword_threshold = float(p.get("wakeword_threshold", 0.5))
            self._vad_silence_ms = int(p.get("vad_silence_ms", 1200))
            self._vad_min_speech_ms = int(p.get("vad_min_speech_ms", 300))
            log.info(
                "configured: mic=%s, ww_model=%s, threshold=%.2f",
                self._mic_device,
                self._wakeword_model_path,
                self._wakeword_threshold,
            )
            self._configured.set()

        elif t == EAR_CMD_START_LISTENING:
            self._start_listening()

        elif t == EAR_CMD_STOP_LISTENING:
            self._stop_listening()

        elif t == EAR_CMD_PAUSE_VAD:
            self._vad_paused = True

        elif t == EAR_CMD_RESUME_VAD:
            self._vad_paused = False

    def _start_listening(self) -> None:
        """Begin forwarding mic audio and running VAD."""
        if self._listening:
            return
        self._listening = True
        self._vad_paused = False
        self._reset_vad_state()
        # Connect mic socket if not yet connected
        if not self._mic_sock and self._mic_socket_path:
            asyncio.create_task(self._connect_mic_socket())
        log.info("listening started")

    def _stop_listening(self) -> None:
        """Stop forwarding mic audio."""
        self._listening = False
        self._vad_paused = False
        self._reset_vad_state()
        self._vad_buffer.clear()
        log.info("listening stopped")

    def _reset_vad_state(self) -> None:
        self._speech_detected = False
        self._speech_start_mono = 0.0
        self._silence_start_mono = 0.0
        # Reset Silero hidden state
        if self._vad_session is not None:
            import numpy as np

            self._vad_h = np.zeros((2, 1, 64), dtype=np.float32)
            self._vad_c = np.zeros((2, 1, 64), dtype=np.float32)

    def health_payload(self) -> dict[str, Any]:
        return {
            "listening": self._listening,
            "vad_paused": self._vad_paused,
            "speech_detected": self._speech_detected,
            "oww_loaded": self._oww_model is not None,
            "vad_loaded": self._vad_session is not None,
        }

    # ── Main loop ─────────────────────────────────────────────────

    async def run(self) -> None:
        # Wait for config
        try:
            await asyncio.wait_for(self._configured.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.error("ear worker never received config, exiting")
            return

        # Load models in background thread
        await asyncio.to_thread(self._load_models)

        # Spawn arecord (always-on)
        self._arecord_proc = await asyncio.create_subprocess_exec(
            "arecord",
            "-D",
            self._mic_device,
            "-r",
            str(SAMPLE_RATE),
            "-f",
            "S16_LE",
            "-c",
            str(CHANNELS),
            "-t",
            "raw",
            "-q",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        log.info("arecord started (device=%s)", self._mic_device)

        try:
            await self._capture_loop()
        except asyncio.CancelledError:
            pass
        finally:
            await self._kill_arecord()

    def _load_models(self) -> None:
        """Load OpenWakeWord and Silero VAD models (runs in thread)."""
        import numpy as np

        # ── OpenWakeWord ──────────────────────────────────────────
        ww_path = self._wakeword_model_path
        if ww_path and Path(ww_path).exists():
            try:
                from openwakeword.model import Model  # type: ignore[import-untyped]

                self._oww_model = Model(
                    wakeword_models=[ww_path],
                    inference_framework="onnx",
                )
                log.info("OpenWakeWord model loaded: %s", ww_path)
            except Exception:
                log.exception("failed to load OpenWakeWord model")
        else:
            log.warning("wake word model not found at %s — wake word disabled", ww_path)

        # ── Silero VAD ────────────────────────────────────────────
        vad_path = Path(__file__).parent.parent / "models" / "silero_vad.onnx"
        if vad_path.exists():
            try:
                import onnxruntime as ort  # type: ignore[import-untyped]

                opts = ort.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                self._vad_session = ort.InferenceSession(
                    str(vad_path), sess_options=opts
                )
                self._vad_h = np.zeros((2, 1, 64), dtype=np.float32)
                self._vad_c = np.zeros((2, 1, 64), dtype=np.float32)
                log.info("Silero VAD loaded: %s", vad_path)
            except Exception:
                log.exception("failed to load Silero VAD")
        else:
            log.warning("Silero VAD model not found at %s — VAD disabled", vad_path)

    # ── Capture loop ──────────────────────────────────────────────

    async def _capture_loop(self) -> None:
        """Read 10 ms chunks from arecord and process."""
        assert self._arecord_proc and self._arecord_proc.stdout

        while self.running and self._arecord_proc.stdout:
            data = await self._arecord_proc.stdout.read(CHUNK_BYTES)
            if not data:
                break

            # Always: accumulate for wake word detection
            self._ww_buffer.extend(data)
            if len(self._ww_buffer) >= _OWW_FRAME_BYTES:
                frame = bytes(self._ww_buffer[:_OWW_FRAME_BYTES])
                del self._ww_buffer[:_OWW_FRAME_BYTES]
                await self._check_wake_word(frame)

            # During conversation: forward audio and run VAD
            if self._listening:
                self._forward_to_mic_socket(data)

                if not self._vad_paused:
                    self._vad_buffer.extend(data)
                    while len(self._vad_buffer) >= _VAD_FRAME_BYTES:
                        vad_frame = bytes(self._vad_buffer[:_VAD_FRAME_BYTES])
                        del self._vad_buffer[:_VAD_FRAME_BYTES]
                        self._check_vad(vad_frame)

    async def _check_wake_word(self, pcm_80ms: bytes) -> None:
        """Run OpenWakeWord inference on an 80 ms frame."""
        if self._oww_model is None:
            return

        # Don't trigger during active conversation
        if self._listening:
            return

        now = time.monotonic()
        if now - self._last_ww_mono < _WW_COOLDOWN_S:
            return

        try:
            import numpy as np

            # OWW expects int16 samples
            samples = np.frombuffer(pcm_80ms, dtype=np.int16)
            prediction = self._oww_model.predict(samples)

            # Check all model scores
            for name, score in prediction.items():
                if score >= self._wakeword_threshold:
                    self._last_ww_mono = now
                    log.info("wake word detected: %s (score=%.3f)", name, score)
                    self.send(
                        EAR_EVENT_WAKE_WORD,
                        {
                            "model": name,
                            "score": round(score, 3),
                        },
                    )
                    # Reset OWW internal buffers to prevent double-trigger
                    self._oww_model.reset()
                    return
        except Exception:
            log.exception("wake word inference error")

    def _check_vad(self, pcm_30ms: bytes) -> None:
        """Run Silero VAD inference on a 30 ms frame. Updates state machine."""
        if self._vad_session is None:
            return

        try:
            import numpy as np

            samples = (
                np.frombuffer(pcm_30ms, dtype=np.int16).astype(np.float32) / 32768.0
            )
            samples = samples.reshape(1, -1)

            # Silero VAD ONNX: input, sr, h, c → output, hn, cn
            ort_inputs = {
                "input": samples,
                "sr": np.array([SAMPLE_RATE], dtype=np.int64),
                "h": self._vad_h,
                "c": self._vad_c,
            }
            ort_outputs = self._vad_session.run(None, ort_inputs)
            speech_prob = ort_outputs[0].item()
            self._vad_h = ort_outputs[1]
            self._vad_c = ort_outputs[2]

            now = time.monotonic()
            is_speech = speech_prob > 0.5

            if is_speech:
                if not self._speech_detected:
                    self._speech_detected = True
                    self._speech_start_mono = now
                    log.debug("VAD: speech started")
                # Reset silence timer
                self._silence_start_mono = 0.0
            else:
                if self._speech_detected and self._silence_start_mono == 0.0:
                    self._silence_start_mono = now
                    log.debug("VAD: silence started after speech")

            # Check for end-of-utterance: enough speech followed by enough silence
            if self._speech_detected and self._silence_start_mono > 0.0:
                speech_dur_ms = (
                    self._silence_start_mono - self._speech_start_mono
                ) * 1000
                silence_dur_ms = (now - self._silence_start_mono) * 1000

                if (
                    speech_dur_ms >= self._vad_min_speech_ms
                    and silence_dur_ms >= self._vad_silence_ms
                ):
                    log.info(
                        "end-of-utterance: speech=%.0fms silence=%.0fms",
                        speech_dur_ms,
                        silence_dur_ms,
                    )
                    self.send(
                        EAR_EVENT_END_OF_UTTERANCE,
                        {
                            "speech_ms": round(speech_dur_ms),
                            "silence_ms": round(silence_dur_ms),
                        },
                    )
                    self._reset_vad_state()

        except Exception:
            log.exception("VAD inference error")

    # ── Mic socket (Mode A) ───────────────────────────────────────

    def _forward_to_mic_socket(self, pcm_chunk: bytes) -> None:
        """Forward a PCM chunk to the AI worker via the rb-mic socket."""
        if not self._mic_sock:
            return
        try:
            frame = struct.pack("<H", len(pcm_chunk)) + pcm_chunk
            self._mic_sock.sendall(frame)
        except (BrokenPipeError, OSError):
            log.warning("mic socket write failed, disconnecting")
            self._close_mic_socket()

    async def _connect_mic_socket(self) -> None:
        """Connect to the rb-mic Unix domain socket (retry loop)."""
        path = self._mic_socket_path
        if not path:
            return

        t0 = time.monotonic()
        while self.running and (time.monotonic() - t0) < _SOCKET_RETRY_TIMEOUT_S:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(path)
                sock.setblocking(False)
                self._mic_sock = sock
                self.send(SYSTEM_AUDIO_LINK_UP, {"socket": "mic"})
                log.info("connected to mic socket: %s", path)
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                await asyncio.sleep(_SOCKET_RETRY_INTERVAL_S)

        log.error("failed to connect mic socket after %.0fs", _SOCKET_RETRY_TIMEOUT_S)

    def _close_mic_socket(self) -> None:
        if self._mic_sock:
            try:
                self._mic_sock.close()
            except OSError:
                pass
            self._mic_sock = None
            self.send(
                SYSTEM_AUDIO_LINK_DOWN, {"socket": "mic", "reason": "write_error"}
            )

    # ── arecord lifecycle ─────────────────────────────────────────

    async def _kill_arecord(self) -> None:
        if self._arecord_proc:
            try:
                self._arecord_proc.kill()
                await self._arecord_proc.wait()
            except Exception:
                pass
            self._arecord_proc = None


if __name__ == "__main__":
    worker_main(EarWorker)
