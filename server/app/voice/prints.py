"""Voiceprints per roster member id: ``<data_dir>/voiceprints.json`` (0600, no names).

Each member holds up to ``max_per_member`` sample embeddings, not one average, so a voice
heard in different rooms and moods stays covered. A member's score for a clip is the mean
of its best three sample cosines. A name is given only when the best member clears
``match_score`` and leads the runner-up by ``margin`` (as faces: brothers overlap).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

_TOP_K = 3
_DUPLICATE = 0.97


@dataclass(frozen=True, slots=True)
class Match:
    member_id: str | None  # None: nobody clears the bar with a clear lead
    score: float  # best member's score (even when not named)
    best_id: str | None
    runner_id: str | None
    runner_score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "score": round(self.score, 3),
            "best_id": self.best_id,
            "runner_id": self.runner_id,
            "runner_score": round(self.runner_score, 3),
        }


def member_score(samples: np.ndarray, emb: np.ndarray) -> float:
    sims = samples @ emb
    k = min(_TOP_K, len(sims))
    return float(np.sort(sims)[-k:].mean())


class VoicePrintStore:
    def __init__(self, path: Path, *, max_per_member: int = 40) -> None:
        self.path = Path(path)
        self.max_per_member = max_per_member
        self._lock = threading.Lock()
        self._samples: dict[str, np.ndarray] = {}
        self._meta: dict[str, list[dict[str, Any]]] = {}
        self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            log.warning("voiceprints unreadable (%s); starting empty", e)
            return
        for mid, entry in (raw.get("members") or {}).items():
            embs = [s["emb"] for s in entry.get("samples", []) if s.get("emb")]
            if embs:
                self._samples[mid] = np.asarray(embs, dtype=np.float32)
                self._meta[mid] = [
                    {k: v for k, v in s.items() if k != "emb"}
                    for s in entry["samples"]
                    if s.get("emb")
                ]

    def _save(self) -> None:
        members = {}
        for mid, arr in self._samples.items():
            members[mid] = {
                "samples": [
                    {**m, "emb": [round(float(x), 5) for x in e]}
                    for m, e in zip(self._meta[mid], arr, strict=True)
                ]
            }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "members": members}, f)
        os.replace(tmp, self.path)

    # -- queries -----------------------------------------------------------

    def summary(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                mid: {
                    "samples": len(arr),
                    "speech_s": round(
                        sum(float(m.get("speech_s", 0)) for m in self._meta[mid]), 1
                    ),
                    "last": max((m.get("ts", 0) for m in self._meta[mid]), default=0),
                }
                for mid, arr in self._samples.items()
            }

    def count(self, member_id: str) -> int:
        with self._lock:
            arr = self._samples.get(member_id)
            return 0 if arr is None else len(arr)

    def scores(self, emb: np.ndarray) -> dict[str, float]:
        with self._lock:
            return {mid: member_score(arr, emb) for mid, arr in self._samples.items()}

    def match(self, emb: np.ndarray, *, threshold: float, margin: float) -> Match:
        ranked = sorted(self.scores(emb).items(), key=lambda kv: kv[1], reverse=True)
        if not ranked:
            return Match(None, 0.0, None, None, 0.0)
        best_id, best = ranked[0]
        runner_id, runner = ranked[1] if len(ranked) > 1 else (None, 0.0)
        named = best >= threshold and best - runner >= margin
        return Match(best_id if named else None, best, best_id, runner_id, runner)

    # -- changes -----------------------------------------------------------

    def add(
        self, member_id: str, emb: np.ndarray, *, speech_s: float, source: str
    ) -> bool:
        """Add a sample; False if it nearly duplicates one already held."""
        emb = np.asarray(emb, dtype=np.float32)
        with self._lock:
            arr = self._samples.get(member_id)
            if arr is not None and len(arr) and float((arr @ emb).max()) >= _DUPLICATE:
                return False
            meta = {"ts": round(time.time(), 1), "speech_s": round(speech_s, 2)}
            meta["source"] = source
            if arr is None:
                self._samples[member_id] = emb[None, :]
                self._meta[member_id] = [meta]
            else:
                self._samples[member_id] = np.vstack([arr, emb[None, :]])
                self._meta[member_id].append(meta)
            self._trim(member_id)
            self._save()
            return True

    def _trim(self, member_id: str) -> None:
        """A full set drops its most redundant sample (most like the others), not its
        oldest, so the variety stays."""
        arr = self._samples[member_id]
        while len(arr) > self.max_per_member:
            sims = arr @ arr.T
            np.fill_diagonal(sims, 0.0)
            drop = int(sims.mean(axis=1).argmax())
            arr = np.delete(arr, drop, axis=0)
            del self._meta[member_id][drop]
        self._samples[member_id] = arr

    def forget(self, member_id: str) -> bool:
        with self._lock:
            if member_id not in self._samples:
                return False
            del self._samples[member_id]
            del self._meta[member_id]
            self._save()
            return True

    def keep_only(self, member_ids: set[str]) -> list[str]:
        """Drop prints of members no longer on the robot's roster."""
        with self._lock:
            gone = [m for m in self._samples if m not in member_ids]
            for m in gone:
                del self._samples[m]
                del self._meta[m]
            if gone:
                self._save()
            return gone

    def forget_all(self) -> None:
        with self._lock:
            self._samples.clear()
            self._meta.clear()
            self._save()
