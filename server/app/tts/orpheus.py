"""Orpheus TTS integration — emotional text-to-speech with prosody tags.

Orpheus TTS is a 3B-parameter model that supports emotion tags like <happy>,
<sad>, <surprised>, etc. embedded directly in the input text. It produces
expressive, natural-sounding speech with emotional prosody.

Audio output: 24 kHz, mono, float32 → resampled to 16 kHz 16-bit PCM for
the robot's speaker.
"""

from __future__ import annotations

import audioop
import io
import logging
import os
import queue
import shutil
import struct
import subprocess
import threading
import time
import uuid
import wave
from collections.abc import AsyncIterator
from typing import Any, Callable, Iterator

from app.config import settings

log = logging.getLogger(__name__)

# Map robot emotion names → Orpheus prosody tags
EMOTION_TO_PROSODY_TAG: dict[str, str] = {
    "neutral": "",
    "happy": "<happy>",
    "excited": "<excited>",
    "curious": "",
    "sad": "<sad>",
    "scared": "<scared>",
    "angry": "<angry>",
    "surprised": "<surprised>",
    "sleepy": "<yawn>",
    "love": "<happy>",
    "silly": "<laughing>",
    "thinking": "",
}

# Output PCM format for the robot
OUTPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_WIDTH = 2  # 16-bit signed
OUTPUT_CHANNELS = 1
CHUNK_SAMPLES = 160  # 10ms chunks at 16 kHz
ORPHEUS_IDLE_TIMEOUT_S = settings.orpheus_idle_timeout_s
ORPHEUS_TOTAL_TIMEOUT_S = settings.orpheus_total_timeout_s


def apply_prosody_tag(emotion: str, text: str) -> str:
    """Prepend the Orpheus emotion tag to the text."""
    tag = EMOTION_TO_PROSODY_TAG.get(emotion, "")
    if tag:
        return f"{tag} {text}"
    return text


def pcm_float32_to_int16(float_audio: bytes, *, src_rate: int = 24000) -> bytes:
    """Convert float32 audio to 16-bit signed PCM, with optional resampling.

    Simple linear resampling from src_rate to 16 kHz. For production quality,
    use a proper resampler (e.g. scipy.signal.resample_poly).
    """
    n_samples = len(float_audio) // 4
    float_samples = struct.unpack(f"<{n_samples}f", float_audio)

    # Resample if needed
    if src_rate != OUTPUT_SAMPLE_RATE:
        ratio = OUTPUT_SAMPLE_RATE / src_rate
        out_len = int(n_samples * ratio)
        resampled = []
        for i in range(out_len):
            src_idx = i / ratio
            idx = int(src_idx)
            if idx >= n_samples - 1:
                resampled.append(float_samples[-1])
            else:
                frac = src_idx - idx
                resampled.append(
                    float_samples[idx] * (1 - frac) + float_samples[idx + 1] * frac
                )
        float_samples = resampled

    # Convert to 16-bit signed
    int16_samples = []
    for s in float_samples:
        clamped = max(-1.0, min(1.0, s))
        int16_samples.append(int(clamped * 32767))

    return struct.pack(f"<{len(int16_samples)}h", *int16_samples)


def pcm_int16_resample_to_int16(pcm_audio: bytes, *, src_rate: int = 24000) -> bytes:
    """Resample int16 PCM bytes from src_rate to OUTPUT_SAMPLE_RATE."""
    if src_rate == OUTPUT_SAMPLE_RATE:
        return pcm_audio
    if len(pcm_audio) < 2:
        return b""

    n_samples = len(pcm_audio) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_audio[: n_samples * 2])
    ratio = OUTPUT_SAMPLE_RATE / src_rate
    out_len = int(n_samples * ratio)
    out: list[int] = []
    for i in range(out_len):
        src_idx = i / ratio
        idx = int(src_idx)
        if idx >= n_samples - 1:
            out.append(samples[-1])
        else:
            frac = src_idx - idx
            v = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
            out.append(int(v))
    return struct.pack(f"<{len(out)}h", *out)


class OrpheusTTS:
    """Text-to-speech using Orpheus TTS with emotion prosody.

    The model is loaded lazily on first synthesis call.
    """

    def __init__(
        self,
        model_name: str = settings.tts_model_name,
        device: str = "cuda",
        backend: str = settings.tts_backend,
        voice: str = settings.tts_voice,
        rate_wpm: int = settings.tts_rate_wpm,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._backend_pref = str(backend or "auto").strip().lower()
        self._voice = str(voice or "en-us")
        self._rate_wpm = int(rate_wpm)
        self._loaded = False
        self._backend: str | None = None
        self._legacy_generate_speech: Callable[[str], bytes] | None = None
        self._model: Any = None
        self._init_error: str | None = None
        self._espeak_bin: str | None = None

    @staticmethod
    def _hf_token_present() -> bool:
        return bool(
            os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        )

    def _enable_espeak_fallback(self, *, force: bool = False) -> bool:
        if not force and self._backend_pref not in {"auto", "espeak"}:
            return False
        espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak is None:
            return False
        self._espeak_bin = espeak
        self._backend = "espeak"
        self._loaded = True
        self._init_error = None
        log.warning("Using espeak fallback TTS backend (%s)", espeak)
        return True

    def _ensure_model(self) -> None:
        if self._loaded:
            return

        if self._backend_pref == "off":
            self._backend = "off"
            self._init_error = "tts_disabled"
            self._loaded = True
            log.info("TTS backend disabled via TTS_BACKEND=off")
            return

        if self._backend_pref == "espeak":
            if self._enable_espeak_fallback(force=True):
                return
            self._init_error = "espeak_not_available"
            self._loaded = True
            log.warning("TTS_BACKEND=espeak but espeak-ng/espeak is not installed")
            return

        if self._backend_pref not in {"auto", "orpheus"}:
            log.warning("Unknown TTS_BACKEND=%r; defaulting to auto", self._backend_pref)
            self._backend_pref = "auto"

        log.info("Loading Orpheus TTS model %s on %s...", self._model_name, self._device)

        # Backend A: legacy runtime exposing `orpheus_speech.generate_speech`.
        try:
            from orpheus_speech import generate_speech  # type: ignore[import-not-found]

            self._legacy_generate_speech = generate_speech
            self._backend = "orpheus_speech"
            self._loaded = True
            log.info("Orpheus TTS backend loaded via orpheus_speech.")
            return
        except ImportError:
            pass

        # Backend B: current PyPI package exposing `orpheus_tts.OrpheusModel`.
        try:
            from orpheus_tts import OrpheusModel  # type: ignore[import-not-found]
            from vllm import AsyncEngineArgs, AsyncLLMEngine  # type: ignore[import-not-found]

            class _TunedOrpheusModel(OrpheusModel):
                def _setup_engine(self):
                    engine_args = AsyncEngineArgs(
                        model=self.model_name,
                        dtype=self.dtype,
                        gpu_memory_utilization=settings.orpheus_gpu_memory_utilization,
                        max_model_len=settings.orpheus_max_model_len,
                        max_num_seqs=settings.orpheus_max_num_seqs,
                        max_num_batched_tokens=settings.orpheus_max_num_batched_tokens,
                    )
                    return AsyncLLMEngine.from_engine_args(engine_args)

            model_candidates = [
                self._model_name,
                "canopylabs/orpheus-tts-0.1-finetune-prod",
            ]
            last_err: Exception | None = None
            tried: set[str] = set()
            for name in model_candidates:
                if name in tried:
                    continue
                tried.add(name)
                try:
                    self._model = _TunedOrpheusModel(name)
                    self._backend = "orpheus_tts"
                    self._loaded = True
                    log.info(
                        (
                            "Orpheus TTS backend loaded via orpheus_tts "
                            "(%s, gpu_mem=%.2f, max_len=%d, max_num_seqs=%d, max_batched_tokens=%d)."
                        ),
                        name,
                        settings.orpheus_gpu_memory_utilization,
                        settings.orpheus_max_model_len,
                        settings.orpheus_max_num_seqs,
                        settings.orpheus_max_num_batched_tokens,
                    )
                    return
                except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                    last_err = exc
                    log.warning("Orpheus model init failed for %s: %s", name, exc)
            if last_err is not None:
                raise last_err
        except ImportError:
            log.warning(
                "Orpheus TTS runtime not available. "
                "Install/launch with: `uv sync --extra tts` and "
                "`uv run --extra tts python -m app.main`."
            )
        except Exception:
            log.exception("Failed to initialize Orpheus TTS runtime")
            self._init_error = "failed_to_initialize_orpheus_runtime"

        if self._backend_pref == "auto" and self._enable_espeak_fallback():
            return

        # Don't retry on every request if runtime is unavailable.
        self._loaded = True

    def _reset_orpheus_backend(self) -> None:
        """Drop backend state so a dead engine can be recreated."""
        self._loaded = False
        self._backend = None
        self._legacy_generate_speech = None
        self._model = None
        self._init_error = None

    def _collect_chunks_with_timeout(self, gen: Iterator[bytes]) -> bytes:
        """Drain an Orpheus generator safely with idle/total timeouts."""
        q: queue.Queue[tuple[str, bytes | Exception | None]] = queue.Queue()

        def _run() -> None:
            try:
                for chunk in gen:
                    q.put(("chunk", bytes(chunk)))
            except Exception as exc:  # pragma: no cover - runtime dependent
                q.put(("error", exc))
            finally:
                q.put(("done", None))

        th = threading.Thread(target=_run, daemon=True)
        th.start()

        out: list[bytes] = []
        start = time.monotonic()
        last_item = start

        while True:
            now = time.monotonic()
            if (now - start) > ORPHEUS_TOTAL_TIMEOUT_S:
                raise TimeoutError(
                    f"orpheus stream exceeded total timeout ({ORPHEUS_TOTAL_TIMEOUT_S}s)"
                )

            wait_s = min(
                ORPHEUS_IDLE_TIMEOUT_S,
                max(0.1, ORPHEUS_TOTAL_TIMEOUT_S - (now - start)),
            )
            try:
                kind, payload = q.get(timeout=wait_s)
            except queue.Empty:
                idle = time.monotonic() - last_item
                raise TimeoutError(
                    f"orpheus stream idle for {idle:.1f}s "
                    f"(limit {ORPHEUS_IDLE_TIMEOUT_S}s)"
                ) from None

            last_item = time.monotonic()
            if kind == "chunk":
                assert isinstance(payload, (bytes, bytearray))
                if payload:
                    out.append(bytes(payload))
            elif kind == "error":
                assert isinstance(payload, Exception)
                raise payload
            elif kind == "done":
                break

        return b"".join(out)

    @staticmethod
    def _wav_to_pcm16_16k(wav_bytes: bytes) -> bytes:
        if not wav_bytes:
            return b""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        pcm = frames
        if sample_width != 2:
            pcm = audioop.lin2lin(pcm, sample_width, 2)
        if n_channels != 1:
            pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
        if sample_rate != OUTPUT_SAMPLE_RATE:
            pcm, _ = audioop.ratecv(pcm, 2, 1, sample_rate, OUTPUT_SAMPLE_RATE, None)
        return pcm

    def _synthesize_with_espeak(self, text: str) -> bytes:
        exe = self._espeak_bin or shutil.which("espeak-ng") or shutil.which("espeak")
        if exe is None:
            self._init_error = "espeak_not_available"
            return b""
        cmd = [
            exe,
            "-v",
            self._voice,
            "-s",
            str(self._rate_wpm),
            "--stdout",
            text,
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
        except Exception as exc:
            log.warning("espeak synthesis failed: %s", exc)
            self._init_error = "espeak_exec_failed"
            return b""

        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore").strip()
            log.warning("espeak exited with code %s: %s", proc.returncode, err[:200])
            self._init_error = "espeak_nonzero_exit"
            return b""

        return self._wav_to_pcm16_16k(proc.stdout)

    async def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """Synthesize speech from text with emotional prosody.

        Returns complete PCM audio (16-bit, 16 kHz, mono).
        """
        import asyncio

        return await asyncio.to_thread(self._synthesize_sync, text, emotion)

    def _synthesize_sync(self, text: str, emotion: str) -> bytes:
        """Synchronous synthesis."""
        self._ensure_model()
        tagged_text = apply_prosody_tag(emotion, text)

        if self._backend == "off":
            return b""
        if self._backend == "espeak":
            return self._synthesize_with_espeak(text)

        for attempt in (1, 2):
            try:
                if self._backend == "orpheus_speech" and self._legacy_generate_speech is not None:
                    audio_float32 = self._legacy_generate_speech(tagged_text)
                    return pcm_float32_to_int16(audio_float32, src_rate=24000)

                if self._backend == "orpheus_tts" and self._model is not None:
                    # orpheus_tts currently yields int16 PCM chunks at 24 kHz.
                    req_id = f"req-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"
                    gen = self._model.generate_speech(prompt=tagged_text, request_id=req_id)
                    audio_int16_24k = self._collect_chunks_with_timeout(gen)
                    if not audio_int16_24k:
                        return b""
                    return pcm_int16_resample_to_int16(audio_int16_24k, src_rate=24000)

                if self._init_error is None:
                    self._init_error = "orpheus_backend_unavailable"
                log.warning(
                    "TTS unavailable (%s). hf_token_present=%s. If using gated HF models, ensure "
                    "Hugging Face login + accepted model access.",
                    self._init_error,
                    self._hf_token_present(),
                )
                return b""
            except Exception as exc:
                if self._backend == "orpheus_tts" and attempt == 1:
                    log.warning("Orpheus synthesis failed; resetting engine and retrying once: %s", exc)
                    self._reset_orpheus_backend()
                    self._ensure_model()
                    continue
                if self._backend_pref == "auto" and self._enable_espeak_fallback():
                    log.warning("Falling back to espeak after Orpheus failure")
                    return self._synthesize_with_espeak(text)
                log.exception("TTS synthesis failed for: %s", tagged_text[:80])
                return b""

        return b""

    async def stream(self, text: str, emotion: str = "neutral") -> AsyncIterator[bytes]:
        """Stream PCM audio chunks as they're generated.

        Yields 10ms chunks of 16-bit 16 kHz mono PCM.
        Falls back to synthesize-then-chunk if streaming isn't supported.
        """
        # For now, synthesize full audio then yield in chunks.
        # True streaming requires deeper Orpheus integration.
        audio = await self.synthesize(text, emotion)

        chunk_bytes = CHUNK_SAMPLES * OUTPUT_SAMPLE_WIDTH
        offset = 0
        while offset < len(audio):
            yield audio[offset : offset + chunk_bytes]
            offset += chunk_bytes

    def debug_snapshot(self) -> dict:
        return {
            "backend_pref": self._backend_pref,
            "backend_active": self._backend,
            "model_name": self._model_name,
            "device": self._device,
            "loaded": self._loaded,
            "init_error": self._init_error,
            "hf_token_present": self._hf_token_present(),
            "espeak_available": bool(
                self._espeak_bin or shutil.which("espeak-ng") or shutil.which("espeak")
            ),
        }
