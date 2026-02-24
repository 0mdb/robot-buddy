"""Orpheus TTS integration — emotional text-to-speech with prosody tags.

Orpheus TTS is a 3B-parameter model that supports emotion tags like <happy>,
<sad>, <surprised>, etc. embedded directly in the input text. It produces
expressive, natural-sounding speech with emotional prosody.

Audio output: 24 kHz, mono, float32 → resampled to 16 kHz 16-bit PCM for
the robot's speaker.
"""

from __future__ import annotations

import asyncio
import audioop
import io
import logging
import os
import queue
import shutil
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


class TTSBusyError(RuntimeError):
    """Raised when Orpheus is busy and no fallback backend is available."""


def apply_prosody_tag(emotion: str, text: str) -> str:
    """Prepend the Orpheus emotion tag to the text."""
    tag = EMOTION_TO_PROSODY_TAG.get(emotion, "")
    if tag:
        return f"{tag} {text}"
    return text


def pcm_float32_to_int16(
    float_audio: bytes,
    *,
    src_rate: int = 24000,
    max_duration_s: float = 0,
) -> bytes:
    """Convert float32 audio to 16-bit signed PCM, with optional resampling.

    Uses numpy for vectorized linear interpolation from *src_rate* to
    OUTPUT_SAMPLE_RATE (16 kHz).  When *max_duration_s* > 0 the input is
    truncated before resampling.
    """
    import numpy as np

    if len(float_audio) < 4:
        return b""

    samples = np.frombuffer(float_audio, dtype=np.float32).copy()

    # Enforce max duration at source rate
    if max_duration_s > 0:
        max_samples = int(src_rate * max_duration_s)
        if len(samples) > max_samples:
            log.warning(
                "Truncating float32 audio from %.1fs to %.1fs",
                len(samples) / src_rate,
                max_duration_s,
            )
            samples = samples[:max_samples]

    # Resample if needed
    if src_rate != OUTPUT_SAMPLE_RATE:
        n_in = len(samples)
        n_out = int(n_in * OUTPUT_SAMPLE_RATE / src_rate)
        if n_out == 0:
            return b""
        x_in = np.arange(n_in, dtype=np.float64)
        x_out = np.linspace(0, n_in - 1, n_out, dtype=np.float64)
        samples = np.interp(x_out, x_in, samples).astype(np.float32)

    # Clamp and convert to int16
    np.clip(samples, -1.0, 1.0, out=samples)
    return (samples * 32767).astype(np.int16).tobytes()


def pcm_int16_resample_to_int16(
    pcm_audio: bytes,
    *,
    src_rate: int = 24000,
    max_duration_s: float = 0,
) -> bytes:
    """Resample int16 PCM bytes from *src_rate* to OUTPUT_SAMPLE_RATE.

    Uses numpy for vectorized linear interpolation.  When *max_duration_s* > 0
    the input is truncated before resampling.
    """
    if src_rate == OUTPUT_SAMPLE_RATE and max_duration_s <= 0:
        return pcm_audio
    if len(pcm_audio) < 2:
        return b""

    import numpy as np

    samples = np.frombuffer(pcm_audio, dtype=np.int16).astype(np.float64)

    # Enforce max duration at source rate
    if max_duration_s > 0:
        max_samples = int(src_rate * max_duration_s)
        if len(samples) > max_samples:
            log.warning(
                "Truncating int16 audio from %.1fs to %.1fs",
                len(samples) / src_rate,
                max_duration_s,
            )
            samples = samples[:max_samples]

    if src_rate == OUTPUT_SAMPLE_RATE:
        return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()

    n_in = len(samples)
    n_out = int(n_in * OUTPUT_SAMPLE_RATE / src_rate)
    if n_out == 0:
        return b""

    x_in = np.arange(n_in, dtype=np.float64)
    x_out = np.linspace(0, n_in - 1, n_out, dtype=np.float64)
    resampled = np.interp(x_out, x_in, samples)
    return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()


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
        self._active_requests = 0
        self._active_lock = threading.Lock()
        self._orpheus_allowed = bool(settings.performance_mode)
        self._orpheus_policy_reason = (
            "performance_mode_enabled"
            if settings.performance_mode
            else "performance_mode_disabled"
        )

    @property
    def orpheus_allowed(self) -> bool:
        return self._orpheus_allowed

    def prefers_orpheus(self) -> bool:
        return self._backend_pref in {"auto", "orpheus"}

    @staticmethod
    def _hf_token_present() -> bool:
        return bool(
            os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        )

    @staticmethod
    def _espeak_available() -> bool:
        return bool(shutil.which("espeak-ng") or shutil.which("espeak"))

    def set_orpheus_allowed(self, allowed: bool, reason: str) -> None:
        self._orpheus_allowed = bool(allowed)
        self._orpheus_policy_reason = reason or (
            "performance_mode_enabled" if allowed else "performance_mode_disabled"
        )
        if not self._orpheus_allowed and self._backend in {
            "orpheus_speech",
            "orpheus_tts",
        }:
            self._reset_orpheus_backend()

    async def warmup(self) -> None:
        if not self.prefers_orpheus() or not self._orpheus_allowed:
            return
        try:
            await self.synthesize("Ready.", "neutral")
            log.info("TTS warm-up complete")
        except Exception as exc:
            log.warning("TTS warm-up skipped/failed: %s", exc)

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
            log.warning(
                "Unknown TTS_BACKEND=%r; defaulting to auto", self._backend_pref
            )
            self._backend_pref = "auto"

        if not self._orpheus_allowed:
            if self._enable_espeak_fallback(force=True):
                log.info(
                    "Orpheus disabled by policy (%s); using espeak fallback",
                    self._orpheus_policy_reason,
                )
                return
            self._backend = "off"
            self._init_error = f"orpheus_disabled_{self._orpheus_policy_reason}"
            self._loaded = True
            log.warning(
                "Orpheus disabled by policy (%s) and espeak unavailable; TTS off",
                self._orpheus_policy_reason,
            )
            return

        log.info(
            "Loading Orpheus TTS model %s on %s...", self._model_name, self._device
        )

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
            from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams  # type: ignore[import-not-found]

            class _TunedOrpheusModel(OrpheusModel):
                """OrpheusModel with a persistent event loop for vLLM.

                The upstream generate_tokens_sync() calls asyncio.run() per
                invocation, destroying the event loop each time.  vLLM's
                AsyncLLMEngine starts persistent background tasks on that
                loop, so destroying it kills the engine.  We maintain a
                single persistent loop on a dedicated daemon thread.
                """

                def __init__(self, model_name):
                    self._persistent_loop = asyncio.new_event_loop()
                    self._loop_thread = threading.Thread(
                        target=self._persistent_loop.run_forever,
                        daemon=True,
                        name="orpheus-vllm-loop",
                    )
                    self._loop_thread.start()
                    super().__init__(model_name)

                def _setup_engine(self):
                    engine_args = AsyncEngineArgs(
                        model=self.model_name,
                        dtype=self.dtype,
                        gpu_memory_utilization=settings.orpheus_gpu_memory_utilization,
                        max_model_len=settings.orpheus_max_model_len,
                        max_num_seqs=settings.orpheus_max_num_seqs,
                        max_num_batched_tokens=settings.orpheus_max_num_batched_tokens,
                    )
                    future = asyncio.run_coroutine_threadsafe(
                        self._create_engine_async(engine_args),
                        self._persistent_loop,
                    )
                    return future.result(timeout=120)

                @staticmethod
                async def _create_engine_async(engine_args):
                    return AsyncLLMEngine.from_engine_args(engine_args)

                def generate_tokens_sync(
                    self,
                    prompt,
                    voice=None,
                    request_id="req-001",
                    temperature=0.6,
                    top_p=0.8,
                    max_tokens=1200,
                    stop_token_ids=[49158],
                    repetition_penalty=1.3,
                ):
                    """Use persistent event loop instead of asyncio.run()."""
                    prompt_string = self._format_prompt(prompt, voice)
                    sampling_params = SamplingParams(
                        temperature=temperature,
                        top_p=top_p,
                        max_tokens=max_tokens,
                        stop_token_ids=stop_token_ids,
                        repetition_penalty=repetition_penalty,
                    )

                    token_queue: queue.Queue[str | Exception | None] = queue.Queue()

                    async def async_producer():
                        try:
                            async for result in self.engine.generate(
                                prompt=prompt_string,
                                sampling_params=sampling_params,
                                request_id=request_id,
                            ):
                                token_queue.put(result.outputs[0].text)
                        except Exception as exc:
                            token_queue.put(exc)
                            return
                        token_queue.put(None)

                    future = asyncio.run_coroutine_threadsafe(
                        async_producer(), self._persistent_loop
                    )

                    while True:
                        item = token_queue.get()
                        if item is None:
                            break
                        if isinstance(item, Exception):
                            raise item
                        yield item

                    future.result(timeout=5)

                def generate_speech(self, **kwargs):
                    from orpheus_tts.decoder import tokens_decoder_sync

                    return tokens_decoder_sync(self.generate_tokens_sync(**kwargs))

                def shutdown(self):
                    """Shutdown the vLLM engine and stop the persistent loop."""
                    engine = getattr(self, "engine", None)
                    if engine is not None:
                        shutdown_fn = getattr(engine, "shutdown", None)
                        if callable(shutdown_fn):
                            if self._persistent_loop.is_running():
                                fut = asyncio.run_coroutine_threadsafe(
                                    self._call_shutdown(shutdown_fn),
                                    self._persistent_loop,
                                )
                                try:
                                    fut.result(timeout=10)
                                except Exception:
                                    log.debug(
                                        "Orpheus engine shutdown raised", exc_info=True
                                    )
                        self.engine = None

                    loop = getattr(self, "_persistent_loop", None)
                    thread = getattr(self, "_loop_thread", None)
                    if loop is not None and loop.is_running():
                        loop.call_soon_threadsafe(loop.stop)
                    if thread is not None:
                        thread.join(timeout=5)

                @staticmethod
                async def _call_shutdown(shutdown_fn):
                    import inspect

                    result = shutdown_fn()
                    if inspect.isawaitable(result):
                        await result

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
                except (
                    Exception
                ) as exc:  # pragma: no cover - hardware/runtime dependent
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
        """Drop backend state so a dead engine can be recreated.

        Explicitly shuts down the vLLM engine subprocess and frees GPU
        memory so a fresh engine can allocate its full VRAM budget.
        """
        model = self._model
        self._loaded = False
        self._backend = None
        self._legacy_generate_speech = None
        self._model = None
        self._init_error = None

        if model is not None:
            shutdown = getattr(model, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    log.debug("Orpheus engine shutdown raised", exc_info=True)
            del model

        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def close(self) -> None:
        """Shutdown the TTS engine and free GPU memory."""
        if self._backend in {"orpheus_speech", "orpheus_tts"}:
            self._reset_orpheus_backend()

    def _collect_chunks_with_timeout(self, gen: Iterator[bytes]) -> bytes:
        """Drain an Orpheus generator safely with idle/total timeouts and max duration."""
        # Byte-count cap at source rate (24 kHz, 16-bit mono = 48 kB/s)
        max_utterance_s = settings.tts_max_utterance_s
        max_bytes = int(max_utterance_s * 24000 * 2) if max_utterance_s > 0 else 0

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
        total_bytes = 0
        start = time.monotonic()
        last_item = start

        while True:
            now = time.monotonic()
            if (now - start) > ORPHEUS_TOTAL_TIMEOUT_S:
                raise TimeoutError(
                    f"orpheus stream exceeded total timeout ({ORPHEUS_TOTAL_TIMEOUT_S}s)"
                )

            if max_bytes > 0 and total_bytes >= max_bytes:
                log.warning(
                    "Truncating orpheus stream at %.1fs max utterance duration",
                    max_utterance_s,
                )
                break

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
                    total_bytes += len(payload)
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
        if not isinstance(text, str) or not text.strip():
            return b""

        should_shed_to_espeak = False
        with self._active_lock:
            busy = self._active_requests > settings.tts_busy_queue_threshold
            if busy and self.prefers_orpheus() and self._orpheus_allowed:
                if self._espeak_available():
                    log.info(
                        "TTS busy (active=%d threshold=%d); shedding to espeak",
                        self._active_requests,
                        settings.tts_busy_queue_threshold,
                    )
                    should_shed_to_espeak = True
                else:
                    raise TTSBusyError("tts_busy_no_fallback")
            if not should_shed_to_espeak:
                self._active_requests += 1

        if should_shed_to_espeak:
            return await asyncio.to_thread(self._synthesize_with_espeak, text)

        try:
            return await asyncio.to_thread(self._synthesize_sync, text, emotion)
        finally:
            with self._active_lock:
                if self._active_requests > 0:
                    self._active_requests -= 1

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
                if (
                    self._backend == "orpheus_speech"
                    and self._legacy_generate_speech is not None
                ):
                    audio_float32 = self._legacy_generate_speech(tagged_text)
                    return pcm_float32_to_int16(
                        audio_float32,
                        src_rate=24000,
                        max_duration_s=settings.tts_max_utterance_s,
                    )

                if self._backend == "orpheus_tts" and self._model is not None:
                    # orpheus_tts currently yields int16 PCM chunks at 24 kHz.
                    req_id = f"req-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
                    gen = self._model.generate_speech(
                        prompt=tagged_text, request_id=req_id
                    )
                    audio_int16_24k = self._collect_chunks_with_timeout(gen)
                    if not audio_int16_24k:
                        return b""
                    return pcm_int16_resample_to_int16(
                        audio_int16_24k,
                        src_rate=24000,
                        max_duration_s=settings.tts_max_utterance_s,
                    )

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
                    log.warning(
                        "Orpheus synthesis failed; resetting engine and retrying once: %s",
                        exc,
                    )
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
            "performance_mode": bool(settings.performance_mode),
            "orpheus_allowed": self._orpheus_allowed,
            "orpheus_policy_reason": self._orpheus_policy_reason,
            "active_requests": self._active_requests,
            "busy_queue_threshold": settings.tts_busy_queue_threshold,
        }
