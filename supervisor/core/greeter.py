"""Greeting people who come up to Buddy: by name when the camera recognises them.

Face events arrive in this order: ``vision.face_appeared`` (after 300 ms of detections),
then ``vision.person_identified`` for each enrolled member recognised (recognition runs a few
times a second, so usually within a second). Greeting on the first event would say "Oh, hi!"
and then "Hi, <name>!" a moment later, so a face that appears opens a short wait:

- recognised within ``WAIT_MS`` → "Hi, <name>!" (each member at most once per
  ``MEMBER_COOLDOWN_MS``);
- not recognised by then → the generic greeting (at most once per ``GENERIC_COOLDOWN_MS``);
- someone recognised later in the same visit, after any greeting → no second greeting
  unless ``QUIET_GAP_MS`` has passed since the last one.

Only someone close (``MAX_RANGE_MM``), and never during a conversation or in quiet mode
(the tick loop drops those). Names come from the roster on the robot and are spoken by
Buddy's own TTS (LAN); this module never logs them.
"""

from __future__ import annotations

import random

# Long enough for recognition to settle: at 1.5 s a known face often got "Oh, hi!" a
# moment before it was recognised (2026-11-18); faces are named over several checks now.
WAIT_MS = 3000.0
MAX_RANGE_MM = 2000.0
MEMBER_COOLDOWN_MS = 30 * 60 * 1000.0
GENERIC_COOLDOWN_MS = 10 * 60 * 1000.0
QUIET_GAP_MS = 60 * 1000.0

GENERIC_PHRASES = ("Oh, hi!", "Hi there!", "Hello!")
NAME_PHRASES = ("Hi, {name}!", "Hey, {name}!", "Oh, hi {name}!")


class Greeter:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._pending_until: float | None = None
        self._last_generic_ms = -1e12
        self._last_any_ms = -1e12
        self._last_member_ms: dict[str, float] = {}

    def on_event(
        self, etype: str, payload: dict, now_ms: float, names: dict[str, str]
    ) -> str | None:
        """Feed one planner event; returns a line to say now, if any."""
        if etype == "vision.face_appeared":
            rng = payload.get("range_mm")
            if isinstance(rng, (int, float)) and rng > MAX_RANGE_MM:
                return None
            self._pending_until = now_ms + WAIT_MS
            return None
        if etype == "vision.person_identified":
            mid = str(payload.get("member_id") or "")
            name = names.get(mid, "").strip()
            rng = payload.get("range_mm")
            if not name or (isinstance(rng, (int, float)) and rng > MAX_RANGE_MM):
                return None
            waiting = self._pending_until is not None
            self._pending_until = None
            if now_ms - self._last_member_ms.get(mid, -1e12) < MEMBER_COOLDOWN_MS:
                return None
            if not waiting and now_ms - self._last_any_ms < QUIET_GAP_MS:
                return None  # already greeted this visit
            self._last_member_ms[mid] = now_ms
            self._last_any_ms = now_ms
            return self._rng.choice(NAME_PHRASES).format(name=name)
        if etype == "vision.face_lost":
            self._pending_until = None
        return None

    def poll(self, now_ms: float) -> str | None:
        """The generic greeting once the wait for recognition runs out."""
        if self._pending_until is None or now_ms < self._pending_until:
            return None
        self._pending_until = None
        if now_ms - self._last_generic_ms < GENERIC_COOLDOWN_MS:
            return None
        if now_ms - self._last_any_ms < QUIET_GAP_MS:
            return None
        self._last_generic_ms = now_ms
        self._last_any_ms = now_ms
        return self._rng.choice(GENERIC_PHRASES)

    def cancel(self) -> None:
        """Drop a pending greeting (a conversation started, or quiet mode)."""
        self._pending_until = None
