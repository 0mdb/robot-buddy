"""Conversation history for the parent's review and tuning: off by default, robot-local.

What the children said (as heard by speech recognition) and what Buddy said back, plus
Buddy's own lines (greeter, planner, remarks), with the timing and expression of each
reply and who the camera recognised. It is a record of what children say, so:

- **Off unless a parent turns it on** (``conversation.history_enabled``); nothing is
  written while it is off.
- **On the robot only:** ``conversation_history/history.jsonl`` beside the household
  roster (git-ignored ``data/``), shown in the dashboard. "Forget everyone" deletes it with
  the roster (``personality/roster.py``), and the dashboard can clear it.
- **Short-lived:** entries older than ``conversation.history_days`` are dropped.
- **Never logged:** the words go only to this file, not to the journal, so logs read for
  debugging carry no conversation text.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    AI_CONVERSATION_ASSISTANT_TEXT,
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_SPEAKER,
    AI_CONVERSATION_TRANSCRIPTION,
    AI_CONVERSATION_USER_TEXT,
)

log = logging.getLogger(__name__)

HISTORY_DIR = "conversation_history"
MAX_TEXT = 1000
PRUNE_EVERY_S = 3600.0


def history_path(roster_path: str | Path) -> Path:
    return Path(roster_path).parent / HISTORY_DIR / "history.jsonl"


class ConversationHistory:
    def __init__(
        self,
        path: str | Path,
        enabled: Callable[[], bool],
        days: Callable[[], float],
        present: Callable[[], list[str]] | None = None,
        clock: Callable[[], float] = time.time,
        names: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.path = Path(path)
        self._enabled = enabled
        self._days = days
        self._present = present or (lambda: [])
        self._names = names or (lambda: {})
        self._clock = clock
        self._last_prune = -1e18
        # The reply's expression arrives before its text.
        self._emotion: dict[tuple[str, Any], str] = {}

    # -- writing ------------------------------------------------------------

    def feed(self, env: Envelope) -> None:
        """Take the conversation events the tick loop drains (AI worker)."""
        if not self._enabled():
            self._emotion.clear()
            return
        p = env.payload
        key = (str(p.get("session_id", "")), p.get("turn_id"))
        if env.type == AI_CONVERSATION_TRANSCRIPTION:
            self._write(
                role="child",
                text=p.get("text", ""),
                session=key[0],
                who=self._present(),
                stt_ms=p.get("stt_latency_ms"),
            )
        elif env.type == AI_CONVERSATION_USER_TEXT:
            self._write(role="typed", text=p.get("text", ""), session=key[0])
        elif env.type == AI_CONVERSATION_EMOTION:
            self._emotion[key] = str(p.get("emotion", ""))
        elif env.type == AI_CONVERSATION_ASSISTANT_TEXT:
            self._write(
                role="buddy",
                source="conversation",
                text=p.get("text", ""),
                session=key[0],
                emotion=self._emotion.pop(key, None),
            )
        elif env.type == AI_CONVERSATION_DONE:
            self._emotion.pop(key, None)
        elif env.type == AI_CONVERSATION_SPEAKER:
            # Voice ID's guess, for checking it against who was really there.
            turn = p.get("turn") or {}
            sess = p.get("session") or {}
            self._write(
                role="voice",
                session=key[0],
                voice=self._name(turn.get("member_id")) or "unsure",
                best=self._name(turn.get("best_id")),
                score=turn.get("score"),
                runner=self._name(turn.get("runner_id")),
                runner_score=turn.get("runner_score"),
                conversation=self._name(sess.get("member_id")),
                speech_s=p.get("speech_s"),
                learned=bool(p.get("learned")) or None,
            )

    def _name(self, member_id: Any) -> str | None:
        if not member_id:
            return None
        return self._names().get(str(member_id)) or "someone enrolled"

    def reply_timing(self, after_speech_ms: float, late_resumes: int) -> None:
        """How long the child waited: end of their speech to Buddy's first sound."""
        if self._enabled():
            self._write(
                role="timing",
                reply_ms=round(after_speech_ms),
                late_resumes=late_resumes or None,
            )

    def say(self, source: str, text: str) -> None:
        """A line Buddy says on its own (greeter, planner, remarks)."""
        if self._enabled():
            self._write(role="buddy", source=source, text=text)

    def _write(self, **entry: Any) -> None:
        text = entry.get("text")
        if text is not None:
            entry["text"] = str(text)[:MAX_TEXT]
            if not entry["text"].strip():
                return
        entry = {k: v for k, v in entry.items() if v not in (None, "", [])}
        entry["t"] = round(self._clock(), 3)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("conversation history: write failed (%s)", e)
            return
        if entry["t"] - self._last_prune >= PRUNE_EVERY_S:
            self.prune()

    # -- reading and housekeeping -----------------------------------------

    def read(self) -> list[dict[str, Any]]:
        """Entries within the keep window, oldest first."""
        cutoff = self._clock() - self._days() * 86400.0
        out: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return out
        for line in lines:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(e, dict) and float(e.get("t", 0)) >= cutoff:
                out.append(e)
        return out

    def prune(self) -> None:
        """Rewrite the file without entries past the keep window."""
        self._last_prune = self._clock()
        if not self.path.exists():
            return
        keep = self.read()
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(
                "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in keep),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("conversation history: prune failed (%s)", e)

    def clear(self) -> None:
        self._emotion.clear()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
