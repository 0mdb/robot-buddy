"""Conversation benchmark — measures LLM + TTS latency via text-mode WebSocket.

Uses /converse in text mode (bypasses STT entirely) to measure LLM first-token
latency and TTS TTFB in isolation.  Triggered from the dashboard via WS command.

Metrics per utterance:
    ws_connect_ms     — time to open the WebSocket and receive "listening"
    llm_latency_ms    — server-reported LLM generation time (from emotion message)
    llm_observed_ms   — supervisor-observed time from text sent → emotion received
    tts_ttfb_ms       — time from text sent to first audio chunk received
    total_ms          — time from text sent to "done" message
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from typing import TYPE_CHECKING

from supervisor.api.tts_benchmark import BENCHMARK_CORPUS
from supervisor.messages.types import CONV_BENCHMARK_DONE, CONV_BENCHMARK_PROGRESS

if TYPE_CHECKING:
    from supervisor.api.conversation_capture import ConversationCapture

log = logging.getLogger(__name__)

_benchmark_task: asyncio.Task[None] | None = None


def start_benchmark(
    server_base_url: str,
    conv_capture: ConversationCapture,
    *,
    session_active: bool = False,
) -> bool:
    """Start benchmark if not already running. Returns False on conflict."""
    global _benchmark_task  # noqa: PLW0603
    if _benchmark_task and not _benchmark_task.done():
        log.warning("conv benchmark already running")
        return False
    if session_active:
        log.warning("refusing conv benchmark during active conversation")
        return False
    if not server_base_url:
        log.warning("no server URL configured")
        return False
    _benchmark_task = asyncio.create_task(_run(server_base_url, conv_capture))
    return True


async def _run(server_base_url: str, capture: ConversationCapture) -> None:
    """Run the benchmark corpus sequentially."""
    ws_url = server_base_url.replace("http", "ws") + "/converse"
    total = len(BENCHMARK_CORPUS)
    ws_connect_list: list[float] = []
    llm_list: list[float] = []
    llm_observed_list: list[float] = []
    tts_ttfb_list: list[float] = []
    total_list: list[float] = []
    run_id = int(time.time() * 1000)

    for idx, (text, emotion) in enumerate(BENCHMARK_CORPUS):
        result = await _bench_one(
            ws_url,
            text,
            emotion,
            robot_id=f"benchmark-{run_id}-{idx}",
        )
        result["index"] = idx
        result["total"] = total
        capture.capture_event(CONV_BENCHMARK_PROGRESS, result)

        if "ws_connect_ms" in result:
            ws_connect_list.append(float(result["ws_connect_ms"]))
        if "llm_latency_ms" in result:
            llm_list.append(float(result["llm_latency_ms"]))
        if "llm_observed_ms" in result:
            llm_observed_list.append(float(result["llm_observed_ms"]))
        if "tts_ttfb_ms" in result:
            tts_ttfb_list.append(float(result["tts_ttfb_ms"]))
        if "total_ms" in result:
            total_list.append(float(result["total_ms"]))

    def _stats(values: list[float], prefix: str) -> dict:
        if not values:
            return {}
        s = sorted(values)
        return {
            f"mean_{prefix}": round(statistics.mean(values), 1),
            f"p50_{prefix}": round(s[len(s) // 2], 1),
            f"p95_{prefix}": round(s[int(len(s) * 0.95)], 1),
        }

    summary: dict = {"count": total}
    summary.update(_stats(ws_connect_list, "ws_connect_ms"))
    summary.update(_stats(llm_list, "llm_ms"))
    summary.update(_stats(llm_observed_list, "llm_observed_ms"))
    summary.update(_stats(tts_ttfb_list, "tts_ttfb_ms"))
    summary.update(_stats(total_list, "total_ms"))

    capture.capture_event(CONV_BENCHMARK_DONE, summary)
    log.info("conv benchmark done: %s", summary)


async def _bench_one(
    ws_url: str, text: str, emotion: str, *, robot_id: str = "benchmark"
) -> dict:
    """Benchmark one utterance via text-mode WebSocket. Returns metrics dict."""
    truncated = text[:40] + ("..." if len(text) > 40 else "")
    try:
        import websockets
    except ImportError:
        return {
            "text": truncated,
            "emotion": emotion,
            "error": "websockets not installed",
        }

    try:
        t_connect = time.monotonic()
        async with websockets.connect(
            f"{ws_url}?robot_id={robot_id}",
            open_timeout=10.0,
        ) as ws:
            # Await "listening" — server is ready
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            ws_connect_ms = round((time.monotonic() - t_connect) * 1000, 1)
            msg = json.loads(raw)
            if msg.get("type") != "listening":
                return {
                    "text": truncated,
                    "emotion": emotion,
                    "error": f"unexpected: {msg.get('type')}",
                }

            # Send text and start timing
            t_text = time.monotonic()
            await ws.send(json.dumps({"type": "text", "text": text}))

            llm_latency_ms: float | None = None
            llm_observed_ms: float | None = None
            tts_ttfb_ms: float | None = None
            t_end: float | None = None

            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                msg = json.loads(raw)
                mtype = msg.get("type")

                if mtype == "emotion":
                    if llm_observed_ms is None:
                        llm_observed_ms = round((time.monotonic() - t_text) * 1000, 1)
                    if "llm_latency_ms" in msg:
                        llm_latency_ms = float(msg["llm_latency_ms"])
                    elif llm_latency_ms is None and llm_observed_ms is not None:
                        llm_latency_ms = llm_observed_ms

                elif mtype == "audio" and tts_ttfb_ms is None:
                    tts_ttfb_ms = round((time.monotonic() - t_text) * 1000, 1)

                elif mtype in ("done", "listening"):
                    t_end = time.monotonic()
                    break

                elif mtype == "error":
                    return {
                        "text": truncated,
                        "emotion": emotion,
                        "error": msg.get("message", "server_error"),
                    }

            total_ms = round((t_end - t_text) * 1000, 1) if t_end else None

            result: dict = {
                "text": truncated,
                "emotion": emotion,
                "ws_connect_ms": ws_connect_ms,
            }
            if llm_latency_ms is not None:
                result["llm_latency_ms"] = llm_latency_ms
            if llm_observed_ms is not None:
                result["llm_observed_ms"] = llm_observed_ms
            if tts_ttfb_ms is not None:
                result["tts_ttfb_ms"] = tts_ttfb_ms
            if total_ms is not None:
                result["total_ms"] = total_ms
            return result

    except asyncio.TimeoutError:
        return {"text": truncated, "emotion": emotion, "error": "timeout"}
    except Exception as e:
        return {"text": truncated, "emotion": emotion, "error": str(e)}
