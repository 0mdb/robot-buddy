"""Tests for negative affect guardrails."""

from __future__ import annotations

from supervisor.core.guardrails import (
    INTENSITY_CAP,
    NEGATIVE_MOOD_IDS,
    Guardrails,
)
from supervisor.devices.protocol import FaceMood

NEUTRAL = int(FaceMood.NEUTRAL)
HAPPY = int(FaceMood.HAPPY)
EXCITED = int(FaceMood.EXCITED)
SAD = int(FaceMood.SAD)
SCARED = int(FaceMood.SCARED)
ANGRY = int(FaceMood.ANGRY)
SURPRISED = int(FaceMood.SURPRISED)
CURIOUS = int(FaceMood.CURIOUS)
THINKING = int(FaceMood.THINKING)


# ── Context gate ─────────────────────────────────────────────────


class TestContextGate:
    def test_sad_blocked_outside_conversation(self):
        g = Guardrails()
        mood, intensity = g.check(SAD, 0.7, conversation_active=False, now=0.0)
        assert mood == NEUTRAL
        assert intensity == 0.0

    def test_scared_blocked_outside_conversation(self):
        g = Guardrails()
        mood, _ = g.check(SCARED, 0.6, conversation_active=False, now=0.0)
        assert mood == NEUTRAL

    def test_angry_blocked_outside_conversation(self):
        g = Guardrails()
        mood, _ = g.check(ANGRY, 0.5, conversation_active=False, now=0.0)
        assert mood == NEUTRAL

    def test_sad_allowed_during_conversation(self):
        g = Guardrails()
        mood, _ = g.check(SAD, 0.7, conversation_active=True, now=0.0)
        assert mood == SAD

    def test_scared_allowed_during_conversation(self):
        g = Guardrails()
        mood, _ = g.check(SCARED, 0.6, conversation_active=True, now=0.0)
        assert mood == SCARED

    def test_angry_allowed_during_conversation(self):
        g = Guardrails()
        mood, _ = g.check(ANGRY, 0.5, conversation_active=True, now=0.0)
        assert mood == ANGRY

    def test_happy_allowed_outside_conversation(self):
        g = Guardrails()
        mood, _ = g.check(HAPPY, 1.0, conversation_active=False, now=0.0)
        assert mood == HAPPY

    def test_neutral_allowed_outside_conversation(self):
        g = Guardrails()
        mood, _ = g.check(NEUTRAL, 1.0, conversation_active=False, now=0.0)
        assert mood == NEUTRAL

    def test_surprised_not_context_gated(self):
        """SURPRISED is not in NEGATIVE_MOODS (reclassified as Neutral class)."""
        g = Guardrails()
        assert SURPRISED not in NEGATIVE_MOOD_IDS
        mood, _ = g.check(SURPRISED, 0.8, conversation_active=False, now=0.0)
        assert mood == SURPRISED

    def test_curious_allowed_outside_conversation(self):
        g = Guardrails()
        mood, _ = g.check(CURIOUS, 0.8, conversation_active=False, now=0.0)
        assert mood == CURIOUS


# ── Intensity cap ────────────────────────────────────────────────


class TestIntensityCap:
    def test_angry_capped_at_0_5(self):
        g = Guardrails()
        _, intensity = g.check(ANGRY, 1.0, conversation_active=True, now=0.0)
        assert intensity == INTENSITY_CAP[ANGRY]
        assert intensity == 0.5

    def test_scared_capped_at_0_6(self):
        g = Guardrails()
        _, intensity = g.check(SCARED, 1.0, conversation_active=True, now=0.0)
        assert intensity == 0.6

    def test_sad_capped_at_0_7(self):
        g = Guardrails()
        _, intensity = g.check(SAD, 1.0, conversation_active=True, now=0.0)
        assert intensity == 0.7

    def test_surprised_capped_at_0_8(self):
        g = Guardrails()
        _, intensity = g.check(SURPRISED, 0.9, conversation_active=True, now=0.0)
        assert intensity == 0.8

    def test_happy_not_capped(self):
        g = Guardrails()
        _, intensity = g.check(HAPPY, 1.0, conversation_active=True, now=0.0)
        assert intensity == 1.0

    def test_intensity_below_cap_unchanged(self):
        g = Guardrails()
        _, intensity = g.check(ANGRY, 0.3, conversation_active=True, now=0.0)
        assert intensity == 0.3


# ── Duration cap ─────────────────────────────────────────────────


class TestDurationCap:
    def test_angry_recovers_after_2s(self):
        g = Guardrails()
        g.check(ANGRY, 0.5, conversation_active=True, now=0.0)
        mood, _ = g.check(ANGRY, 0.5, conversation_active=True, now=2.1)
        assert mood == NEUTRAL

    def test_scared_recovers_after_2s(self):
        g = Guardrails()
        g.check(SCARED, 0.6, conversation_active=True, now=0.0)
        mood, _ = g.check(SCARED, 0.6, conversation_active=True, now=2.1)
        assert mood == NEUTRAL

    def test_sad_recovers_after_4s(self):
        g = Guardrails()
        g.check(SAD, 0.7, conversation_active=True, now=0.0)
        mood, _ = g.check(SAD, 0.7, conversation_active=True, now=4.1)
        assert mood == NEUTRAL

    def test_surprised_recovers_after_3s(self):
        g = Guardrails()
        g.check(SURPRISED, 0.8, conversation_active=True, now=0.0)
        mood, _ = g.check(SURPRISED, 0.8, conversation_active=True, now=3.1)
        assert mood == NEUTRAL

    def test_happy_no_duration_cap(self):
        g = Guardrails()
        g.check(HAPPY, 1.0, conversation_active=True, now=0.0)
        mood, _ = g.check(HAPPY, 1.0, conversation_active=True, now=100.0)
        assert mood == HAPPY

    def test_within_duration_no_recovery(self):
        g = Guardrails()
        g.check(ANGRY, 0.5, conversation_active=True, now=0.0)
        mood, _ = g.check(ANGRY, 0.5, conversation_active=True, now=1.0)
        assert mood == ANGRY

    def test_recovery_fires_once(self):
        g = Guardrails()
        g.check(ANGRY, 0.5, conversation_active=True, now=0.0)
        # First check after cap: fires
        mood1, _ = g.check(ANGRY, 0.5, conversation_active=True, now=2.1)
        assert mood1 == NEUTRAL
        # Second check with same mood: _fired prevents re-fire
        # (mood changed to NEUTRAL via return, but internal _current stays ANGRY
        #  until we actually pass a different mood_id — but the RETURN is NEUTRAL)
        # If caller feeds ANGRY again:
        mood2, _ = g.check(ANGRY, 0.5, conversation_active=True, now=3.0)
        # Same mood_id, _fired is True, no re-fire — passes through with cap
        assert mood2 == ANGRY
        assert g._fired

    def test_mood_change_resets_fired_flag(self):
        g = Guardrails()
        g.check(ANGRY, 0.5, conversation_active=True, now=0.0)
        g.check(ANGRY, 0.5, conversation_active=True, now=2.1)  # fires
        assert g._fired
        # Change to different mood
        g.check(HAPPY, 1.0, conversation_active=True, now=3.0)
        assert not g._fired


# ── Combined ─────────────────────────────────────────────────────


class TestCombined:
    def test_angry_outside_conversation_context_gate_takes_priority(self):
        """Context gate fires before intensity/duration cap checks."""
        g = Guardrails()
        mood, intensity = g.check(ANGRY, 1.0, conversation_active=False, now=0.0)
        assert mood == NEUTRAL
        assert intensity == 0.0

    def test_angry_in_conversation_gets_both_caps(self):
        g = Guardrails()
        # Start angry
        _, intensity = g.check(ANGRY, 1.0, conversation_active=True, now=0.0)
        assert intensity == 0.5  # intensity cap
        # After duration
        mood, _ = g.check(ANGRY, 1.0, conversation_active=True, now=2.1)
        assert mood == NEUTRAL  # duration cap

    def test_neutral_passes_through_unchanged(self):
        g = Guardrails()
        mood, intensity = g.check(NEUTRAL, 1.0, conversation_active=False, now=0.0)
        assert mood == NEUTRAL
        assert intensity == 1.0

    def test_thinking_passes_through(self):
        g = Guardrails()
        mood, intensity = g.check(THINKING, 0.5, conversation_active=True, now=0.0)
        assert mood == THINKING
        assert intensity == 0.5
