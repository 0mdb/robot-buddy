"""Deterministic event-driven speech policy."""

from __future__ import annotations

from dataclasses import dataclass

from supervisor_v2.devices.protocol import FaceButtonId
from supervisor_v2.core.event_bus import PlannerEvent
from supervisor_v2.core.state import RobotState


@dataclass(slots=True)
class SpeechIntent:
    text: str
    source_event: str


_FACE_BUSY_HOLD_MS: float = 1500.0


class SpeechPolicy:
    """Turns high-signal runtime events into bounded spoken lines."""

    def __init__(self) -> None:
        self._last_spoken_ms: dict[str, float] = {}
        self._phrase_index: dict[str, int] = {}
        # Intents held when face was busy; retried on next tick when face is free.
        # Maps event key → (phrase, expire_mono_ms).  One slot per key.
        self._held: dict[str, tuple[str, float]] = {}
        self._cooldown_ms = {
            "vision.ball_acquired": 5000.0,
            "mode.changed:WANDER": 7000.0,
            "mode.changed:IDLE": 9000.0,
            "fault.raised": 6000.0,
            "face.button.click": 4000.0,
        }
        self._phrases = {
            "vision.ball_acquired": [
                "Ooh, I see a ball!",
                "Ball spotted!",
                "I found a ball!",
            ],
            "mode.changed:WANDER": [
                "Wander mode on. Let's explore!",
                "I am going exploring now.",
                "Patrol drift started.",
            ],
            "mode.changed:IDLE": [
                "Okay, I'll pause in idle mode.",
                "Taking a little rest in idle.",
            ],
            "fault.raised": [
                "Uh oh. I need to pause for safety.",
                "I found a fault, stopping now.",
            ],
            "face.button.click": [
                "Nice click!",
                "Button press detected.",
                "Boop!",
            ],
        }

    def generate(
        self,
        *,
        state: RobotState,
        events: list[PlannerEvent],
        now_mono_ms: float,
    ) -> tuple[list[SpeechIntent], list[str]]:
        """Return speech intents and drop reasons from the provided events."""
        intents: list[SpeechIntent] = []
        drops: list[str] = []

        # Expire stale held intents.
        expired = [k for k, (_, exp) in self._held.items() if now_mono_ms > exp]
        for k in expired:
            del self._held[k]
            drops.append("policy_held_expired")

        # Flush one held intent when face becomes free.
        if not (state.face_listening or state.face_talking):
            for key, (phrase, _) in list(self._held.items()):
                if not self._on_cooldown(key, now_mono_ms):
                    self._last_spoken_ms[key] = now_mono_ms
                    del self._held[key]
                    return [
                        SpeechIntent(text=phrase, source_event=f"held:{key}")
                    ], drops

        if not events:
            return intents, drops

        # Bound output to one utterance per tick to avoid event bursts turning chatty.
        for evt in events:
            key = self._event_key(evt)
            if key is None:
                continue

            # ACTION click already runs an explicit greet routine in Runtime.
            if key == "face.button.click":
                button_id = int(evt.payload.get("button_id", -1))
                if button_id == int(FaceButtonId.ACTION):
                    continue

            if state.face_listening or state.face_talking:
                # Hold for retry rather than silently dropping.
                if key not in self._held and not self._on_cooldown(key, now_mono_ms):
                    phrase = self._next_phrase(key)
                    if phrase:
                        self._held[key] = (phrase, now_mono_ms + _FACE_BUSY_HOLD_MS)
                        drops.append("policy_face_busy_held")
                        continue
                drops.append("policy_face_busy")
                continue

            if self._on_cooldown(key, now_mono_ms):
                drops.append("policy_cooldown")
                continue

            phrase = self._next_phrase(key)
            if not phrase:
                drops.append("policy_no_phrase")
                continue

            self._last_spoken_ms[key] = now_mono_ms
            intents.append(SpeechIntent(text=phrase, source_event=evt.type))
            break

        return intents, drops

    def snapshot(self) -> dict:
        return {
            "cooldowns": dict(self._cooldown_ms),
            "last_spoken_ms": dict(self._last_spoken_ms),
            "phrase_index": dict(self._phrase_index),
            "held": {k: phrase for k, (phrase, _) in self._held.items()},
        }

    def _event_key(self, evt: PlannerEvent) -> str | None:
        if evt.type == "vision.ball_acquired":
            return "vision.ball_acquired"
        if evt.type == "fault.raised":
            return "fault.raised"
        if evt.type == "face.button.click":
            return "face.button.click"
        if evt.type == "mode.changed":
            to_mode = str(evt.payload.get("to", "")).upper()
            if to_mode == "WANDER":
                return "mode.changed:WANDER"
            if to_mode == "IDLE":
                return "mode.changed:IDLE"
        return None

    def _on_cooldown(self, key: str, now_mono_ms: float) -> bool:
        cooldown = float(self._cooldown_ms.get(key, 0.0))
        last = float(self._last_spoken_ms.get(key, -1e12))
        return (now_mono_ms - last) < cooldown

    def _next_phrase(self, key: str) -> str:
        phrases = self._phrases.get(key, [])
        if not phrases:
            return ""
        idx = int(self._phrase_index.get(key, 0))
        phrase = phrases[idx % len(phrases)]
        self._phrase_index[key] = idx + 1
        return phrase
