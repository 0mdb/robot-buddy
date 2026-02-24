"""TTS benchmark runner — measures synthesis latency for a fixed corpus.

Triggered from the dashboard via WS command. Runs httpx POSTs to the
server /tts endpoint, measures TTFB + total time, and reports results
through ConversationCapture so the dashboard can display them.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import TYPE_CHECKING

from supervisor.messages.types import TTS_BENCHMARK_DONE, TTS_BENCHMARK_PROGRESS

if TYPE_CHECKING:
    from supervisor.api.conversation_capture import ConversationCapture

log = logging.getLogger(__name__)

# 320 bytes = 10 ms at 16 kHz, 16-bit mono
_CHUNK_BYTES = 320
_BYTES_PER_MS = 32  # 16000 Hz * 2 bytes / 1000

BENCHMARK_CORPUS: list[tuple[str, str]] = [
    ("Hi!", "happy"),
    ("I like your shoes.", "happy"),
    ("Let's play a game together!", "excited"),
    (
        "Once upon a time, there was a little robot who loved to help.",
        "neutral",
    ),
    ("I don't know the answer to that question.", "sad"),
    ("Watch out! There's something behind you!", "scared"),
    (
        "Did you know that octopuses have three hearts and blue blood? That's so cool!",
        "curious",
    ),
    (
        "I'm feeling really sleepy. Maybe we should take a break and "
        "rest for a little while.",
        "sleepy",
    ),
]

_benchmark_task: asyncio.Task[None] | None = None


def start_benchmark(
    tts_endpoint: str,
    conv_capture: ConversationCapture,
    *,
    session_active: bool = False,
) -> bool:
    """Start benchmark if not already running. Returns False on conflict."""
    global _benchmark_task  # noqa: PLW0603
    if _benchmark_task and not _benchmark_task.done():
        log.warning("benchmark already running")
        return False
    if session_active:
        log.warning("refusing benchmark during active conversation")
        return False
    if not tts_endpoint:
        log.warning("no TTS endpoint configured")
        return False
    _benchmark_task = asyncio.create_task(_run(tts_endpoint, conv_capture))
    return True


async def _run(tts_endpoint: str, capture: ConversationCapture) -> None:
    """Run the benchmark corpus sequentially."""
    try:
        import httpx
    except ImportError:
        capture.capture_event(
            TTS_BENCHMARK_DONE, {"error": "httpx not installed", "count": 0}
        )
        return

    total = len(BENCHMARK_CORPUS)
    ttfb_list: list[float] = []
    total_list: list[float] = []

    for idx, (text, emotion) in enumerate(BENCHMARK_CORPUS):
        result = await _bench_one(httpx, tts_endpoint, text, emotion)
        result["index"] = idx
        result["total"] = total
        capture.capture_event(TTS_BENCHMARK_PROGRESS, result)

        if "ttfb_ms" in result:
            ttfb_list.append(result["ttfb_ms"])
        if "total_ms" in result:
            total_list.append(result["total_ms"])

    # Summary
    summary: dict = {"count": total}
    if ttfb_list:
        sorted_ttfb = sorted(ttfb_list)
        summary["mean_ttfb_ms"] = round(statistics.mean(ttfb_list), 1)
        summary["p50_ttfb_ms"] = round(sorted_ttfb[len(sorted_ttfb) // 2], 1)
        summary["p95_ttfb_ms"] = round(sorted_ttfb[int(len(sorted_ttfb) * 0.95)], 1)
    if total_list:
        summary["mean_total_ms"] = round(statistics.mean(total_list), 1)

    capture.capture_event(TTS_BENCHMARK_DONE, summary)
    log.info("TTS benchmark done: %s", summary)


async def _bench_one(
    httpx_mod: object,
    endpoint: str,
    text: str,
    emotion: str,
) -> dict:
    """Benchmark a single utterance. Returns metrics dict."""
    payload = {"text": text, "emotion": emotion, "stream": True}
    truncated = text[:40] + ("..." if len(text) > 40 else "")
    try:
        async with httpx_mod.AsyncClient(timeout=30.0) as client:  # type: ignore[union-attr]
            t_start = time.monotonic()
            async with client.stream("POST", endpoint, json=payload) as resp:
                if resp.status_code != 200:
                    return {
                        "text": truncated,
                        "emotion": emotion,
                        "error": f"HTTP {resp.status_code}",
                    }

                t_first: float | None = None
                total_bytes = 0
                chunk_count = 0

                async for chunk in resp.aiter_bytes(_CHUNK_BYTES):
                    if t_first is None:
                        t_first = time.monotonic()
                    total_bytes += len(chunk)
                    chunk_count += 1

                t_end = time.monotonic()

            if t_first is None:
                return {
                    "text": truncated,
                    "emotion": emotion,
                    "error": "no audio data",
                }

            return {
                "text": truncated,
                "emotion": emotion,
                "ttfb_ms": round((t_first - t_start) * 1000, 1),
                "total_ms": round((t_end - t_start) * 1000, 1),
                "audio_duration_ms": round(total_bytes / _BYTES_PER_MS, 1),
                "chunk_count": chunk_count,
            }
    except Exception as e:
        return {"text": truncated, "emotion": emotion, "error": str(e)}
