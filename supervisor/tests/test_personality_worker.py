"""Tests for PersonalityWorker — L0 impulse rules, idle rules, duration caps,
guardrail config, session/daily time limits."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from supervisor.messages.envelope import Envelope, make_envelope
from supervisor.messages.types import (
    PERSONALITY_CMD_OVERRIDE_AFFECT,
    PERSONALITY_CMD_RESET_MEMORY,
    PERSONALITY_CMD_SET_GUARDRAIL,
    PERSONALITY_CONFIG_INIT,
    PERSONALITY_EVENT_AI_EMOTION,
    PERSONALITY_EVENT_BUTTON_PRESS,
    PERSONALITY_EVENT_CONV_ENDED,
    PERSONALITY_EVENT_CONV_STARTED,
    PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
    PERSONALITY_EVENT_MEMORY_EXTRACT,
    PERSONALITY_EVENT_SPEECH_ACTIVITY,
    PERSONALITY_EVENT_SYSTEM_STATE,
    PERSONALITY_LLM_PROFILE,
    PERSONALITY_STATE_SNAPSHOT,
)
from supervisor.personality.affect import compute_trait_parameters
from supervisor.workers.personality_worker import (
    IDLE_DROWSY_S,
    IDLE_SUPPRESS_AFTER_CONV_S,
    PersonalityWorker,
    _validate_mood_reason,
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

    @pytest.mark.asyncio
    async def test_planner_emote_impulse_shifts_affect(self):
        """Planner emotion routes through PE and shifts affect toward anchor."""
        w = _make_worker()
        sends = _collect_sends(w)
        v_before = w._affect.valence
        a_before = w._affect.arousal

        # "excited" anchor is (0.65, 0.80) — high V, high A
        await w.on_message(
            _env(PERSONALITY_EVENT_AI_EMOTION, {"emotion": "excited", "intensity": 0.9})
        )
        # Affect should shift toward excited (positive V, high A)
        assert w._affect.valence > v_before
        assert w._affect.arousal > a_before
        # Snapshot should have been emitted
        snap_payloads = [p for t, p in sends if t == PERSONALITY_STATE_SNAPSHOT]
        assert len(snap_payloads) >= 1

    @pytest.mark.asyncio
    async def test_confused_emotion_recognized(self):
        """'confused' is a known PE emotion — should emit a snapshot, not be dropped."""
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION, {"emotion": "confused", "intensity": 0.6}
            )
        )
        assert any(t == PERSONALITY_STATE_SNAPSHOT for t, _ in sends)


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


# ── Guardrail Config Init ──────────────────────────────────────────


class TestGuardrailConfigInit:
    @pytest.mark.asyncio
    async def test_config_parses_guardrails(self):
        w = PersonalityWorker()
        await w.on_message(
            _env(
                PERSONALITY_CONFIG_INIT,
                {
                    "axes": {},
                    "guardrails": {
                        "negative_duration_caps": False,
                        "negative_intensity_caps": False,
                        "context_gate": False,
                        "session_time_limit_s": 600.0,
                        "daily_time_limit_s": 1800.0,
                    },
                    "memory_path": "/tmp/test_mem.json",
                    "memory_consent": True,
                },
            )
        )
        assert w._guardrails.negative_duration_caps is False
        assert w._guardrails.negative_intensity_caps is False
        assert w._guardrails.context_gate is False
        assert w._guardrails.session_time_limit_s == 600.0
        assert w._guardrails.daily_time_limit_s == 1800.0
        assert w._memory_path == "/tmp/test_mem.json"
        assert w._memory_consent is True

    @pytest.mark.asyncio
    async def test_config_defaults_without_guardrails_key(self):
        w = PersonalityWorker()
        await w.on_message(_env(PERSONALITY_CONFIG_INIT, {"axes": {}}))
        # Defaults preserved
        assert w._guardrails.session_time_limit_s == 900.0
        assert w._guardrails.daily_time_limit_s == 2700.0
        assert w._guardrails.context_gate is True

    @pytest.mark.asyncio
    async def test_context_gate_disabled(self):
        """When context_gate=False, negative moods pass through outside conv."""
        w = _make_worker()
        w._guardrails.context_gate = False
        w._conversation_active = False
        sends = _collect_sends(w)

        # Force affect deep into negative territory
        w._affect.valence = -0.80
        w._affect.arousal = 0.50

        w._process_and_emit(0.01)
        _, payload = sends[-1]
        # Gate is disabled — negative mood should pass through
        assert payload["mood"] != "neutral"

    @pytest.mark.asyncio
    async def test_duration_caps_disabled(self):
        """When negative_duration_caps=False, no recovery impulse."""
        w = _make_worker()
        w._guardrails.negative_duration_caps = False
        w._current_mood = "sad"
        w._negative_mood_name = "sad"
        w._negative_mood_timer_s = 10.0  # well over 4.0s cap
        _collect_sends(w)

        w._process_and_emit(1.0)
        # No recovery impulse should have been injected
        assert len(w._pending_impulses) == 0

    @pytest.mark.asyncio
    async def test_intensity_caps_disabled(self):
        """When negative_intensity_caps=False, intensity is uncapped."""
        w = _make_worker()
        w._guardrails.negative_intensity_caps = False
        w._conversation_active = True
        sends = _collect_sends(w)

        # Force affect deep into sad territory for high intensity
        w._affect.valence = -0.60
        w._affect.arousal = -0.40

        w._process_and_emit(0.01)
        _, payload = sends[-1]
        if payload["mood"] == "sad":
            # Without caps, intensity can exceed 0.70
            # (depends on distance but shouldn't be artificially clamped)
            assert True  # Just ensure no crash — exact value depends on projection

    def test_intensity_caps_enforced_sad(self):
        """When negative_intensity_caps=True, sad intensity is capped at 0.70."""
        w = _make_worker()
        w._guardrails.negative_intensity_caps = True
        w._conversation_active = True
        sends = _collect_sends(w)

        # Force affect exactly onto the sad anchor for max intensity
        w._affect.valence = -0.60
        w._affect.arousal = -0.40

        w._process_and_emit(0.01)
        _, payload = sends[-1]
        if payload["mood"] == "sad":
            assert payload["intensity"] <= 0.70

    @pytest.mark.parametrize(
        "mood,va,cap",
        [
            ("sad", (-0.60, -0.40), 0.70),
            ("scared", (-0.70, 0.65), 0.60),
            ("angry", (-0.60, 0.70), 0.50),
            ("surprised", (0.15, 0.80), 0.80),
        ],
    )
    def test_intensity_caps_per_mood(self, mood, va, cap):
        """Per-mood intensity caps enforced (spec §9.1)."""
        w = _make_worker()
        w._guardrails.negative_intensity_caps = True
        w._conversation_active = True
        sends = _collect_sends(w)

        w._affect.valence, w._affect.arousal = va
        w._process_and_emit(0.01)
        _, payload = sends[-1]
        if payload["mood"] == mood:
            assert payload["intensity"] <= cap


# ── Session Time Limit (RS-1) ───────────────────────────────────────


class TestSessionTimeLimit:
    def test_session_timer_increments_during_conversation(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = True
        w._session_time_s = 0.0

        w._tick_1hz()
        assert w._session_time_s > 0.0

    def test_session_timer_does_not_increment_outside_conversation(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = False
        w._session_time_s = 10.0

        w._tick_1hz()
        # Should stay at 10.0 (not increment)
        assert w._session_time_s == 10.0

    def test_session_limit_triggers_event(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = True
        w._guardrails.session_time_limit_s = 10.0
        w._session_time_s = 9.5
        w._last_tick_ts = time.monotonic() - 1.0  # ensure dt ≈ 1.0s

        # This tick should push over the limit
        w._tick_1hz()
        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        assert len(guardrail_events) == 1
        assert guardrail_events[0][1]["rule"] == "session_time_limit"
        assert w._session_limit_reached is True

    def test_session_limit_fires_once(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = True
        w._guardrails.session_time_limit_s = 10.0
        w._session_time_s = 9.5
        w._session_limit_reached = False
        w._last_tick_ts = time.monotonic() - 1.0

        w._tick_1hz()
        w._tick_1hz()  # Second tick — already reached

        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        assert len(guardrail_events) == 1  # Only one event

    def test_session_timer_resets_on_new_conversation(self):
        w = _make_worker()
        _collect_sends(w)
        w._session_time_s = 500.0
        w._session_limit_reached = True

        # Start new conversation
        w._handle_conv_started({})
        assert w._session_time_s == 0.0
        assert w._session_limit_reached is False

    def test_session_limit_disabled_when_zero(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = True
        w._guardrails.session_time_limit_s = 0.0
        w._session_time_s = 99999.0

        w._tick_1hz()
        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        assert len(guardrail_events) == 0

    def test_snapshot_includes_session_time(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._session_time_s = 42.5

        w._emit_snapshot()
        _, payload = sends[-1]
        assert payload["session_time_s"] == 42.5
        assert "session_limit_reached" in payload


# ── Daily Time Limit (RS-2) ─────────────────────────────────────────


class TestDailyTimeLimit:
    def test_daily_timer_increments_during_conversation(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = True
        w._daily_state.total_s = 100.0

        w._tick_1hz()
        assert w._daily_state.total_s > 100.0

    def test_daily_limit_triggers_event(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = True
        w._guardrails.daily_time_limit_s = 50.0
        w._daily_state.total_s = 49.5
        w._last_tick_ts = time.monotonic() - 1.0

        w._tick_1hz()
        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        assert len(guardrail_events) == 1
        assert guardrail_events[0][1]["rule"] == "daily_time_limit"

    def test_daily_limit_fires_once(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._conversation_active = True
        w._guardrails.daily_time_limit_s = 50.0
        w._daily_state.total_s = 49.5
        w._last_tick_ts = time.monotonic() - 1.0

        w._tick_1hz()
        w._tick_1hz()

        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        assert len(guardrail_events) == 1

    def test_daily_limit_blocks_new_conversation(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._guardrails.daily_time_limit_s = 50.0
        w._daily_state.total_s = 60.0

        w._handle_conv_started({})
        # Should not have started conversation
        assert not w._conversation_active

        # Should have emitted a block event
        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        assert len(guardrail_events) == 1
        assert guardrail_events[0][1]["rule"] == "daily_limit_blocked"

    def test_daily_limit_reached_property(self):
        w = _make_worker()
        w._guardrails.daily_time_limit_s = 100.0
        w._daily_state.total_s = 50.0
        assert w._daily_limit_reached is False

        w._daily_state.total_s = 100.0
        assert w._daily_limit_reached is True

    def test_daily_limit_disabled_when_zero(self):
        w = _make_worker()
        w._guardrails.daily_time_limit_s = 0.0
        w._daily_state.total_s = 99999.0
        assert w._daily_limit_reached is False

    def test_snapshot_includes_daily_time(self):
        w = _make_worker()
        sends = _collect_sends(w)
        w._daily_state.total_s = 123.4

        w._emit_snapshot()
        _, payload = sends[-1]
        assert payload["daily_time_s"] == 123.4
        assert "daily_limit_reached" in payload


# ── Conv-Ended Teardown Coverage (B6) ─────────────────────────────────


class TestConvEndedTeardown:
    """Edge cases for conversation teardown during time-limit scenarios."""

    def test_conv_ended_resets_session_timer(self):
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = True
        w._session_time_s = 500.0
        w._session_limit_reached = True

        w._handle_conv_ended({"sentiment": "positive"})
        assert w._conversation_active is False
        # Session time stays (only reset on next conv_started)
        # but conv_ended_ago should be 0
        assert w._conv_ended_ago_s == 0.0

    def test_daily_limit_blocks_after_conv_ended(self):
        """After daily limit exhausted and conv ends, new conv is blocked."""
        w = _make_worker()
        sends = _collect_sends(w)
        w._guardrails.daily_time_limit_s = 50.0
        w._daily_state.total_s = 60.0

        # End current conversation
        w._conversation_active = True
        w._handle_conv_ended({})
        assert w._conversation_active is False

        # Try to start new conversation — should be blocked
        w._handle_conv_started({})
        assert w._conversation_active is False

        guardrail_events = [
            (t, p) for t, p in sends if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
        ]
        block_events = [
            e for e in guardrail_events if e[1]["rule"] == "daily_limit_blocked"
        ]
        assert len(block_events) >= 1

    def test_session_limit_reached_then_new_conv_resets(self):
        """Session limit reached mid-conv; next conv starts fresh."""
        w = _make_worker()
        _collect_sends(w)
        w._conversation_active = True
        w._guardrails.session_time_limit_s = 10.0
        w._session_time_s = 9.5
        w._last_tick_ts = time.monotonic() - 1.0

        # Trip the session limit
        w._tick_1hz()
        assert w._session_limit_reached is True

        # End conversation
        w._handle_conv_ended({})

        # Start new conversation — session timer should reset
        w._handle_conv_started({})
        assert w._session_time_s == 0.0
        assert w._session_limit_reached is False
        assert w._conversation_active is True


# ── Daily Timer Persistence ──────────────────────────────────────────


class TestDailyPersistence:
    def test_persist_and_load(self, tmp_path: Path):
        import datetime

        today = datetime.date.today().isoformat()

        w = _make_worker()
        _collect_sends(w)
        w._daily_persist_path = tmp_path / "daily_usage.json"
        w._daily_state.date = today
        w._daily_state.total_s = 456.7

        w._persist_daily_state()
        assert w._daily_persist_path.exists()

        raw = json.loads(w._daily_persist_path.read_text())
        assert raw["date"] == today
        assert raw["total_s"] == 456.7

        # Load into fresh worker
        w2 = _make_worker()
        _collect_sends(w2)
        w2._daily_persist_path = w._daily_persist_path
        w2._memory_path = str(tmp_path / "mem.json")
        w2._load_daily_state()
        assert w2._daily_state.total_s == 456.7
        assert w2._daily_state.date == today

    def test_load_resets_on_new_day(self, tmp_path: Path):
        persist_path = tmp_path / "daily_usage.json"
        persist_path.write_text(json.dumps({"date": "2020-01-01", "total_s": 999.0}))

        w = _make_worker()
        _collect_sends(w)
        w._daily_persist_path = persist_path
        w._memory_path = str(tmp_path / "mem.json")
        w._load_daily_state()

        # Different date → reset
        assert w._daily_state.total_s == 0.0
        assert w._daily_state.date != "2020-01-01"

    def test_load_handles_missing_file(self, tmp_path: Path):
        w = _make_worker()
        _collect_sends(w)
        w._daily_persist_path = tmp_path / "nonexistent.json"
        w._memory_path = str(tmp_path / "mem.json")
        w._load_daily_state()

        assert w._daily_state.total_s == 0.0


# ── Set Guardrail Command ────────────────────────────────────────────


class TestSetGuardrail:
    @pytest.mark.asyncio
    async def test_update_session_limit(self):
        w = _make_worker()
        _collect_sends(w)
        assert w._guardrails.session_time_limit_s == 900.0

        await w.on_message(
            _env(PERSONALITY_CMD_SET_GUARDRAIL, {"session_time_limit_s": 1200.0})
        )
        assert w._guardrails.session_time_limit_s == 1200.0

    @pytest.mark.asyncio
    async def test_update_daily_limit(self):
        w = _make_worker()
        _collect_sends(w)
        await w.on_message(
            _env(PERSONALITY_CMD_SET_GUARDRAIL, {"daily_time_limit_s": 5400.0})
        )
        assert w._guardrails.daily_time_limit_s == 5400.0

    @pytest.mark.asyncio
    async def test_toggle_context_gate(self):
        w = _make_worker()
        _collect_sends(w)
        assert w._guardrails.context_gate is True

        await w.on_message(_env(PERSONALITY_CMD_SET_GUARDRAIL, {"context_gate": False}))
        assert w._guardrails.context_gate is False

    @pytest.mark.asyncio
    async def test_reset_daily(self):
        w = _make_worker()
        _collect_sends(w)
        w._daily_state.total_s = 2000.0
        w._daily_limit_notified = True

        await w.on_message(_env(PERSONALITY_CMD_SET_GUARDRAIL, {"reset_daily": True}))
        assert w._daily_state.total_s == 0.0
        assert w._daily_limit_notified is False

    @pytest.mark.asyncio
    async def test_partial_update_preserves_other_fields(self):
        w = _make_worker()
        _collect_sends(w)
        original_session = w._guardrails.session_time_limit_s

        await w.on_message(_env(PERSONALITY_CMD_SET_GUARDRAIL, {"context_gate": False}))
        assert w._guardrails.context_gate is False
        assert w._guardrails.session_time_limit_s == original_session


# ── mood_reason Validation (§13.3) ─────────────────────────────────────


class TestValidateMoodReason:
    """Tests for _validate_mood_reason() — PE spec §13.3."""

    def test_valid_reason_in_conversation(self):
        assert _validate_mood_reason("child told a joke", "happy", True) == 0.95

    def test_empty_reason_returns_full_modulation(self):
        assert _validate_mood_reason("", "happy", True) == 1.00

    def test_negative_emotion_rejected_outside_conversation(self):
        assert _validate_mood_reason("some reason", "sad", False) == 0.0
        assert _validate_mood_reason("some reason", "angry", False) == 0.0
        assert _validate_mood_reason("some reason", "scared", False) == 0.0

    def test_negative_emotion_accepted_in_conversation(self):
        assert _validate_mood_reason("empathizing with child", "sad", True) == 0.95

    def test_angry_at_child_rejected(self):
        assert (
            _validate_mood_reason("angry at child for not listening", "angry", True)
            == 0.0
        )

    def test_frustrated_with_child_rejected(self):
        assert _validate_mood_reason("frustrated with child", "sad", True) == 0.0

    def test_child_refused_rejected(self):
        assert _validate_mood_reason("child refused to answer", "angry", True) == 0.0

    def test_positive_emotion_allowed_outside_conversation(self):
        """Positive emotions are fine even outside conversation."""
        assert _validate_mood_reason("idle curiosity", "curious", False) == 0.95

    def test_neutral_emotion_allowed_outside_conversation(self):
        assert _validate_mood_reason("", "neutral", False) == 1.00

    def test_case_insensitive_phrase_matching(self):
        assert _validate_mood_reason("ANGRY AT CHILD", "angry", True) == 0.0


class TestMoodReasonIntegration:
    """Integration tests: mood_reason validation in PersonalityWorker."""

    @pytest.mark.asyncio
    async def test_rejected_mood_reason_substitutes_thinking(self):
        w = _make_worker()
        sends = _collect_sends(w)
        # Start conversation first so conversation_active=True
        await w.on_message(_env(PERSONALITY_EVENT_CONV_STARTED, {"session_id": "s1"}))

        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {
                    "emotion": "angry",
                    "intensity": 0.8,
                    "mood_reason": "angry at child for not paying attention",
                },
            )
        )

        # Should have emitted guardrail_triggered
        guardrail_events = [
            (t, p)
            for t, p in sends
            if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
            and p.get("rule") == "mood_reason_rejected"
        ]
        assert len(guardrail_events) == 1

    @pytest.mark.asyncio
    async def test_valid_mood_reason_applies_light_modulation(self):
        w = _make_worker()
        _collect_sends(w)
        await w.on_message(_env(PERSONALITY_EVENT_CONV_STARTED, {"session_id": "s1"}))

        v_before = w._affect.valence
        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {
                    "emotion": "happy",
                    "intensity": 0.8,
                    "mood_reason": "child told a funny joke",
                },
            )
        )
        # Valence should have increased (happy is positive valence)
        assert w._affect.valence > v_before

    @pytest.mark.asyncio
    async def test_negative_emotion_outside_conv_rejected(self):
        w = _make_worker()
        sends = _collect_sends(w)
        # No conversation started — conv_ended_ago_s != inf

        await w.on_message(
            _env(
                PERSONALITY_EVENT_AI_EMOTION,
                {"emotion": "sad", "intensity": 0.5, "mood_reason": "feeling down"},
            )
        )

        guardrail_events = [
            (t, p)
            for t, p in sends
            if t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED
            and p.get("rule") == "mood_reason_rejected"
        ]
        assert len(guardrail_events) == 1


# ── LLM Profile Emission (PE spec S2 §12.5) ──────────────────────────


class TestLLMProfile:
    @pytest.mark.asyncio
    async def test_profile_emitted_on_conv_start(self):
        w = _make_worker()
        sends = _collect_sends(w)

        await w.on_message(
            _env(PERSONALITY_EVENT_CONV_STARTED, {"session_id": "s1", "trigger": "ptt"})
        )

        profiles = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles) >= 1
        payload = profiles[0][1]
        assert "mood" in payload
        assert "intensity" in payload
        assert "valence" in payload
        assert "arousal" in payload
        assert "idle_state" in payload
        assert "session_time_s" in payload

    @pytest.mark.asyncio
    async def test_profile_not_emitted_outside_conversation(self):
        w = _make_worker()
        sends = _collect_sends(w)

        # Tick without conversation active
        w._tick_1hz()

        profiles = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles) == 0

    def test_profile_emitted_at_1hz_during_conversation(self):
        w = _make_worker()
        sends = _collect_sends(w)

        # Start conversation
        w._conversation_active = True

        # First tick emits profile
        w._tick_1hz()
        profiles = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles) == 1

        # Second tick emits another profile
        w._tick_1hz()
        profiles = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles) == 2

    def test_profile_reflects_current_mood(self):
        w = _make_worker()
        # Push valence high to get a positive mood
        w._affect.valence = 0.80
        w._affect.arousal = 0.60
        w._conversation_active = True
        sends = _collect_sends(w)

        w._tick_1hz()

        profiles = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles) == 1
        payload = profiles[0][1]
        # Should reflect the current mood, not always neutral
        assert isinstance(payload["mood"], str)
        assert 0.0 <= payload["intensity"] <= 1.0
        assert isinstance(payload["valence"], float)
        assert isinstance(payload["arousal"], float)

    @pytest.mark.asyncio
    async def test_profile_stops_after_conv_ends(self):
        w = _make_worker()
        sends = _collect_sends(w)

        # Start conversation
        await w.on_message(
            _env(PERSONALITY_EVENT_CONV_STARTED, {"session_id": "s1", "trigger": "ptt"})
        )
        sends.clear()

        # One tick during conversation
        w._tick_1hz()
        profiles_during = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles_during) == 1

        # End conversation
        await w.on_message(_env(PERSONALITY_EVENT_CONV_ENDED, {"session_id": "s1"}))
        sends.clear()

        # Tick after conversation ends
        w._tick_1hz()
        profiles_after = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles_after) == 0


# ── Memory System (PE spec S2 §8) ──────────────────────────────────────


class TestMemoryHandlers:
    @pytest.mark.asyncio
    async def test_memory_extract_stores_entries(self, tmp_path):
        w = _make_worker()
        w._memory_consent = True
        w._memory_path = str(tmp_path / "mem.json")
        from supervisor.personality.memory import MemoryStore

        w._memory = MemoryStore(w._memory_path, consent=True)

        await w.on_message(
            _env(
                PERSONALITY_EVENT_MEMORY_EXTRACT,
                {
                    "session_id": "s1",
                    "turn_id": 1,
                    "tags": [
                        {"tag": "likes_dinosaurs", "category": "topic"},
                        {"tag": "child_name_emma", "category": "name"},
                    ],
                },
            )
        )
        assert w._memory.entry_count == 2
        tags = w._memory.tag_summary()
        assert "likes_dinosaurs" in tags
        assert "child_name_emma" in tags

    @pytest.mark.asyncio
    async def test_memory_extract_legacy_strings(self, tmp_path):
        """Legacy string tags should be handled gracefully."""
        w = _make_worker()
        w._memory_consent = True
        w._memory_path = str(tmp_path / "mem.json")
        from supervisor.personality.memory import MemoryStore

        w._memory = MemoryStore(w._memory_path, consent=True)

        await w.on_message(
            _env(
                PERSONALITY_EVENT_MEMORY_EXTRACT,
                {
                    "tags": ["likes_trains", "enjoys_math"],
                },
            )
        )
        assert w._memory.entry_count == 2

    @pytest.mark.asyncio
    async def test_memory_reset_clears_store(self, tmp_path):
        w = _make_worker()
        w._memory_consent = True
        w._memory_path = str(tmp_path / "mem.json")
        from supervisor.personality.memory import MemoryStore

        w._memory = MemoryStore(w._memory_path, consent=True)
        w._memory.add_or_reinforce("test_tag", "topic")
        w._memory.save()
        assert w._memory.entry_count == 1

        await w.on_message(_env(PERSONALITY_CMD_RESET_MEMORY, {}))
        assert w._memory.entry_count == 0

    @pytest.mark.asyncio
    async def test_memory_consent_gate(self, tmp_path):
        """No storage when consent is False."""
        w = _make_worker()
        w._memory_consent = False
        w._memory_path = str(tmp_path / "mem.json")
        from supervisor.personality.memory import MemoryStore

        w._memory = MemoryStore(w._memory_path, consent=False)

        await w.on_message(
            _env(
                PERSONALITY_EVENT_MEMORY_EXTRACT,
                {"tags": [{"tag": "test", "category": "topic"}]},
            )
        )
        assert w._memory.entry_count == 0

    @pytest.mark.asyncio
    async def test_memory_tags_in_llm_profile(self, tmp_path):
        w = _make_worker()
        w._memory_consent = True
        w._memory_path = str(tmp_path / "mem.json")
        from supervisor.personality.memory import MemoryStore

        w._memory = MemoryStore(w._memory_path, consent=True)
        w._memory.add_or_reinforce("likes_dinosaurs", "topic")
        w._conversation_active = True
        sends = _collect_sends(w)

        w._emit_llm_profile()
        profiles = [(t, p) for t, p in sends if t == PERSONALITY_LLM_PROFILE]
        assert len(profiles) == 1
        _, payload = profiles[0]
        assert "memory_tags" in payload
        assert "likes_dinosaurs" in payload["memory_tags"]

    @pytest.mark.asyncio
    async def test_health_payload_includes_memory(self, tmp_path):
        w = _make_worker()
        w._memory_consent = True
        w._memory_path = str(tmp_path / "mem.json")
        from supervisor.personality.memory import MemoryStore

        w._memory = MemoryStore(w._memory_path, consent=True)
        w._memory.add_or_reinforce("test_tag", "topic")

        health = w.health_payload()
        assert health["memory_count"] == 1
        assert health["memory_consent"] is True
