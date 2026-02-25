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
    EAR_CMD_SET_THRESHOLD,
    EAR_CMD_START_LISTENING,
    EAR_CMD_STOP_LISTENING,
    EAR_CMD_STREAM_SCORES,
    EAR_CONFIG_INIT,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_OWW_SCORE,
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

_VAD_SCHEMA_DISABLED = "disabled"
_VAD_SCHEMA_STATE = "state"
_VAD_SCHEMA_HC = "hc"


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
        self._vad_schema: str = _VAD_SCHEMA_DISABLED
        self._vad_state: Any = None  # Silero combined recurrent state
        self._vad_state_shape: tuple[int, int, int] = (2, 1, 128)
        self._vad_h: Any = None  # Silero VAD hidden state
        self._vad_c: Any = None  # Silero VAD cell state
        self._vad_h_shape: tuple[int, int, int] = (2, 1, 64)
        self._vad_c_shape: tuple[int, int, int] = (2, 1, 64)
        self._vad_prob_output_idx: int = 0
        self._vad_state_output_idx: int | None = None
        self._vad_h_output_idx: int | None = None
        self._vad_c_output_idx: int | None = None

        # Buffers
        self._ww_buffer = bytearray()
        self._vad_buffer = bytearray()

        # VAD state machine
        self._speech_detected = False
        self._speech_start_mono: float = 0.0
        self._silence_start_mono: float = 0.0

        # Wake word timing
        self._last_ww_mono: float = 0.0
        self._stream_scores: bool = False

        # Socket + process
        self._mic_sock: socket.socket | None = None
        self._arecord_proc: asyncio.subprocess.Process | None = None

    def _reset_vad_runtime(self) -> None:
        """Disable VAD runtime and clear recurrent buffers."""
        self._vad_session = None
        self._vad_schema = _VAD_SCHEMA_DISABLED
        self._vad_state = None
        self._vad_h = None
        self._vad_c = None
        self._vad_prob_output_idx = 0
        self._vad_state_output_idx = None
        self._vad_h_output_idx = None
        self._vad_c_output_idx = None

    @staticmethod
    def _resolve_recurrent_shape(
        raw_shape: Any, fallback: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        """Resolve ONNX recurrent tensor shape with fallbacks for dynamic dims."""
        dims = list(raw_shape) if isinstance(raw_shape, (list, tuple)) else []
        out: list[int] = []
        for idx, fb in enumerate(fallback):
            val = dims[idx] if idx < len(dims) else None
            if isinstance(val, int) and val > 0:
                out.append(val)
            else:
                out.append(fb)
        return (out[0], out[1], out[2])

    @staticmethod
    def _pick_fallback_output_index(total: int, used: set[int]) -> int | None:
        for idx in range(total):
            if idx not in used:
                return idx
        return None

    def _configure_vad_schema(self) -> bool:
        """Inspect ONNX I/O and configure recurrent state handling."""
        if self._vad_session is None:
            self._reset_vad_runtime()
            return False

        import numpy as np

        inputs = list(self._vad_session.get_inputs())
        outputs = list(self._vad_session.get_outputs())
        input_names = [i.name for i in inputs]
        output_names = [o.name for o in outputs]

        self._vad_prob_output_idx = (
            output_names.index("output") if "output" in output_names else 0
        )

        if "state" in input_names:
            state_node = inputs[input_names.index("state")]
            self._vad_state_shape = self._resolve_recurrent_shape(
                getattr(state_node, "shape", None),
                (2, 1, 128),
            )

            if "stateN" in output_names:
                self._vad_state_output_idx = output_names.index("stateN")
            else:
                self._vad_state_output_idx = self._pick_fallback_output_index(
                    len(output_names), {self._vad_prob_output_idx}
                )

            if self._vad_state_output_idx is None:
                log.error(
                    "Silero VAD schema unsupported (missing state output): inputs=%s outputs=%s",
                    input_names,
                    output_names,
                )
                self._reset_vad_runtime()
                return False

            self._vad_schema = _VAD_SCHEMA_STATE
            self._vad_state = np.zeros(self._vad_state_shape, dtype=np.float32)
            self._vad_h = None
            self._vad_c = None
            self._vad_h_output_idx = None
            self._vad_c_output_idx = None
            return True

        if "h" in input_names and "c" in input_names:
            h_node = inputs[input_names.index("h")]
            c_node = inputs[input_names.index("c")]
            self._vad_h_shape = self._resolve_recurrent_shape(
                getattr(h_node, "shape", None),
                (2, 1, 64),
            )
            self._vad_c_shape = self._resolve_recurrent_shape(
                getattr(c_node, "shape", None),
                (2, 1, 64),
            )

            used = {self._vad_prob_output_idx}
            if "hn" in output_names:
                self._vad_h_output_idx = output_names.index("hn")
            else:
                self._vad_h_output_idx = self._pick_fallback_output_index(
                    len(output_names), used
                )
            if self._vad_h_output_idx is not None:
                used.add(self._vad_h_output_idx)

            if "cn" in output_names:
                self._vad_c_output_idx = output_names.index("cn")
            else:
                self._vad_c_output_idx = self._pick_fallback_output_index(
                    len(output_names), used
                )

            if self._vad_h_output_idx is None or self._vad_c_output_idx is None:
                log.error(
                    "Silero VAD schema unsupported (missing h/c outputs): inputs=%s outputs=%s",
                    input_names,
                    output_names,
                )
                self._reset_vad_runtime()
                return False

            self._vad_schema = _VAD_SCHEMA_HC
            self._vad_h = np.zeros(self._vad_h_shape, dtype=np.float32)
            self._vad_c = np.zeros(self._vad_c_shape, dtype=np.float32)
            self._vad_state = None
            self._vad_state_output_idx = None
            return True

        log.error(
            "Silero VAD schema unsupported (expected state or h/c inputs): inputs=%s outputs=%s",
            input_names,
            output_names,
        )
        self._reset_vad_runtime()
        return False

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

        elif t == EAR_CMD_STREAM_SCORES:
            self._stream_scores = bool(p.get("enabled", False))
            log.info("score streaming: %s", "on" if self._stream_scores else "off")

        elif t == EAR_CMD_SET_THRESHOLD:
            val = float(p.get("threshold", self._wakeword_threshold))
            self._wakeword_threshold = max(0.0, min(1.0, val))
            log.info("wake word threshold: %.3f", self._wakeword_threshold)

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

            if self._vad_schema == _VAD_SCHEMA_STATE:
                self._vad_state = np.zeros(self._vad_state_shape, dtype=np.float32)
            elif self._vad_schema == _VAD_SCHEMA_HC:
                self._vad_h = np.zeros(self._vad_h_shape, dtype=np.float32)
                self._vad_c = np.zeros(self._vad_c_shape, dtype=np.float32)

    def health_payload(self) -> dict[str, Any]:
        return {
            "listening": self._listening,
            "vad_paused": self._vad_paused,
            "speech_detected": self._speech_detected,
            "oww_loaded": self._oww_model is not None,
            "vad_loaded": self._vad_session is not None,
            "vad_schema": self._vad_schema,
            "wakeword_threshold": self._wakeword_threshold,
            "stream_scores": self._stream_scores,
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
        self.send(SYSTEM_AUDIO_LINK_UP, {"socket": "mic"})

        try:
            await self._capture_loop()
        except asyncio.CancelledError:
            pass
        finally:
            await self._kill_arecord()

    def _load_models(self) -> None:
        """Load OpenWakeWord and Silero VAD models (runs in thread)."""
        # ── OpenWakeWord ──────────────────────────────────────────
        ww_path = self._wakeword_model_path
        if not ww_path:
            log.warning("no wake word model configured — wake word disabled")
        elif not Path(ww_path).exists() and "/" not in ww_path and "\\" not in ww_path:
            # Treat as a built-in model name (e.g. "alexa", "hey_jarvis")
            try:
                from openwakeword.model import Model  # type: ignore[import-untyped]

                self._oww_model = Model(
                    wakeword_models=[ww_path],
                    inference_framework="onnx",
                )
                log.info("OpenWakeWord built-in model loaded by name: %s", ww_path)
            except Exception:
                log.exception("failed to load OpenWakeWord built-in model: %s", ww_path)
        elif Path(ww_path).exists():
            try:
                from openwakeword.model import Model  # type: ignore[import-untyped]

                self._oww_model = Model(
                    wakeword_models=[ww_path],
                    inference_framework="onnx",
                )
                log.info("OpenWakeWord model loaded from path: %s", ww_path)
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
                if self._configure_vad_schema():
                    log.info(
                        "Silero VAD loaded: %s (schema=%s)",
                        vad_path,
                        self._vad_schema,
                    )
            except Exception:
                log.exception("failed to load Silero VAD")
                self._reset_vad_runtime()
        else:
            log.warning("Silero VAD model not found at %s — VAD disabled", vad_path)
            self._reset_vad_runtime()

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

        try:
            import numpy as np

            # OWW expects int16 samples
            samples = np.frombuffer(pcm_80ms, dtype=np.int16)
            prediction = self._oww_model.predict(samples)

            # Stream scores to dashboard workbench (opt-in, 12.5 Hz)
            if self._stream_scores:
                self.send(
                    EAR_EVENT_OWW_SCORE,
                    {
                        "scores": {
                            k: float(round(v, 4)) for k, v in prediction.items()
                        },
                        "threshold": self._wakeword_threshold,
                    },
                )

            # Don't trigger during active conversation
            if self._listening:
                return

            now = time.monotonic()
            if now - self._last_ww_mono < _WW_COOLDOWN_S:
                return

            # Check all model scores
            for name, score in prediction.items():
                if score >= self._wakeword_threshold:
                    self._last_ww_mono = now
                    log.info("wake word detected: %s (score=%.3f)", name, score)
                    self.send(
                        EAR_EVENT_WAKE_WORD,
                        {
                            "model": name,
                            "score": float(round(score, 3)),
                        },
                    )
                    # Reset OWW internal buffers to prevent double-trigger
                    self._oww_model.reset()
                    return
        except Exception:
            log.exception("wake word inference error")

    def _check_vad(self, pcm_30ms: bytes) -> None:
        """Run Silero VAD inference on a 30 ms frame. Updates state machine."""
        if self._vad_session is None or self._vad_schema == _VAD_SCHEMA_DISABLED:
            return

        try:
            import numpy as np

            samples = (
                np.frombuffer(pcm_30ms, dtype=np.int16).astype(np.float32) / 32768.0
            )
            samples = samples.reshape(1, -1)

            ort_inputs: dict[str, Any] = {
                "input": samples,
                "sr": np.array([SAMPLE_RATE], dtype=np.int64),
            }
            if self._vad_schema == _VAD_SCHEMA_STATE:
                if self._vad_state is None:
                    self._reset_vad_state()
                ort_inputs["state"] = self._vad_state
            elif self._vad_schema == _VAD_SCHEMA_HC:
                if self._vad_h is None or self._vad_c is None:
                    self._reset_vad_state()
                ort_inputs["h"] = self._vad_h
                ort_inputs["c"] = self._vad_c
            else:
                return

            ort_outputs = self._vad_session.run(None, ort_inputs)
            speech_prob = float(
                np.asarray(ort_outputs[self._vad_prob_output_idx]).reshape(-1)[0]
            )

            if self._vad_schema == _VAD_SCHEMA_STATE:
                idx = self._vad_state_output_idx
                if idx is None or idx >= len(ort_outputs):
                    raise ValueError("VAD state output missing for schema=state")
                self._vad_state = ort_outputs[idx]
            elif self._vad_schema == _VAD_SCHEMA_HC:
                h_idx = self._vad_h_output_idx
                c_idx = self._vad_c_output_idx
                if (
                    h_idx is None
                    or c_idx is None
                    or h_idx >= len(ort_outputs)
                    or c_idx >= len(ort_outputs)
                ):
                    raise ValueError("VAD h/c outputs missing for schema=hc")
                self._vad_h = ort_outputs[h_idx]
                self._vad_c = ort_outputs[c_idx]

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

    # ── arecord lifecycle ─────────────────────────────────────────

    async def _kill_arecord(self) -> None:
        if self._arecord_proc:
            self.send(
                SYSTEM_AUDIO_LINK_DOWN, {"socket": "mic", "reason": "arecord_exit"}
            )
            try:
                self._arecord_proc.kill()
                await self._arecord_proc.wait()
            except Exception:
                pass
            self._arecord_proc = None


if __name__ == "__main__":
    worker_main(EarWorker)
