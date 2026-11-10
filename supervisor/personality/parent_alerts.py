"""Quiet alerts to parents when a child asks Buddy to keep a secret or discloses something serious.

Operator decision (2026-11-10, ~/vantage/docs/SIM-INTERACTION.md "Parent alerts"):

- **Triggers:** a child asking Buddy to keep a secret from parents, or saying someone told them
  not to tell; and the disclosures where follow-up matters most: a stranger, unwanted touching,
  being hurt, being bullied. Not ordinary sadness.
- **Quiet:** nothing changes in what Buddy says to the child. Buddy already never promises
  secrecy (a hard check in the L1 suite), so it never says something this contradicts.
- **Where:** an inbox stored on the robot (``data/parent_alerts.json``, git-ignored, mode 600),
  shown on the dashboard with the child's words and Buddy's reply; plus, if configured, a Home
  Assistant push with **only the category and time** -- the words never leave the robot.

Detection is deliberately separate from the server's prompt cues (``server/app/llm/
safety_cues.py``): different job, different categories, and the robot is the record. Like the
cues, it errs towards firing; a parent dismissing a false alert costs little.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_ALERTS = 200
RETENTION_S = 90 * 86400
PUSH_COOLDOWN_S = 600.0  # at most one push per category per 10 minutes

CATEGORIES: dict[str, str] = {
    "secret": "asked Buddy to keep a secret",
    "dont_tell": "said someone told them not to tell",
    "stranger": "mentioned a stranger or someone they don't know",
    "touch": "mentioned unwanted touching",
    "hurt": "said they were hurt",
    "bullied": "mentioned being bullied or hit",
}

_PATTERNS: dict[str, re.Pattern[str]] = {
    "secret": re.compile(
        r"\b(keep (a|my|this|the|it a) secret|(it'?s|its) (a|our) secret|"
        r"promise (you )?(won'?t|not to|don'?t) tell|don'?t tell (my |anyone|any)|"
        r"can you keep|just between us|nobody can know|you can'?t tell)\b",
        re.IGNORECASE,
    ),
    "dont_tell": re.compile(
        r"\b(said|says|told me) (not to|to not|don'?t|i can'?t|i shouldn'?t) tell|"
        r"\bif i tell\b|\bnot supposed to tell\b|\bour little secret\b",
        re.IGNORECASE,
    ),
    "stranger": re.compile(
        r"\b(stranger|a (man|lady|woman|guy|person|grown-?up) (at|in|on|from|said|asked|"
        r"wants?|told|offered|gave)|someone i don'?t know|"
        r"in (his|her|their|a) (car|van|truck)|get in (his|her|the|their) (car|van)|"
        r"wants? to meet|meet up|send (him|her|them) (pictures|photos|a picture))\b",
        re.IGNORECASE,
    ),
    "touch": re.compile(
        r"\b(touch(es|ed|ing)? me|touch(es|ed)? my|private parts?|"
        r"in a way i don'?t like|bad touch|made me take off)\b",
        re.IGNORECASE,
    ),
    "hurt": re.compile(
        r"\b(really (hurts|hurt)|it hurts|i'?m hurt|got hurt|bleed\w*|blood|broke my|"
        r"can'?t breathe|hit my head|fell (off|down))\b",
        re.IGNORECASE,
    ),
    "bullied": re.compile(
        r"\b(bull(y|ies|ied|ying)|push(es|ed)? me|hit(s)? me|kick(s|ed)? me|"
        r"punch(es|ed)? me|beat me up|picks? on me|mean to me every)\b",
        re.IGNORECASE,
    ),
}


def detect(text: str) -> list[str]:
    """Alert categories the child's words match, in a fixed order."""
    return [c for c, pat in _PATTERNS.items() if pat.search(text or "")]


@dataclass(slots=True)
class Alert:
    id: str
    ts: float  # wall clock, for a parent reading it
    categories: list[str]
    child_text: str
    buddy_reply: str = ""
    session_id: str = ""
    turn_id: int | str = ""
    reviewed: bool = False

    @property
    def summary(self) -> str:
        return "; ".join(CATEGORIES[c] for c in self.categories if c in CATEGORIES)


@dataclass(slots=True)
class AlertStore:
    path: Path
    enabled: bool = True
    alerts: list[Alert] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> AlertStore:
        store = cls(path)
        if not path.exists():
            return store
        try:
            raw = json.loads(path.read_text())
            store.enabled = bool(raw.get("enabled", True))
            names = set(Alert.__dataclass_fields__)
            store.alerts = [
                Alert(**{k: v for k, v in a.items() if k in names})
                for a in raw.get("alerts", [])
            ]
        except (OSError, json.JSONDecodeError, TypeError) as e:
            log.warning(
                "parent alerts unreadable (%s); starting a new inbox beside it", e
            )
            path.rename(path.with_name(path.name + f".damaged-{int(time.time())}"))
        return store

    def save(self) -> None:
        cutoff = time.time() - RETENTION_S
        self.alerts = [a for a in self.alerts if a.ts >= cutoff][-MAX_ALERTS:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(
                {
                    "version": 1,
                    "enabled": self.enabled,
                    "alerts": [asdict(a) for a in self.alerts],
                },
                f,
                indent=1,
            )
        os.replace(tmp, self.path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "alerts": [
                asdict(a) | {"summary": a.summary} for a in reversed(self.alerts)
            ],
            "unreviewed": sum(not a.reviewed for a in self.alerts),
        }

    def mark(self, alert_id: str, reviewed: bool) -> bool:
        for a in self.alerts:
            if a.id == alert_id:
                a.reviewed = reviewed
                return True
        return False

    def remove(self, alert_id: str) -> bool:
        n = len(self.alerts)
        self.alerts = [a for a in self.alerts if a.id != alert_id]
        return len(self.alerts) != n

    def clear(self) -> None:
        self.alerts = []


# ── Home Assistant push ─────────────────────────────────────────────

PushFn = Callable[[str, str], Awaitable[bool]]
"""(title, message) -> delivered."""


def home_assistant_push_from_env(env: dict[str, str] | None = None) -> PushFn | None:
    """A push function from the environment, or None if unset. Two ways, webhook preferred:

    - ``RB_HA_WEBHOOK_URL``: a Home Assistant automation with a webhook trigger that sends the
      notification itself. Buddy holds no token and can do nothing else in Home Assistant.
      The URL contains the webhook id, which is a secret.
    - ``RB_HA_URL`` + ``RB_HA_TOKEN`` + ``RB_HA_NOTIFY``: call a notify service directly with a
      token. Any HA token can do far more than notify; use a dedicated non-admin user.

    These live in /etc/robot-buddy/supervisor.env on the robot, never in the repo.
    """
    env = dict(os.environ if env is None else env)
    webhook = env.get("RB_HA_WEBHOOK_URL")
    if webhook:
        if not re.fullmatch(
            r"https?://[^\s/]+/api/webhook/[A-Za-z0-9_-]{16,}", webhook
        ):
            log.warning(
                "RB_HA_WEBHOOK_URL is not a Home Assistant webhook URL; pushes disabled"
            )
            return None
        return _poster(webhook, headers={}, kind="webhook")
    url, token, service = (
        env.get("RB_HA_URL"),
        env.get("RB_HA_TOKEN"),
        env.get("RB_HA_NOTIFY"),
    )
    if not (url and token and service):
        return None
    service = service.removeprefix("notify.")
    if not re.fullmatch(r"[a-z0-9_]+", service):
        log.warning(
            "RB_HA_NOTIFY %r is not a notify service name; pushes disabled", service
        )
        return None
    endpoint = f"{url.rstrip('/')}/api/services/notify/{service}"
    return _poster(
        endpoint, headers={"Authorization": f"Bearer {token}"}, kind="notify"
    )


def _poster(endpoint: str, *, headers: dict[str, str], kind: str) -> PushFn:
    async def push(title: str, message: str) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(
                    endpoint, headers=headers, json={"title": title, "message": message}
                )
            if r.status_code >= 300:
                log.warning("parent alert push (%s): HTTP %s", kind, r.status_code)
            return r.status_code < 300
        except Exception as e:  # noqa: BLE001 -- a failed push must never touch the robot
            # Never log the exception text: it can carry the URL, and the webhook id is secret.
            log.warning("parent alert push (%s) failed: %s", kind, type(e).__name__)
            return False

    return push


def push_message(alert: Alert) -> tuple[str, str]:
    """Category and time only. The child's words stay on the robot."""
    when = time.strftime("%-I:%M %p", time.localtime(alert.ts))
    return (
        "Buddy",
        f"At {when} a child {alert.summary}. Details are in Buddy's dashboard.",
    )


# ── The tap on conversation events ──────────────────────────────────


class ParentAlerts:
    """Fed every worker envelope by the tick loop; creates and completes alerts."""

    TRANSCRIPTION = "ai.conversation.transcription"
    ASSISTANT_TEXT = "ai.conversation.assistant_text"

    def __init__(self, path: Path, push: PushFn | None = None) -> None:
        self.path = path
        self.push = push
        self._pending: dict[
            tuple[str, str], Alert
        ] = {}  # (session, turn) -> alert awaiting reply
        self._last_push: dict[str, float] = {}

    def store(self) -> AlertStore:
        return AlertStore.load(self.path)

    def capture_envelope(self, env: Any) -> None:
        """Called from the tick loop for every worker envelope. Never raises. Does nothing for
        almost every envelope; when an alert fires it writes one small file (rare) and
        schedules the push as a task, so the tick never waits on the network."""
        try:
            t = getattr(env, "type", "")
            if t == self.TRANSCRIPTION:
                self._on_child_text(env.payload or {})
            elif t == self.ASSISTANT_TEXT:
                self._on_reply(env.payload or {})
        except Exception:  # noqa: BLE001
            log.exception("parent alert tap failed")

    def _key(self, p: dict[str, Any]) -> tuple[str, str]:
        return str(p.get("session_id", "")), str(p.get("turn_id", ""))

    def _on_child_text(self, p: dict[str, Any]) -> None:
        text = str(p.get("text", ""))[:500]
        cats = detect(text)
        if not cats:
            return
        alert = Alert(
            id=secrets.token_hex(4),
            ts=time.time(),
            categories=cats,
            child_text=text,
            session_id=str(p.get("session_id", "")),
            turn_id=p.get("turn_id", ""),
        )
        store = self.store()
        if not store.enabled:
            return
        store.alerts.append(alert)
        self._write(store)
        self._pending[self._key(p)] = alert
        self._maybe_push(alert)

    def _on_reply(self, p: dict[str, Any]) -> None:
        alert = self._pending.pop(self._key(p), None)
        if alert is None:
            return
        store = self.store()
        for a in store.alerts:
            if a.id == alert.id:
                a.buddy_reply = str(p.get("text", ""))[:500]
        self._write(store)

    def _write(self, store: AlertStore) -> None:
        try:
            store.save()
        except OSError as e:
            log.warning("parent alerts not saved: %s", e)

    def _maybe_push(self, alert: Alert) -> None:
        if self.push is None:
            return
        now = time.monotonic()
        fresh = [
            c
            for c in alert.categories
            if now - self._last_push.get(c, -1e9) >= PUSH_COOLDOWN_S
        ]
        if not fresh:
            return
        for c in alert.categories:
            self._last_push[c] = now
        title, message = push_message(alert)
        try:
            asyncio.get_running_loop().create_task(self.push(title, message))
        except RuntimeError:
            log.warning("parent alert push skipped: no event loop")
