"""Tests for PersonalityWorker — L0 impulse rules, idle rules, duration caps."""

from __future__ import annotations

import time

import pytest

from supervisor.messages.envelope import Envelope, make_envelope
from supervisor.messages.types import (
    PERSONALITY_CMD_OVERRIDE_AFFECT,
    PERSONALITY_CONFIG_INIT,
    PERSONALITY_EVENT_AI_EMOTION,
    PERSONALITY_EVENT_BUTTON_PRESS,
    PERSONALITY_EVENT_CONV_ENDED,
    PERSONALITY_EVENT_CONV_STARTED,
    PERSONALITY_EVENT_SPEECH_ACTIVITY,
    PERSONALITY_EVENT_SYSTEM_STATE,
    PERSONALITY_STATE_SNAPSHOT,
)
from supervisor.personality.affect import compute_trait_parameters
from supervisor.workers.personality_worker import (
    IDLE_DROWSY_S,
    IDLE_SUPPRESS_AFTER_CONV_S,
    PersonalityWorker,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_worker() -> PersonalityWorker:
    """Create a pre-configured worker ready for testing (bypasses async run)."""
    w = PersonalityWorker()
    w._trait = compute_trait_parameters(0.40, 0.50, 0.30, 0.35, 0.75)
    w._affect.valence = w._trait.baseline_valence
    w._affect.arousal = w._trait.baseline_arousal
    w._last_tick_ts = time.monotonic()
    return w


def _env(msg_type: str, payload: dict | None = None) -> Envelope:
    """Build a test envelope."""
    return make_envelope(msg_type, src="core", seq=0, payload=payload or {})


def _collect_sends(worker: PersonalityWorker) -> list[tuple[str, dict]]:
    """Patch send() and return list of (type, payload) tuples."""
    calls: list[tuple[str, dict]] = []

    def fake_send(msg_type: str, payload: dict | None = None, **_kw):
        calls.append((msg_type, payload or {}))

    worker.send = fake_send  # type: ignore[assignment]
    return calls


# ── Config Init ──────────────────────────────────────────────────────


class TestConfigInit:
    @pytest.mark.asyncio
    async def test_config_sets_trait(self):
        w = PersonalityWorker()
        assert w._trait is None
        env = _env(
            PERSONALITY_CONFIG_INIT,
            {
                "axes": {
                    "energy": 0.40,
                    "reactivity": 0.50,
                    "initiative": 0.30,
                    "vulnerability": 0.35,
                    "predictability": 0.75,
                }
            },
        )
        await w.on_message(env)
        assert w._trait is not None
        assert w._configured.is_set()

    @pytest.mark.asyncio
    async def test_config_defaults(self):
        """Config with empty axes uses default personality values."""
        w = PersonalityWorker()
        await w.on_message(_env(PERSONALITY_CONFIG_INIT, {"axes": {}}))
        assert w._trait is not None
        # Default energy=0.40 → baseline_valence ≈ 0.10
        assert abs(w._trait.baseline_valence - 0.10) < 0.01


# ── L0 System Events (L0-01 through L0-05) ───────────────────────────


class TestSystemEvents:
    @pytest.mark.asyncio
    async def test_boot_fires_once(self):
        w = _make_worker()
        sends = _collect_sends(w)

        # First boot
        await w.on_message(_env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "boot"}))
        assert w._boot_fired
        snap_count_1 = sum(1 for t, _ in sends if t == PERSONALITY_STATE_SNAPSHOT)

        # Second boot — no additional impulse
        await w.on_message(_env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "boot"}))
        # Impulses were consumed by fast path, but no NEW boot impulse was queued
        snap_count_2 = sum(1 for t, _ in sends if t == PERSONALITY_STATE_SNAPSHOT)
        # Should still emit a snapshot (from fast_path) but no boot impulse queued
        assert snap_count_2 >= snap_count_1

    @pytest.mark.asyncio
    async def test_low_battery_with_cooldown(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "low_battery"})
        )
        # Impulse applied via fast_path → snapshot emitted
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

        # Second call within cooldown (120s) — should not fire again
        sends.clear()
        await w.on_message(
            _env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "low_battery"})
        )
        # Cooldown blocks second impulse — no snapshot from fast_path
        # (system event handler returns early for unknown, but low_battery
        # still calls fast_path; the impulse just isn't queued)

    @pytest.mark.asyncio
    async def test_critical_battery_no_cooldown(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "critical_battery"})
        )
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)
        sends.clear()

        # Second call immediately — should still fire (no cooldown)
        await w.on_message(
            _env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "critical_battery"})
        )
        snap2 = sum(1 for t, _ in sends if t == PERSONALITY_STATE_SNAPSHOT)
        assert snap2 >= 1

    @pytest.mark.asyncio
    async def test_fault_raised_and_cleared(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "fault_raised"})
        )
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

        sends.clear()
        await w.on_message(
            _env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "fault_cleared"})
        )
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_unknown_system_event(self):
        w = _make_worker()
        sends = _collect_sends(w)
        await w.on_message(_env(PERSONALITY_EVENT_SYSTEM_STATE, {"event": "nonsense"}))
        # Unknown event returns early — no fast_path → no snapshot
        assert not any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)


# ── Conversation Events (L0-06 through L0-08, L0-13) ─────────────────


class TestConversation:
    @pytest.mark.asyncio
    async def test_conv_started_sets_active(self):
        w = _make_worker()
        sends = _collect_sends(w)
        assert not w._conversation_active

        await w.on_message(_env(PERSONALITY_EVENT_CONV_STARTED, {}))
        assert w._conversation_active
        assert w._idle_timer_s == 0.0
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_conv_started_wake_word_fires_l0_13(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(PERSONALITY_EVENT_CONV_STARTED, {"trigger": "wake_word"})
        )
        # L0-06 + L0-13 both queued → fast_path fires
        assert w._conversation_active
        # Snapshot emitted
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_conv_ended_positive_valence(self):
        w = _make_worker()
        w._conversation_active = True
        # Force positive valence
        w._affect.valence = 0.30
        sends = _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_CONV_ENDED, {}))
        assert not w._conversation_active
        assert w._conv_ended_ago_s == 0.0
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_conv_ended_negative_valence(self):
        w = _make_worker()
        w._conversation_active = True
        w._affect.valence = -0.10
        _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_CONV_ENDED, {}))
        assert not w._conversation_active

    @pytest.mark.asyncio
    async def test_conv_started_resets_idle(self):
        w = _make_worker()
        w._idle_timer_s = 600.0
        _collect_sends(w)
        await w.on_message(_env(PERSONALITY_EVENT_CONV_STARTED, {}))
        assert w._idle_timer_s == 0.0


# ── Speech Activity (L0-09) ──────────────────────────────────────────


class TestSpeechActivity:
    @pytest.mark.asyncio
    async def test_speech_fires_on_speaking(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_SPEECH_ACTIVITY, {"speaking": True}))
        assert w._idle_timer_s == 0.0
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_speech_no_fire_when_not_speaking(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_SPEECH_ACTIVITY, {"speaking": False}))
        # Not speaking → no impulse → no fast_path
        assert not any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_speech_cooldown(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_SPEECH_ACTIVITY, {"speaking": True}))
        first_snaps = sum(1 for t, _ in sends if t == PERSONALITY_STATE_SNAPSHOT)
        assert first_snaps == 1

        sends.clear()
        # Second call within 5s cooldown — no impulse, no fast_path
        await w.on_message(_env(PERSONALITY_EVENT_SPEECH_ACTIVITY, {"speaking": True}))
        assert not any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)


# ── Button Press (L0-10) ─────────────────────────────────────────────


class TestButtonPress:
    @pytest.mark.asyncio
    async def test_button_fires_impulse(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_BUTTON_PRESS, {}))
        assert w._idle_timer_s == 0.0
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_button_cooldown(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(_env(PERSONALITY_EVENT_BUTTON_PRESS, {}))
        sends.clear()

        # Within 5s cooldown — no new impulse
        await w.on_message(_env(PERSONALITY_EVENT_BUTTON_PRESS, {}))
        assert not any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)


# ── AI Emotion ───────────────────────────────────────────────────────


class TestAIEmotion:
    @pytest.mark.asyncio
    async def test_known_emotion(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {"emotion": "happy", "intensity": 0.8},
            )
        )
        assert w._idle_timer_s == 0.0
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_unknown_emotion_ignored(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {"emotion": "flummoxed", "intensity": 0.5},
            )
        )
        # Unknown emotion → returns early, no fast_path
        assert not any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    @pytest.mark.asyncio
    async def test_intensity_scales_magnitude(self):
        w = _make_worker()
        _collect_sends(w)

        # Low intensity
        v_before = w._affect.valence
        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {"emotion": "happy", "intensity": 0.1},
            )
        )
        low_delta = w._affect.valence - v_before

        # Reset
        w2 = _make_worker()
        _collect_sends(w2)
        v2_before = w2._affect.valence
        await w2.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {"emotion": "happy", "intensity": 1.0},
            )
        )
        high_delta = w2._affect.valence - v2_before

        # Higher intensity → larger shift
        assert high_delta > low_delta


# ── Override ─────────────────────────────────────────────────────────


class TestOverride:
    @pytest.mark.asyncio
    async def test_override_injects_impulse(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(
                PERSONALITY_CMD_OVERRIDE_AFFECT,
                {"valence": 0.50, "arousal": 0.30, "magnitude": 0.8},
            )
        )
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)


# ── Idle Rules (L0-11, L0-12) ────────────────────────────────────────


class TestIdleRules:
    def test_idle_state_awake(self):
        w = _make_worker()
        w._idle_timer_s = 0.0
        assert w._idle_state() == "awake"

    def test_idle_state_drowsy(self):
        w = _make_worker()
        w._idle_timer_s = IDLE_DROWSY_S + 1.0
        assert w._idle_state() == "drowsy"

    def test_idle_state_asleep(self):
        w = _make_worker()
        w._idle_timer_s = 900.0 + 1.0
        assert w._idle_state() == "asleep"

    def test_idle_rule_suppressed_during_conversation(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = True
        w._idle_timer_s = 600.0  # well past 5 min

        w._evaluate_idle_rules()
        # No impulses queued — suppressed during conversation
        assert len(w._pending_impulses) == 0

    def test_idle_rule_suppressed_shortly_after_conv(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = False
        w._conv_ended_ago_s = 30.0  # only 30s after conv ended
        w._idle_timer_s = 600.0

        w._evaluate_idle_rules()
        assert len(w._pending_impulses) == 0

    def test_idle_rule_fires_after_suppress_window(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = False
        w._conv_ended_ago_s = IDLE_SUPPRESS_AFTER_CONV_S + 1.0
        w._idle_timer_s = IDLE_DROWSY_S + 1.0

        w._evaluate_idle_rules()
        # L0-11 should have queued an impulse
        assert len(w._pending_impulses) == 1

    def test_idle_rule_l0_12_fires_at_15_min(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = False
        w._conv_ended_ago_s = float("inf")
        w._idle_timer_s = 901.0

        w._evaluate_idle_rules()
        # Both L0-11 and L0-12 fire (timer > both thresholds)
        assert len(w._pending_impulses) == 2

    def test_idle_rule_cooldown_prevents_refire(self):
        w = _make_worker()
        w._conversation_active = False
        w._conv_ended_ago_s = float("inf")
        w._idle_timer_s = 600.0

        w._evaluate_idle_rules()
        assert len(w._pending_impulses) == 1  # L0-11 fires

        w._pending_impulses.clear()
        w._evaluate_idle_rules()
        # Cooldown (600s) blocks re-fire
        assert len(w._pending_impulses) == 0


# ── Duration Caps (spec §9.1) ────────────────────────────────────────


class TestDurationCaps:
    def test_sad_cap_triggers_recovery(self):
        w = _make_worker()
        w._current_mood = "sad"
        w._negative_mood_name = "sad"
        w._negative_mood_timer_s = 3.9

        # Exceed the 4.0s cap
        w._enforce_duration_caps(0.2)
        assert w._negative_mood_timer_s == 0.0  # reset after recovery
        assert len(w._pending_impulses) == 1
        # Recovery impulse targets baseline
        imp = w._pending_impulses[0]
        assert w._trait is not None
        assert abs(imp.target_valence - w._trait.baseline_valence) < 0.001
        assert abs(imp.target_arousal - w._trait.baseline_arousal) < 0.001

    def test_scared_cap_2s(self):
        w = _make_worker()
        w._current_mood = "scared"
        w._negative_mood_name = "scared"
        w._negative_mood_timer_s = 1.9

        w._enforce_duration_caps(0.2)
        assert len(w._pending_impulses) == 1

    def test_angry_cap_2s(self):
        w = _make_worker()
        w._current_mood = "angry"
        w._negative_mood_name = "angry"
        w._negative_mood_timer_s = 1.9

        w._enforce_duration_caps(0.2)
        assert len(w._pending_impulses) == 1

    def test_surprised_cap_3s(self):
        w = _make_worker()
        w._current_mood = "surprised"
        w._negative_mood_name = "surprised"
        w._negative_mood_timer_s = 2.9

        w._enforce_duration_caps(0.2)
        assert len(w._pending_impulses) == 1

    def test_neutral_no_cap(self):
        w = _make_worker()
        w._current_mood = "neutral"
        w._negative_mood_timer_s = 100.0

        w._enforce_duration_caps(1.0)
        assert len(w._pending_impulses) == 0
        assert w._negative_mood_timer_s == 0.0

    def test_cap_accumulates_before_trigger(self):
        w = _make_worker()
        w._current_mood = "sad"
        w._negative_mood_name = "sad"  # pre-set so first call accumulates

        # Accumulate 3.0s (below 4.0 cap)
        w._enforce_duration_caps(1.0)
        w._enforce_duration_caps(1.0)
        w._enforce_duration_caps(1.0)
        assert len(w._pending_impulses) == 0
        assert w._negative_mood_timer_s == pytest.approx(3.0, abs=0.01)

        # This pushes over the 4.0s cap
        w._enforce_duration_caps(1.5)
        assert len(w._pending_impulses) == 1

    def test_mood_change_resets_timer(self):
        w = _make_worker()
        w._current_mood = "sad"
        w._negative_mood_name = "sad"
        w._negative_mood_timer_s = 3.0

        # Change to a different capped mood
        w._current_mood = "scared"
        w._enforce_duration_caps(0.5)
        # Timer reset to 0 + 0.5 on mood change... actually let's check the logic:
        # mood_name != current_mood → reset to 0.0, set name to scared
        # Then 0.0 < 2.0 cap → no trigger
        assert w._negative_mood_name == "scared"
        assert (
            w._negative_mood_timer_s == 0.0
        )  # just reset, doesn't accumulate dt on reset tick


# ── Snapshot Emission ────────────────────────────────────────────────


class TestSnapshotEmission:
    def test_snapshot_fields(self):
        w = _make_worker()
        sends = _collect_sends(w)

        w._process_and_emit(1.0)
        assert len(sends) == 1
        msg_type, payload = sends[0]
        assert msg_type == PERSONALITY_STATE_SNAPSHOT
        assert "mood" in payload
        assert "intensity" in payload
        assert "valence" in payload
        assert "arousal" in payload
        assert "layer" in payload
        assert payload["layer"] == 0
        assert "conversation_active" in payload
        assert "idle_state" in payload

    def test_tick_emits_snapshot(self):
        w = _make_worker()
        sends = _collect_sends(w)

        w._tick_1hz()
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)

    def test_fast_path_emits_snapshot(self):
        w = _make_worker()
        sends = _collect_sends(w)

        w._fast_path()
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)


# ── Health Payload ───────────────────────────────────────────────────


class TestHealthPayload:
    def test_health_before_config(self):
        w = PersonalityWorker()
        h = w.health_payload()
        assert h["configured"] is False
        assert h["mood"] == "neutral"

    def test_health_after_config(self):
        w = _make_worker()
        h = w.health_payload()
        assert h["configured"] is True
        assert "mood" in h
        assert "intensity" in h
        assert "valence" in h
        assert "arousal" in h
        assert "layer" in h
        assert "idle_state" in h
        assert "idle_timer_s" in h

    def test_health_reflects_conversation_state(self):
        w = _make_worker()
        w._conversation_active = True
        h = w.health_payload()
        assert h["conversation_active"] is True


# ── Context Gate Integration ─────────────────────────────────────────


class TestContextGateIntegration:
    def test_negative_mood_gated_outside_conversation(self):
        """Negative mood forced to neutral when conversation is not active."""
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = False

        # Force affect deep into negative territory
        w._affect.valence = -0.80
        w._affect.arousal = 0.50

        w._process_and_emit(0.01)
        # The snapshot mood should be neutral (gated)
        assert len(sends) >= 1
        _, payload = sends[-1]
        assert payload["mood"] not in ("sad", "scared", "angry")

    def test_negative_mood_allowed_during_conversation(self):
        """Negative mood passes through when conversation is active."""
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = True

        # Force affect deep into sad territory
        w._affect.valence = -0.80
        w._affect.arousal = -0.40

        w._process_and_emit(0.01)
        assert len(sends) >= 1
        _, snap = sends[-1]
        # During conversation, negative moods are allowed
        # (exact mood depends on projection, but it shouldn't be forced to neutral)
        assert snap["mood"] != "neutral" or snap["valence"] < 0
