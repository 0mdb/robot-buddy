"""Turn audio on disk: ``<data_dir>/turns/<YYYY-MM-DD>/<HHMMSS>_<turn_id>.wav`` + ``.json``.

The sidecar holds what the bake-off needs to score a model without listening to anything:
the transcript, the face label the robot sent (member id + score, faces in view), speech
length, and the voice match made at the time. Children's voices: directories are 0700,
files 0600, and old days are pruned (``keep_days``, then ``max_mb`` oldest-first).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
_PRUNE_EVERY_S = 3600.0


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def wav_bytes(pcm: bytes) -> bytes:
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16 kHz 16-bit")
        return w.readframes(w.getnframes())


class TurnAudioStore:
    def __init__(self, root: Path, *, keep_days: int = 30, max_mb: int = 2000) -> None:
        self.root = Path(root) / "turns"
        self.keep_days = keep_days
        self.max_bytes = max_mb * 1024 * 1024
        self._last_prune = 0.0

    def save(
        self, pcm: bytes, meta: dict[str, Any], *, now: float | None = None
    ) -> Path:
        ts = time.time() if now is None else now
        dt = datetime.fromtimestamp(ts)
        day = self.root / dt.strftime("%Y-%m-%d")
        _mkdir_private(self.root.parent)
        _mkdir_private(self.root)
        _mkdir_private(day)
        stem = f"{dt.strftime('%H%M%S')}_{meta.get('turn_id') or 'noid'}"
        wav = day / f"{stem}.wav"
        _write_private(wav, wav_bytes(pcm))
        side = {"ts": round(ts, 3), "audio_s": round(len(pcm) / 2 / SAMPLE_RATE, 2)}
        side.update(meta)
        _write_private(
            day / f"{stem}.json", json.dumps(side, sort_keys=True).encode() + b"\n"
        )
        if ts - self._last_prune >= _PRUNE_EVERY_S:
            self._last_prune = ts
            self.prune(now=ts)
        return wav

    def days(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p for p in self.root.iterdir() if p.is_dir())

    def prune(self, *, now: float | None = None) -> int:
        """Drop days older than ``keep_days``, then oldest days over ``max_bytes``."""
        ts = time.time() if now is None else now
        cutoff = datetime.fromtimestamp(ts - self.keep_days * 86400).strftime(
            "%Y-%m-%d"
        )
        removed = 0
        days = self.days()
        for d in list(days):
            if d.name < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                days.remove(d)
                removed += 1
        sizes = {d: sum(f.stat().st_size for f in d.iterdir()) for d in days}
        total = sum(sizes.values())
        for d in days[:-1]:  # never today's
            if total <= self.max_bytes:
                break
            shutil.rmtree(d, ignore_errors=True)
            total -= sizes[d]
            removed += 1
        if removed:
            log.info("voice capture: pruned %d day(s)", removed)
        return removed

    def clips(self) -> list[tuple[Path, dict[str, Any]]]:
        """Every saved clip with its sidecar, oldest first."""
        out = []
        for d in self.days():
            for side in sorted(d.glob("*.json")):
                wav = side.with_suffix(".wav")
                if not wav.exists():
                    continue
                try:
                    out.append((wav, json.loads(side.read_text())))
                except (OSError, ValueError):
                    continue
        return out

    def forget_member(self, member_id: str) -> int:
        """Delete every clip labelled with this member (by face or by voice)."""
        n = 0
        for wav, meta in self.clips():
            labels = {
                (meta.get("face") or {}).get("member_id"),
                (meta.get("voice") or {}).get("member_id"),
            }
            if member_id in labels:
                wav.unlink(missing_ok=True)
                wav.with_suffix(".json").unlink(missing_ok=True)
                n += 1
        return n

    def forget_all(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
