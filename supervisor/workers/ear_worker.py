"""Ear worker — always-on microphone with wake word detection + VAD.

Owns the microphone (arecord). Continuously runs OpenWakeWord inference
to detect "Hey Buddy".  During active conversations, forwards PCM to the
AI worker via the rb-mic Unix socket and runs Silero VAD to detect
end-of-utterance silence.

arecord is supervised: if it exits (USB replug, card renumbered) the worker
re-resolves the device and restarts it. With the reSpeaker Flex it also owns
the board's USB control: voice direction, and the chip settings written each
time the board is opened (never saved to its flash).
"""

from __future__ import annotations

import asyncio
import logging
import math
import socket
import struct
import time
from array import array
from pathlib import Path
from typing import Any

from supervisor.audio.format import (
    CHANNELS,
    CHUNK_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    SOCKET_RETRY_INTERVAL_S,
    SOCKET_RETRY_TIMEOUT_S,
)
from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    EAR_CMD_PAUSE_VAD,
    EAR_CMD_RESUME_VAD,
    EAR_CMD_SET_MIC_CHANNEL,
    EAR_CMD_SET_THRESHOLD,
    EAR_CMD_START_LISTENING,
    EAR_CMD_STOP_LISTENING,
    EAR_CMD_STREAM_SCORES,
    EAR_CMD_XVF_SET,
    EAR_CONFIG_INIT,
    EAR_EVENT_DOA,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_OWW_SCORE,
    EAR_EVENT_WAKE_WORD,
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
)
from supervisor.devices.alsa_device import resolve_alsa_device
from supervisor.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

__all__ = ["CHUNK_BYTES", "SAMPLE_RATE", "EarWorker", "select_channel"]

# OpenWakeWord operates on 80 ms frames
_OWW_FRAME_BYTES = int(SAMPLE_RATE * SAMPLE_WIDTH * 0.08)  # 2560

# Silero VAD operates on 30 ms frames (512 samples at 16 kHz)
_VAD_FRAME_SAMPLES = 512
_VAD_FRAME_BYTES = _VAD_FRAME_SAMPLES * SAMPLE_WIDTH  # 1024

# arecord restart backoff (USB replug, card busy)
_ARECORD_RETRY_MIN_S = 1.0
_ARECORD_RETRY_MAX_S = 5.0

# Input level window for the health payload
_LEVEL_WINDOW_S = 1.0

# Wake word cooldown — suppress re-triggers during active conversation
_WW_COOLDOWN_S = 3.0

# XVF3800 control: retry an absent / failed board this often
_XVF_RETRY_S = 5.0

_VAD_SCHEMA_DISABLED = "disabled"
_VAD_SCHEMA_STATE = "state"
_VAD_SCHEMA_HC = "hc"


def select_channel(data: bytes, channels: int, index: int) -> bytes:
    """One channel of interleaved S16_LE frames (``data`` = whole frames)."""
    if channels <= 1:
        return data
    samples = array("h")
    samples.frombytes(data)
    return samples[index::channels].tobytes()


class EarWorker(BaseWorker):
    domain = "ear"

    def __init__(self) -> None:
        super().__init__()
        # Config (from ear.config.init). _mic_spec is what was asked for
        # (e.g. match:reSpeaker); _mic_device is what it resolved to last.
        self._mic_spec: str = "default"
        self._mic_device: str = "default"
        # Multi-channel capture (reSpeaker Flex: 6 ch, ch 0 = processed ASR
        # beam). Everything downstream stays 16 kHz mono.
        self._mic_channels: int = CHANNELS
        self._mic_channel: int = 0
        self._capture_rem = bytearray()
        # XVF3800 voice direction (USB control). Off unless configured.
        self._xvf_enabled = False
        self._doa_poll_hz = 10.0
        self._doa_offset_deg = 0.0
        self._doa_sign = 1
        self._xvf: Any = None
        self._xvf_status = "off"  # off | ok | error
        self._xvf_version = ""
        self._doa_last_speech = False
        self._doa_last: dict[str, Any] | None = None
        self._xvf_settings: dict[str, Any] = {}
        self._xvf_applied: list[str] = []
        # Capture supervision + input level (selected channel)
        self._arecord_restarts = 0
        self._level_sumsq = 0.0
        self._level_n = 0
        self._level_t0 = 0.0
        self._input_rms_dbfs: float | None = None
        self._mic_socket_path: str = ""
        self._wakeword_model_path: str = ""
        self._wakeword_threshold: float = 0.5
        # VAD end-of-utterance knobs. Empirically (2026-04-18 session),
        # Silero v5 only spikes above 0.5 briefly for short/quick phrases,
        # so a 0.5 prob gate + 300 ms min_speech blocks EoU from ever
        # firing. Loosened defaults catch normal speech; override via
        # EAR_CONFIG_INIT payload (see on_message EAR_CONFIG_INIT handler).
        self._vad_silence_ms: int = 800
        self._vad_min_speech_ms: int = 150
        self._vad_speech_prob_threshold: float = 0.3
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
        # Silero v5 requires a 64-sample (at 16kHz) context buffer prepended
        # to each 512-sample frame. Without it the model silently returns
        # near-constant ~0.0005 probability regardless of input.
        self._vad_context: Any = None  # np.ndarray shape (1, 64), reset on listen start

        # Buffers
        self._ww_buffer = bytearray()
        self._vad_buffer = bytearray()

        # VAD state machine
        self._speech_detected = False
        self._speech_start_mono: float = 0.0
        self._silence_start_mono: float = 0.0

        # VAD diagnostics — periodic dump of recent max prob while listening.
        self._vad_diag_max_prob: float = 0.0
        self._vad_diag_max_amp: float = 0.0
        self._vad_diag_max_amp_oww: float = 0.0
        self._vad_diag_next_log_mono: float = 0.0

        # OWW always-on diag — fires even when not listening, so we can see
        # whether audio is reaching OWW and what max score it's producing.
        self._oww_diag_max_score: float = 0.0
        self._oww_diag_next_log_mono: float = 0.0

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
            self._mic_spec = str(p.get("mic_device", "default"))
            self._mic_device = self._mic_spec
            self._mic_channels = max(1, int(p.get("mic_channels", CHANNELS)))
            self._mic_channel = min(
                max(0, int(p.get("mic_channel", 0))), self._mic_channels - 1
            )
            xvf = p.get("xvf") or {}
            self._xvf_enabled = bool(xvf.get("enabled", False))
            self._doa_poll_hz = max(1.0, min(50.0, float(xvf.get("poll_hz", 10.0))))
            self._doa_offset_deg = float(xvf.get("doa_offset_deg", 0.0))
            self._doa_sign = -1 if int(xvf.get("doa_sign", 1)) < 0 else 1
            self._xvf_settings = self._valid_xvf_settings(xvf.get("settings") or {})
            self._mic_socket_path = str(p.get("mic_socket_path", ""))
            self._wakeword_model_path = str(p.get("wakeword_model_path", ""))
            self._wakeword_threshold = float(p.get("wakeword_threshold", 0.5))
            self._vad_silence_ms = int(p.get("vad_silence_ms", 800))
            self._vad_min_speech_ms = int(p.get("vad_min_speech_ms", 150))
            self._vad_speech_prob_threshold = float(
                p.get("vad_speech_prob_threshold", 0.3)
            )
            log.info(
                "configured: mic=%s (ch %d of %d), xvf=%s, ww_model=%s, threshold=%.2f",
                self._mic_device,
                self._mic_channel,
                self._mic_channels,
                "on" if self._xvf_enabled else "off",
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
            self._vad_buffer.clear()

        elif t == EAR_CMD_RESUME_VAD:
            self._vad_paused = False
            self._vad_buffer.clear()

        elif t == EAR_CMD_SET_MIC_CHANNEL:
            ch = min(max(0, int(p.get("channel", 0))), self._mic_channels - 1)
            if ch != self._mic_channel:
                self._mic_channel = ch
                self._reset_level()
                log.info("mic channel: %d of %d", ch, self._mic_channels)

        elif t == EAR_CMD_XVF_SET:
            new = self._valid_xvf_settings(p.get("settings") or {})
            if new:
                self._xvf_settings.update(new)
                if self._xvf is not None:
                    asyncio.create_task(self._apply_xvf_settings(new))

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
        self._vad_diag_max_prob = 0.0
        self._vad_diag_max_amp = 0.0
        self._vad_diag_max_amp_oww = 0.0
        self._vad_diag_next_log_mono = time.monotonic() + 1.5
        # Connect mic socket if not yet connected
        if not self._mic_sock and self._mic_socket_path:
            asyncio.create_task(self._connect_mic_socket())
        log.info("listening started")

    def _stop_listening(self) -> None:
        """Stop forwarding mic audio. Idempotent — multiple cleanup paths
        (EoU handler, AI_CONVERSATION_DONE, TTS_EVENT_FINISHED) all send
        EAR_CMD_STOP_LISTENING around the same time; only log the first
        actual transition."""
        was_listening = self._listening
        self._listening = False
        self._vad_paused = False
        self._reset_vad_state()
        self._vad_buffer.clear()
        if was_listening:
            log.info("listening stopped")

    def _reset_vad_state(self) -> None:
        self._speech_detected = False
        self._speech_start_mono = 0.0
        self._silence_start_mono = 0.0
        # Reset Silero hidden state
        if self._vad_session is not None:
            import numpy as np

            # Silero v5 at 16kHz: 64-sample context prepended to each frame.
            self._vad_context = np.zeros((1, 64), dtype=np.float32)
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
            "mic_device": self._mic_device,
            "mic_channel": self._mic_channel,
            "mic_channels": self._mic_channels,
            "mic_running": self._arecord_proc is not None,
            "arecord_restarts": self._arecord_restarts,
            "input_rms_dbfs": self._input_rms_dbfs,
            "xvf": self._xvf_status,
            "xvf_version": self._xvf_version,
            "xvf_settings": self._xvf_settings,
            "xvf_applied": self._xvf_applied,
            "doa": self._doa_last,
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

        doa_task = asyncio.create_task(self._doa_loop()) if self._xvf_enabled else None
        try:
            await self._capture_supervisor()
        except asyncio.CancelledError:
            pass
        finally:
            if doa_task:
                doa_task.cancel()
            self._close_xvf()
            await self._kill_arecord()

    async def _capture_supervisor(self) -> None:
        """Run arecord; when it exits, re-resolve the card and start it again."""
        backoff = _ARECORD_RETRY_MIN_S
        while self.running:
            started = await self._start_arecord()
            if started:
                t0 = time.monotonic()
                await self._capture_loop()
                await self._kill_arecord()
                if time.monotonic() - t0 > 10.0:
                    backoff = _ARECORD_RETRY_MIN_S  # it ran fine for a while
            if not self.running:
                break
            self._arecord_restarts += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _ARECORD_RETRY_MAX_S)

    async def _start_arecord(self) -> bool:
        resolved = resolve_alsa_device(self._mic_spec)
        if resolved is None:
            if self._arecord_restarts == 0:
                log.warning("no ALSA card matches %r, using 'default'", self._mic_spec)
            resolved = "default"
        self._mic_device = resolved
        self._reset_capture_buffers()
        try:
            self._arecord_proc = await self._spawn_arecord(resolved)
        except OSError as e:
            log.warning("cannot start arecord: %s", e)
            self._arecord_proc = None
            return False
        log.info("arecord started (device=%s, %d ch)", resolved, self._mic_channels)
        self.send(SYSTEM_AUDIO_LINK_UP, {"socket": "mic"})
        return True

    async def _spawn_arecord(self, device: str) -> Any:
        return await asyncio.create_subprocess_exec(
            "arecord",
            "-D",
            device,
            "-r",
            str(SAMPLE_RATE),
            "-f",
            "S16_LE",
            "-c",
            str(self._mic_channels),
            "-t",
            "raw",
            "-q",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

    def _reset_capture_buffers(self) -> None:
        self._capture_rem.clear()
        self._ww_buffer.clear()
        self._vad_buffer.clear()
        self._reset_vad_state()
        self._reset_level()

    def _reset_level(self) -> None:
        self._level_sumsq = 0.0
        self._level_n = 0
        self._level_t0 = time.monotonic()

    def _update_level(self, mono: bytes) -> None:
        """Track the selected channel's RMS over a 1 s window (health)."""
        samples = array("h")
        samples.frombytes(mono[: len(mono) - len(mono) % 2])
        self._level_sumsq += float(sum(x * x for x in samples))
        self._level_n += len(samples)
        now = time.monotonic()
        if now - self._level_t0 >= _LEVEL_WINDOW_S and self._level_n:
            rms = math.sqrt(self._level_sumsq / self._level_n)
            self._input_rms_dbfs = (
                round(20 * math.log10(rms / 32768.0), 1) if rms > 0 else -120.0
            )
            self._level_sumsq = 0.0
            self._level_n = 0
            self._level_t0 = now

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
            data = await self._arecord_proc.stdout.read(
                CHUNK_BYTES * self._mic_channels
            )
            if not data:
                break
            if self._mic_channels > 1:
                data = self._take_channel(data)
                if not data:
                    continue
            self._update_level(data)

            # Always: accumulate for wake word detection
            self._ww_buffer.extend(data)
            if len(self._ww_buffer) >= _OWW_FRAME_BYTES:
                frame = bytes(self._ww_buffer[:_OWW_FRAME_BYTES])
                del self._ww_buffer[:_OWW_FRAME_BYTES]
                await self._check_wake_word(frame)

            # During conversation: forward audio and run VAD
            if self._listening:
                await self._forward_to_mic_socket(data)

                if not self._vad_paused:
                    self._vad_buffer.extend(data)
                    while len(self._vad_buffer) >= _VAD_FRAME_BYTES:
                        vad_frame = bytes(self._vad_buffer[:_VAD_FRAME_BYTES])
                        del self._vad_buffer[:_VAD_FRAME_BYTES]
                        self._check_vad(vad_frame)

    def _take_channel(self, data: bytes) -> bytes:
        """Keep whole interleaved frames (reads can split one) and return the
        configured channel as mono."""
        frame = SAMPLE_WIDTH * self._mic_channels
        self._capture_rem.extend(data)
        n = len(self._capture_rem) - len(self._capture_rem) % frame
        if n == 0:
            return b""
        whole = bytes(self._capture_rem[:n])
        del self._capture_rem[:n]
        return select_channel(whole, self._mic_channels, self._mic_channel)

    # ── XVF3800 voice direction ───────────────────────────────────

    async def _doa_loop(self) -> None:
        """Poll the XVF3800's direction of arrival + speech energy over USB
        control and publish ear.event.doa while someone is talking."""
        from supervisor.devices.xvf3800 import Xvf3800

        period = 1.0 / self._doa_poll_hz
        while self.running:
            if self._xvf is None:
                try:
                    self._xvf = await asyncio.to_thread(Xvf3800.open_usb)
                    self._xvf_version = await asyncio.to_thread(self._xvf.version)
                    self._xvf_status = "ok"
                    log.info("XVF3800 control open (firmware %s)", self._xvf_version)
                    self._xvf_applied = []
                    if self._xvf_settings:
                        await self._apply_xvf_settings(dict(self._xvf_settings))
                except Exception as e:
                    if self._xvf_status != "error":
                        log.warning("XVF3800 control unavailable: %s", e)
                    self._close_xvf()
                    self._xvf_status = "error"
                    await asyncio.sleep(_XVF_RETRY_S)
                    continue
            try:
                vd = await asyncio.to_thread(self._xvf.voice_direction)
            except Exception as e:
                log.warning("XVF3800 read failed: %s", e)
                self._close_xvf()
                self._xvf_status = "error"
                await asyncio.sleep(1.0)
                continue
            self._handle_voice_direction(vd)
            await asyncio.sleep(period)

    def _handle_voice_direction(self, vd: Any) -> None:
        from supervisor.devices.xvf3800 import signed_deg, to_robot_deg

        if vd.speech and vd.azimuth_deg is not None and not math.isnan(vd.azimuth_deg):
            az = to_robot_deg(vd.azimuth_deg, self._doa_offset_deg, self._doa_sign)
            payload = {
                "speech": True,
                "azimuth_deg": round(signed_deg(az), 1),  # robot frame, + = left
                "energy": float(vd.energy),
                "beam_energy": [float(x) for x in vd.beam_energy],
            }
            self.send(EAR_EVENT_DOA, payload)
            self._doa_last = payload
            self._doa_last_speech = True
        elif self._doa_last_speech:
            self.send(EAR_EVENT_DOA, {"speech": False})
            self._doa_last_speech = False

    @staticmethod
    def _valid_xvf_settings(raw: dict[str, Any]) -> dict[str, Any]:
        from supervisor.devices.xvf3800 import TUNABLE

        good: dict[str, Any] = {}
        for name, value in raw.items():
            if name in TUNABLE:
                good[name] = value
            else:
                log.warning("ignoring XVF setting %s (not tunable)", name)
        return good

    async def _apply_xvf_settings(self, settings: dict[str, Any]) -> None:
        xvf = self._xvf
        if xvf is None:
            return
        try:
            done = await asyncio.to_thread(xvf.apply_settings, settings)
        except Exception as e:
            log.warning("XVF3800 settings failed: %s", e)
            return
        self._xvf_applied = sorted(set(self._xvf_applied) | set(done))
        log.info("XVF3800 settings applied: %s", settings)

    def _close_xvf(self) -> None:
        if self._xvf is not None:
            try:
                self._xvf.close()
            except Exception:
                pass
            self._xvf = None

    async def _check_wake_word(self, pcm_80ms: bytes) -> None:
        """Run OpenWakeWord inference on an 80 ms frame."""
        if self._oww_model is None:
            return

        try:
            import numpy as np

            # OWW expects int16 samples
            samples = np.frombuffer(pcm_80ms, dtype=np.int16)

            # Diagnostic: track peak amplitude on the OWW path for direct
            # comparison with the VAD path, since both should see the same
            # mic stream.
            if samples.size:
                oww_peak = float(np.abs(samples).max()) / 32768.0
                if oww_peak > self._vad_diag_max_amp_oww:
                    self._vad_diag_max_amp_oww = oww_peak

            prediction = self._oww_model.predict(samples)

            # Diagnostic: track max alexa (or any OWW) score so we can log
            # even when wake never crosses the threshold.
            if prediction:
                best = max(prediction.values()) if prediction else 0.0
                if best > self._oww_diag_max_score:
                    self._oww_diag_max_score = float(best)
            now = time.monotonic()
            if now >= self._oww_diag_next_log_mono:
                pred_dump = (
                    {k: round(float(v), 4) for k, v in prediction.items()}
                    if prediction
                    else None
                )
                log.info(
                    "OWW diag: max_score=%.3f oww_amp=%.3f listening=%s pred=%s",
                    self._oww_diag_max_score,
                    self._vad_diag_max_amp_oww,
                    self._listening,
                    pred_dump,
                )
                self._oww_diag_max_score = 0.0
                self._vad_diag_max_amp_oww = 0.0
                self._oww_diag_next_log_mono = now + 2.0

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

            # Silero v5 at 16 kHz expects 64 samples of context prepended to
            # each 512-sample frame (total 576 samples). Without this the
            # model silently returns near-constant ~0.0005 regardless of
            # input. Roll the last 64 samples of the previous frame as the
            # next context.
            if self._vad_context is None:
                self._vad_context = np.zeros((1, 64), dtype=np.float32)
            model_input = np.concatenate([self._vad_context, samples], axis=1)
            self._vad_context = samples[:, -64:].copy()

            ort_inputs: dict[str, Any] = {
                "input": model_input,
                "sr": np.array(SAMPLE_RATE, dtype=np.int64),
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
            is_speech = speech_prob > self._vad_speech_prob_threshold

            # Diagnostics: track max prob and peak sample amplitude per
            # window. amp=0 → VAD is receiving silence (input pipeline bug);
            # amp>0.1 with prob<0.1 → model sees audio but doesn't classify
            # as speech.
            if speech_prob > self._vad_diag_max_prob:
                self._vad_diag_max_prob = speech_prob
            frame_peak = float(np.abs(samples).max()) if samples.size else 0.0
            if frame_peak > self._vad_diag_max_amp:
                self._vad_diag_max_amp = frame_peak
            if now >= self._vad_diag_next_log_mono:
                log.info(
                    "VAD diag: max_prob=%.3f vad_amp=%.3f oww_amp=%.3f speech_detected=%s silence_start=%.1f",
                    self._vad_diag_max_prob,
                    self._vad_diag_max_amp,
                    self._vad_diag_max_amp_oww,
                    self._speech_detected,
                    self._silence_start_mono,
                )
                self._vad_diag_max_prob = 0.0
                self._vad_diag_max_amp = 0.0
                self._vad_diag_max_amp_oww = 0.0
                self._vad_diag_next_log_mono = now + 1.5

            if is_speech:
                if not self._speech_detected:
                    self._speech_detected = True
                    self._speech_start_mono = now
                    log.info("VAD: speech started (prob=%.3f)", speech_prob)
                # Reset silence timer
                self._silence_start_mono = 0.0
            else:
                if self._speech_detected and self._silence_start_mono == 0.0:
                    self._silence_start_mono = now
                    log.info("VAD: silence started after speech")

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

    async def _forward_to_mic_socket(self, pcm_chunk: bytes) -> None:
        """Forward a PCM chunk to the AI worker via the rb-mic socket.

        Uses ``loop.sock_sendall`` because the socket is non-blocking; the
        blocking ``socket.sendall`` raises ``BlockingIOError`` (an OSError
        subclass) whenever the send buffer fills before the AI worker drains,
        which causes the mic link to bounce even during healthy listening.
        """
        if not self._mic_sock:
            return
        try:
            frame = struct.pack("<H", len(pcm_chunk)) + pcm_chunk
            loop = asyncio.get_running_loop()
            await loop.sock_sendall(self._mic_sock, frame)
        except (BrokenPipeError, ConnectionError, OSError):
            log.warning("mic socket write failed, disconnecting")
            self._close_mic_socket()

    async def _connect_mic_socket(self) -> None:
        """Connect to the rb-mic Unix domain socket (retry loop)."""
        path = self._mic_socket_path
        if not path:
            return

        t0 = time.monotonic()
        while self.running and (time.monotonic() - t0) < SOCKET_RETRY_TIMEOUT_S:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(path)
                sock.setblocking(False)
                self._mic_sock = sock
                log.info("connected to mic socket: %s", path)
                return
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                await asyncio.sleep(SOCKET_RETRY_INTERVAL_S)

        log.error("failed to connect mic socket after %.0fs", SOCKET_RETRY_TIMEOUT_S)

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
