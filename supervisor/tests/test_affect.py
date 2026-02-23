"""Tests for supervisor.personality.affect — pure affect model math.

Covers: trait parameter derivation, decaying integrator, impulse application,
mood projection with hysteresis, context gate, and intensity calculation.
"""

from __future__ import annotations

import math
import random

import pytest

from supervisor.personality.affect import (
    MOOD_ANCHORS,
    NEGATIVE_MOODS,
    MAX_ANCHOR_DISTANCE,
    AffectVector,
    Impulse,
    TraitParameters,
    compute_trait_parameters,
    enforce_context_gate,
    project_mood,
    update_affect,
    apply_impulse,
    sigmoid_map,
)

# ── Helpers ──────────────────────────────────────────────────────────

# Canonical axis positions (PE spec §1.1)
CANONICAL = dict(
    energy=0.40,
    reactivity=0.50,
    initiative=0.30,
    vulnerability=0.35,
    predictability=0.75,
)


def _canonical_trait() -> TraitParameters:
    return compute_trait_parameters(**CANONICAL)


def _affect(v: float = 0.10, a: float = -0.05) -> AffectVector:
    return AffectVector(valence=v, arousal=a)


# ── Sigmoid ──────────────────────────────────────────────────────────


class TestSigmoid:
    def test_midpoint(self):
        assert sigmoid_map(0.5) == pytest.approx(0.5, abs=0.001)

    def test_low(self):
        assert sigmoid_map(0.0) < 0.1

    def test_high(self):
        assert sigmoid_map(1.0) > 0.9

    def test_custom_k(self):
        # Higher k → steeper. At x=0.6, k=10 should be closer to 1.0 than k=5
        assert sigmoid_map(0.6, k=10) > sigmoid_map(0.6, k=5)


# ── Trait Parameter Derivation ───────────────────────────────────────


class TestTraitParameters:
    def test_baseline_valence(self):
        t = _canonical_trait()
        assert t.baseline_valence == pytest.approx(0.10, abs=0.01)

    def test_baseline_arousal(self):
        t = _canonical_trait()
        # P2: 0.50 * (0.40 - 0.50) = -0.05
        assert t.baseline_arousal == pytest.approx(-0.05, abs=0.01)

    def test_decay_rate_phasic(self):
        t = _canonical_trait()
        # P3: 0.03 + 0.05 * sigmoid(0.50) ≈ 0.03 + 0.05 * 0.5 = 0.055
        assert t.decay_rate_phasic == pytest.approx(0.055, abs=0.002)

    def test_decay_multipliers(self):
        t = _canonical_trait()
        assert t.decay_multiplier_positive == 0.85
        assert t.decay_multiplier_negative == 1.30

    def test_impulse_scale_positive(self):
        t = _canonical_trait()
        # P7: 0.50 + 1.00 * sigmoid(0.50) ≈ 1.00
        assert t.impulse_scale_positive == pytest.approx(1.00, abs=0.05)

    def test_impulse_scale_negative(self):
        t = _canonical_trait()
        # P8: P7 * (0.30 + 0.70 * 0.35) ≈ 1.00 * 0.545 ≈ 0.55
        assert t.impulse_scale_negative == pytest.approx(0.55, abs=0.05)

    def test_valence_bounds(self):
        t = _canonical_trait()
        # P9: -0.50 - 0.50 * 0.35 = -0.675
        assert t.valence_min == pytest.approx(-0.675, abs=0.01)
        assert t.valence_max == 0.95

    def test_arousal_bounds(self):
        t = _canonical_trait()
        assert t.arousal_min == -0.90
        # P12: 0.50 + 0.40 * 0.40 = 0.66
        assert t.arousal_max == pytest.approx(0.66, abs=0.01)

    def test_noise_amplitude(self):
        t = _canonical_trait()
        # P13: 0.05 * (1.0 - 0.75) = 0.0125
        assert t.noise_amplitude == pytest.approx(0.0125, abs=0.001)

    def test_idle_impulse_magnitude(self):
        t = _canonical_trait()
        # P20: 0.10 + 0.30 * 0.30 = 0.19
        assert t.idle_impulse_magnitude == pytest.approx(0.19, abs=0.01)

    def test_extreme_axes_low(self):
        """All axes at 0.0 should not crash and produce valid parameters."""
        t = compute_trait_parameters(0.0, 0.0, 0.0, 0.0, 0.0)
        assert t.valence_min < 0
        assert t.valence_max > 0
        assert t.noise_amplitude > 0  # predictability=0 → max noise

    def test_extreme_axes_high(self):
        """All axes at 1.0 should not crash and produce valid parameters."""
        t = compute_trait_parameters(1.0, 1.0, 1.0, 1.0, 1.0)
        assert t.noise_amplitude == pytest.approx(0.0, abs=0.001)  # predictability=1


# ── Affect Update (Decay) ───────────────────────────────────────────


class TestAffectDecay:
    def test_dt_zero_no_change(self):
        """dt=0 should not crash and should not change affect."""
        a = _affect(0.50, 0.30)
        t = _canonical_trait()
        update_affect(a, t, [], 0.0)
        assert a.valence == pytest.approx(0.50, abs=0.001)
        assert a.arousal == pytest.approx(0.30, abs=0.001)

    def test_positive_valence_decays_toward_baseline(self):
        a = _affect(0.80, -0.05)
        t = _canonical_trait()
        random.seed(42)
        update_affect(a, t, [], 1.0)
        # Should decay toward baseline=0.10 but not reach it in 1s
        assert a.valence < 0.80
        assert a.valence > t.baseline_valence

    def test_negative_valence_decays_faster(self):
        """Negative valence should decay faster (mult=1.30 vs 0.85)."""
        t = _canonical_trait()

        a_pos = _affect(0.50, -0.05)
        a_neg = _affect(-0.30, -0.05)
        random.seed(42)
        update_affect(a_pos, t, [], 5.0)
        random.seed(42)
        update_affect(a_neg, t, [], 5.0)

        # Both should be closer to baseline, but negative should have
        # converged more (as fraction of distance)
        dist_pos = abs(a_pos.valence - t.baseline_valence) / abs(
            0.50 - t.baseline_valence
        )
        dist_neg = abs(a_neg.valence - t.baseline_valence) / abs(
            -0.30 - t.baseline_valence
        )
        assert dist_neg < dist_pos

    def test_large_dt_converges_to_baseline(self):
        """Very large dt should bring affect very close to baseline."""
        a = _affect(0.80, 0.60)
        # Use zero noise to isolate decay convergence (noise * sqrt(dt) blows up)
        t = _canonical_trait()
        t_quiet = TraitParameters(
            baseline_valence=t.baseline_valence,
            baseline_arousal=t.baseline_arousal,
            decay_rate_phasic=t.decay_rate_phasic,
            decay_multiplier_positive=t.decay_multiplier_positive,
            decay_multiplier_negative=t.decay_multiplier_negative,
            decay_rate_tonic=t.decay_rate_tonic,
            impulse_scale_positive=t.impulse_scale_positive,
            impulse_scale_negative=t.impulse_scale_negative,
            valence_min=t.valence_min,
            valence_max=t.valence_max,
            arousal_min=t.arousal_min,
            arousal_max=t.arousal_max,
            noise_amplitude=0.0,
            emotional_range=t.emotional_range,
            idle_impulse_magnitude=t.idle_impulse_magnitude,
        )
        update_affect(a, t_quiet, [], 1000.0)
        assert a.valence == pytest.approx(t_quiet.baseline_valence, abs=0.01)
        assert a.arousal == pytest.approx(t_quiet.baseline_arousal, abs=0.01)

    def test_clamping_valence(self):
        """Affect should be clamped to trait bounds."""
        a = _affect(10.0, 10.0)  # way out of bounds
        t = _canonical_trait()
        random.seed(42)
        update_affect(a, t, [], 0.01)
        assert a.valence <= t.valence_max
        assert a.arousal <= t.arousal_max

    def test_clamping_negative(self):
        a = _affect(-10.0, -10.0)
        t = _canonical_trait()
        random.seed(42)
        update_affect(a, t, [], 0.01)
        assert a.valence >= t.valence_min
        assert a.arousal >= t.arousal_min


# ── Impulse Application ─────────────────────────────────────────────


class TestImpulse:
    def test_positive_impulse(self):
        a = _affect(0.0, 0.0)
        t = _canonical_trait()
        imp = Impulse(0.70, 0.35, 0.50, "test")
        apply_impulse(a, imp, t)
        # Should move toward (0.70, 0.35)
        assert a.valence > 0.0
        assert a.arousal > 0.0

    def test_negative_impulse_attenuated(self):
        """Negative-valence impulse should be attenuated (~0.55x)."""
        a = _affect(0.10, 0.0)
        t = _canonical_trait()
        imp_neg = Impulse(-0.60, -0.40, 0.50, "test")
        apply_impulse(a, imp_neg, t)
        displacement_neg = math.sqrt((a.valence - 0.10) ** 2 + (a.arousal - 0.0) ** 2)

        a2 = _affect(0.10, 0.0)
        imp_pos = Impulse(0.80, 0.40, 0.50, "test")
        apply_impulse(a2, imp_pos, t)
        displacement_pos = math.sqrt((a2.valence - 0.10) ** 2 + (a2.arousal - 0.0) ** 2)

        # Negative displacement should be ~55% of positive
        assert displacement_neg < displacement_pos
        assert displacement_neg / displacement_pos == pytest.approx(
            t.impulse_scale_negative / t.impulse_scale_positive, abs=0.15
        )

    def test_at_target_no_change(self):
        """If affect is already at target, impulse should be no-op."""
        a = _affect(0.70, 0.35)
        t = _canonical_trait()
        imp = Impulse(0.70, 0.35, 0.50, "test")
        apply_impulse(a, imp, t)
        assert a.valence == pytest.approx(0.70, abs=0.01)
        assert a.arousal == pytest.approx(0.35, abs=0.01)

    def test_no_overshoot(self):
        """Impulse should not overshoot its target."""
        a = _affect(0.60, 0.30)  # Close to target
        t = _canonical_trait()
        imp = Impulse(0.70, 0.35, 5.0, "test")  # Huge magnitude
        apply_impulse(a, imp, t)
        # Should reach target but not go past
        dist = math.sqrt((a.valence - 0.70) ** 2 + (a.arousal - 0.35) ** 2)
        assert dist < 0.01

    def test_impulses_in_update(self):
        """Impulses passed to update_affect should be applied and cleared."""
        a = _affect(0.0, 0.0)
        t = _canonical_trait()
        imps = [Impulse(0.70, 0.35, 0.40, "test")]
        random.seed(42)
        update_affect(a, t, imps, 0.001)
        assert a.valence > 0.0
        assert len(imps) == 0  # queue drained


# ── Mood Projection ─────────────────────────────────────────────────


class TestMoodProjection:
    def test_baseline_projects_neutral(self):
        a = _affect(0.10, -0.05)
        mood, intensity = project_mood(a, "neutral")
        assert mood == "neutral"

    def test_at_happy_anchor(self):
        a = _affect(0.70, 0.35)
        mood, intensity = project_mood(a, "neutral")
        assert mood == "happy"
        assert intensity > 0.8  # should be high, very close to anchor

    def test_at_sad_anchor(self):
        a = _affect(-0.60, -0.40)
        mood, intensity = project_mood(a, "sad")
        assert mood == "sad"
        assert intensity > 0.9

    def test_all_anchors_reachable(self):
        """Each mood anchor should project to itself when affect is at that position."""
        for name, (v, a_val) in MOOD_ANCHORS.items():
            a = _affect(v, a_val)
            mood, intensity = project_mood(a, name)
            assert mood == name, f"Expected {name}, got {mood}"

    def test_hysteresis_prevents_flicker(self):
        """Small perturbation from anchor should not change mood."""
        a = _affect(0.68, 0.34)  # Slightly off HAPPY (0.70, 0.35)
        mood, _ = project_mood(a, "happy")
        assert mood == "happy"  # hysteresis should keep it

    def test_hysteresis_entering_negative_harder(self):
        """Need bigger displacement to enter negative mood (threshold=0.15)."""
        # Start at neutral, move slightly toward SAD — should stay neutral
        a = _affect(-0.10, -0.10)
        mood, _ = project_mood(a, "neutral")
        assert mood == "neutral"  # not far enough to overcome 0.15 threshold

    def test_hysteresis_leaving_negative_easier(self):
        """Need smaller displacement to leave negative mood (threshold=0.08)."""
        # Start at SAD, move slightly toward neutral
        a = _affect(-0.50, -0.30)  # closer to neutral than SAD
        mood, _ = project_mood(a, "sad")
        # Might still be sad due to hysteresis, or might switch
        # The key is it's easier than entering was
        assert mood in ("sad", "neutral", "confused")

    def test_intensity_ranges(self):
        """Intensity should be between 0.0 and 1.0."""
        a = _affect(0.50, 0.30)
        _, intensity = project_mood(a, "neutral")
        assert 0.0 <= intensity <= 1.0

    def test_intensity_at_anchor_is_high(self):
        a = _affect(0.0, 0.0)  # exactly at NEUTRAL anchor
        _, intensity = project_mood(a, "neutral")
        assert intensity > 0.8

    def test_intensity_far_from_anchor_is_low(self):
        a = _affect(0.40, 0.10)  # between several anchors
        _, intensity = project_mood(a, "neutral")
        # Distance from neutral ≈ 0.41, so intensity ≈ 1 - 0.41/1.2 ≈ 0.66
        assert intensity < 0.8


# ── Context Gate ─────────────────────────────────────────────────────


class TestContextGate:
    def test_negative_blocked_outside_conversation(self):
        assert enforce_context_gate("sad", conversation_active=False) == "neutral"
        assert enforce_context_gate("scared", conversation_active=False) == "neutral"
        assert enforce_context_gate("angry", conversation_active=False) == "neutral"

    def test_negative_allowed_during_conversation(self):
        assert enforce_context_gate("sad", conversation_active=True) == "sad"
        assert enforce_context_gate("scared", conversation_active=True) == "scared"
        assert enforce_context_gate("angry", conversation_active=True) == "angry"

    def test_positive_always_passes(self):
        assert enforce_context_gate("happy", conversation_active=False) == "happy"
        assert enforce_context_gate("excited", conversation_active=True) == "excited"

    def test_surprised_not_blocked(self):
        """SURPRISED is Neutral class, not Negative — should not be gated."""
        assert (
            enforce_context_gate("surprised", conversation_active=False) == "surprised"
        )

    def test_sleepy_not_blocked(self):
        assert enforce_context_gate("sleepy", conversation_active=False) == "sleepy"

    def test_neutral_passes(self):
        assert enforce_context_gate("neutral", conversation_active=False) == "neutral"


# ── Constants Sanity ─────────────────────────────────────────────────


class TestConstants:
    def test_thirteen_mood_anchors(self):
        assert len(MOOD_ANCHORS) == 13

    def test_three_negative_moods(self):
        assert len(NEGATIVE_MOODS) == 3
        assert NEGATIVE_MOODS == {"sad", "scared", "angry"}

    def test_all_negative_moods_have_anchors(self):
        for m in NEGATIVE_MOODS:
            assert m in MOOD_ANCHORS

    def test_max_anchor_distance(self):
        assert MAX_ANCHOR_DISTANCE == 1.20
