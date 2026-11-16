"""Measured GPU memory and CUDA out-of-memory counts for /health.

Orpheus, Whisper and the conversation model share one card. When it fills up, the
symptoms are quiet: a model spills to system RAM and first audio goes from ~1.4 s to
~10 s, or an out-of-memory error kills one turn and Buddy says nothing. The old
``orpheus_vram_free_gb`` field is a snapshot from startup, before the models load, so it
showed ~14 GB free on a card with ~1 GB left. This module measures free memory when
asked (cached briefly) and counts out-of-memory errors seen in the logs.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

# Below this much free memory the card is one long prompt away from an OOM.
LOW_FREE_GB = 0.5
_CACHE_S = 5.0

_lock = threading.Lock()
_cached: tuple[float, dict | None] = (0.0, None)
_oom_count = 0
_last_oom: dict | None = None


def _query_nvidia_smi() -> dict | None:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            free, used, total = (float(p) / 1024.0 for p in parts)
        except ValueError:
            continue
        return {
            "free_gb": round(free, 2),
            "used_gb": round(used, 2),
            "total_gb": round(total, 2),
        }
    return None


def gpu_memory(now: float | None = None) -> dict | None:
    """Free/used/total GiB of the first GPU, or None without nvidia-smi."""
    global _cached
    now = time.monotonic() if now is None else now
    with _lock:
        ts, value = _cached
        if value is not None and now - ts < _CACHE_S:
            return value
    value = _query_nvidia_smi()
    with _lock:
        _cached = (now, value)
    return value


def _is_oom(text: str) -> bool:
    t = text.lower()
    return "out of memory" in t and ("cuda" in t or "gpu" in t or "vram" in t)


class OomCounter(logging.Handler):
    """Counts log records whose message or traceback reports a CUDA OOM."""

    def emit(self, record: logging.LogRecord) -> None:
        global _oom_count, _last_oom
        try:
            text = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                text += " " + repr(record.exc_info[1])
            elif record.exc_text:
                text += " " + record.exc_text
        except Exception:
            return
        if not _is_oom(text):
            return
        with _lock:
            _oom_count += 1
            _last_oom = {
                "at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.localtime(record.created)
                ),
                "logger": record.name,
                "message": record.getMessage()[:200],
            }


_handler: OomCounter | None = None


def install() -> None:
    """Attach the OOM counter to the root logger (idempotent)."""
    global _handler
    if _handler is not None:
        return
    _handler = OomCounter(level=logging.WARNING)
    logging.getLogger().addHandler(_handler)


def snapshot() -> dict:
    mem = gpu_memory()
    with _lock:
        count, last = _oom_count, _last_oom
    return {
        **(mem or {"free_gb": None, "used_gb": None, "total_gb": None}),
        "low_free": bool(mem is not None and mem["free_gb"] < LOW_FREE_GB),
        "oom_count": count,
        "last_oom": last,
    }


def _reset_for_tests() -> None:
    global _cached, _oom_count, _last_oom
    with _lock:
        _cached = (0.0, None)
        _oom_count = 0
        _last_oom = None
