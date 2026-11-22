"""Jarvis's own audit log and per-owner history, under JARVIS_DATA_DIR.

Nothing here is shared with Buddy: Buddy's conversation history, per-person
memory and capture never see a Jarvis turn (docs/screen-ui-and-admin.md §6.2).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .config import IDENTITY_RE


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class AuditLog:
    """Append-only JSONL: refusals, turns, every tool call with its arguments."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "audit.jsonl"
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> None:
        record = {"ts": round(time.time(), 3), "event": event, **fields}
        with self._lock:
            _append(self.path, record)


class History:
    """Per-owner turn history, one JSONL file per identity, readable only by them."""

    def __init__(self, data_dir: Path) -> None:
        self.dir = data_dir / "history"
        self._lock = threading.Lock()

    def _path(self, identity: str) -> Path:
        if not IDENTITY_RE.match(identity):
            raise ValueError(f"bad identity {identity!r}")
        return self.dir / f"{identity}.jsonl"

    def append(self, identity: str, user_text: str, reply: str, **meta: Any) -> None:
        record = {
            "ts": round(time.time(), 3),
            "user": user_text,
            "reply": reply,
            **meta,
        }
        with self._lock:
            _append(self._path(identity), record)

    def recent(
        self, identity: str, limit: int, within_s: float | None = None
    ) -> list[dict[str, Any]]:
        path = self._path(identity)
        if limit <= 0 or not path.is_file():
            return []
        with self._lock:
            lines = path.read_text(encoding="utf-8").splitlines()
        cutoff = time.time() - within_s if within_s is not None else None
        out: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None and rec.get("ts", 0) < cutoff:
                break
            out.append(rec)
            if len(out) >= limit:
                break
        out.reverse()
        return out
