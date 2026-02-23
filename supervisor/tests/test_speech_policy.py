"""Tests for SpeechPolicy, including the face-busy hold queue."""

from __future__ import annotations

from supervisor.core.event_bus import PlannerEvent
from supervisor.core.speech_policy import SpeechPolicy, _FACE_BUSY_HOLD_MS
from supervisor.core.state import RobotState


# ── helpers ──────────────────────────────────────────────────────────────────


def _mode_event(to_mode: str, t: float = 0.0) -> PlannerEvent:
    return PlannerEvent("mode.changed", {"from": "IDLE", "to": to_mode}, t)


def _ball_event(t: float = 0.0) -> PlannerEvent:
    return PlannerEvent(
        "vision.ball_acquired", {"confidence": 0.9, "bearing_deg": 10.0}, t
    )


def _state(*, talking: bool = False, listening: bool = False) -> RobotState:
    s = RobotState()
    s.face_talking = talking
    s.face_listening = listening
    return s


def _free_state() -> RobotState:
    return _state()


# ── basic generate() behaviour ────────────────────────────────────────────────


class TestBasicGenerate:
    def test_no_events_returns_empty(self):
        p = SpeechPolicy()
        intents, drops = p.generate(state=_free_state(), events=[], now_mono_ms=0.0)
        assert intents == []
        assert drops == []

    def test_mode_change_fires_intent(self):
        p = SpeechPolicy()
        intents, drops = p.generate(
            state=_free_state(), events=[_mode_event("WANDER")], now_mono_ms=0.0
        )
        assert len(intents) == 1
        assert (
            "explore" in intents[0].text.lower() or "wander" in intents[0].text.lower()
        )
        assert drops == []

    def test_cooldown_drops_second_event(self):
        p = SpeechPolicy()
        p.generate(state=_free_state(), events=[_mode_event("WANDER")], now_mono_ms=0.0)
        intents, drops = p.generate(
            state=_free_state(), events=[_mode_event("WANDER")], now_mono_ms=100.0
        )
        assert intents == []
        assert "policy_cooldown" in drops


# ── face-busy hold queue ──────────────────────────────────────────────────────


class TestFaceBusyHold:
    def test_face_busy_holds_intent(self):
        """Intent is stored in _held rather than silently dropped."""
        p = SpeechPolicy()
        intents, drops = p.generate(
            state=_state(talking=True), events=[_mode_event("WANDER")], now_mono_ms=0.0
        )
        assert intents == []
        assert "policy_face_busy_held" in drops
        assert "mode.changed:WANDER" in p._held

    def test_held_intent_retried_when_free(self):
        """Held intent is emitted on next tick when face becomes free."""
        p = SpeechPolicy()
        # First tick: face talking, intent is held
        p.generate(
            state=_state(talking=True), events=[_mode_event("WANDER")], now_mono_ms=0.0
        )
        assert "mode.changed:WANDER" in p._held

        # Second tick: face free, held intent flushed
        intents, drops = p.generate(state=_free_state(), events=[], now_mono_ms=100.0)
        assert len(intents) == 1
        assert intents[0].source_event == "held:mode.changed:WANDER"
        assert "mode.changed:WANDER" not in p._held

    def test_held_intent_expires(self):
        """Held intent is discarded after _FACE_BUSY_HOLD_MS ms."""
        p = SpeechPolicy()
        p.generate(
            state=_state(talking=True), events=[_mode_event("WANDER")], now_mono_ms=0.0
        )

        # Advance past expiry window
        intents, drops = p.generate(
            state=_free_state(),
            events=[],
            now_mono_ms=_FACE_BUSY_HOLD_MS + 1.0,
        )
        assert intents == []
        assert "policy_held_expired" in drops
        assert "mode.changed:WANDER" not in p._held

    def test_no_duplicate_hold(self):
        """Second event with the same key while already held is not added again."""
        p = SpeechPolicy()
        p.generate(
            state=_state(talking=True), events=[_mode_event("WANDER")], now_mono_ms=0.0
        )
        first_phrase = p._held["mode.changed:WANDER"][0]

        # Same event arrives again while still held
        _, drops = p.generate(
            state=_state(talking=True), events=[_mode_event("WANDER")], now_mono_ms=50.0
        )
        assert "policy_face_busy" in drops
        # Phrase unchanged — first capture wins
        assert p._held["mode.changed:WANDER"][0] == first_phrase

    def test_face_busy_then_still_busy_then_free(self):
        """Intent survives multiple busy ticks before being flushed."""
        p = SpeechPolicy()
        p.generate(state=_state(talking=True), events=[_ball_event()], now_mono_ms=0.0)

        # Still busy on tick 2
        intents, _ = p.generate(
            state=_state(talking=True), events=[], now_mono_ms=100.0
        )
        assert intents == []

        # Face free on tick 3
        intents, _ = p.generate(state=_free_state(), events=[], now_mono_ms=200.0)
        assert len(intents) == 1
        assert intents[0].source_event == "held:vision.ball_acquired"

    def test_held_intent_respects_cooldown(self):
        """Held intent is not flushed while the event key is still on cooldown."""
        p = SpeechPolicy()
        # Speak first, then face goes busy with same event again
        p.generate(state=_free_state(), events=[_ball_event()], now_mono_ms=0.0)
        # Now face is busy and ball event fires again (within cooldown window)
        p.generate(
            state=_state(talking=True), events=[_ball_event()], now_mono_ms=100.0
        )

        # Face becomes free but cooldown not elapsed → no held flush, no new speech
        intents, drops = p.generate(state=_free_state(), events=[], now_mono_ms=200.0)
        assert intents == []


# ── snapshot ──────────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_includes_held(self):
        p = SpeechPolicy()
        p.generate(
            state=_state(talking=True), events=[_mode_event("WANDER")], now_mono_ms=0.0
        )
        snap = p.snapshot()
        assert "held" in snap
        assert "mode.changed:WANDER" in snap["held"]

    def test_snapshot_held_empty_when_clear(self):
        p = SpeechPolicy()
        snap = p.snapshot()
        assert snap["held"] == {}
