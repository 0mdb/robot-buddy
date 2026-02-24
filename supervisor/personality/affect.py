"""Pure affect vector model — data structures and algorithms (PE spec S2 §§2-6).

No asyncio, no I/O, no imports from workers or messages.  This module
contains all the math for the personality engine: trait parameter
derivation, decaying integrator, impulse application, mood projection,
context gate, and hysteresis.

Evidence tagging follows the spec convention:
  [Empirical] = peer-reviewed, [Theory] = general principle,
  [Inference] = derived from evidence, needs validation.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Final

# ── Mood Anchors (spec S2 §4.1, Russell circumplex) ────────────────

MOOD_ANCHORS: Final[dict[str, tuple[float, float]]] = {
    "neutral": (0.00, 0.00),
    "happy": (0.70, 0.35),
    "excited": (0.65, 0.80),
    "curious": (0.40, 0.45),
    "love": (0.80, 0.15),
    "silly": (0.55, 0.60),
    "thinking": (0.10, 0.20),
    "surprised": (0.15, 0.80),
    "sad": (-0.60, -0.40),
    "scared": (-0.70, 0.65),
    "angry": (-0.60, 0.70),
    "confused": (-0.20, 0.30),
    "sleepy": (0.05, -0.80),
}

NEGATIVE_MOODS: Final[frozenset[str]] = frozenset({"sad", "scared", "angry"})

# Max distance in VA space for intensity scaling (spec §4.2).
MAX_ANCHOR_DISTANCE: Final[float] = 1.20

# L1 emotion→VA mapping for LLM impulses (spec §5.2).
# Targets match mood anchors; magnitudes calibrated for trait-scaled application.
EMOTION_VA_TARGETS: Final[dict[str, tuple[float, float, float]]] = {
    # emotion: (target_v, target_a, base_magnitude)
    "neutral": (0.00, 0.00, 0.30),
    "happy": (0.70, 0.35, 0.60),
    "excited": (0.65, 0.80, 0.70),
    "curious": (0.40, 0.45, 0.55),
    "love": (0.80, 0.15, 0.60),
    "silly": (0.55, 0.60, 0.60),
    "thinking": (0.10, 0.20, 0.40),
    "surprised": (0.15, 0.80, 0.65),
    "sad": (-0.60, -0.40, 0.50),
    "scared": (-0.70, 0.65, 0.50),
    "angry": (-0.60, 0.70, 0.45),
    "confused": (-0.20, 0.30, 0.40),
    "sleepy": (0.05, -0.80, 0.40),
}


# ── Data Structures ─────────────────────────────────────────────────


@dataclass(slots=True)
class TraitParameters:
    """Static personality parameters derived from axis positions (spec §3.2).

    Computed once at startup.  Never modified at runtime.
    """

    baseline_valence: float  # P1:  +0.10
    baseline_arousal: float  # P2:  -0.05
    decay_rate_phasic: float  # P3:  0.055 /s
    decay_multiplier_positive: float  # P4:  0.85
    decay_multiplier_negative: float  # P5:  1.30
    decay_rate_tonic: float  # P6:  0.0006 /s
    impulse_scale_positive: float  # P7:  1.00
    impulse_scale_negative: float  # P8:  0.55
    valence_min: float  # P9:  -0.68
    valence_max: float  # P10: +0.95
    arousal_min: float  # P11: -0.90
    arousal_max: float  # P12: +0.66
    noise_amplitude: float  # P13: 0.0125
    emotional_range: float  # P14: 0.70
    idle_impulse_magnitude: float  # P20: 0.19


@dataclass(slots=True)
class AffectVector:
    """Mutable emotional state.  Updated every tick."""

    valence: float = 0.10  # initialized to baseline
    arousal: float = -0.05  # initialized to baseline


@dataclass(slots=True)
class Impulse:
    """Discrete emotional perturbation from any source."""

    target_valence: float
    target_arousal: float
    magnitude: float  # 0.0–1.0, scaled by trait before application
    source: str  # "system_event" | "idle_rule" | "ai_emotion" | "speech_signal"


@dataclass(slots=True)
class PersonalitySnapshot:
    """Primary output consumed by the tick loop (spec §10.5)."""

    mood: str = "neutral"
    intensity: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0
    layer: int = 0  # 0 = deterministic only, 1 = LLM-enhanced
    conversation_active: bool = False
    idle_state: str = "awake"  # "awake" | "drowsy" | "asleep"
    ts: float = 0.0  # monotonic timestamp


# ── Sigmoid Helper (spec §3.1) ──────────────────────────────────────


def sigmoid_map(x: float, k: float = 5.0, x0: float = 0.5) -> float:
    """Map axis position [0,1] through sigmoid.  k=steepness, x0=midpoint."""
    return 1.0 / (1.0 + math.exp(-k * (x - x0)))


# ── Trait Parameter Derivation (spec §3.2) ──────────────────────────


def compute_trait_parameters(
    energy: float,
    reactivity: float,
    initiative: float,
    vulnerability: float,
    predictability: float,
) -> TraitParameters:
    """Derive all 20 parameters from the 5 axis positions.

    Formulas are from spec §3.2.  P4/P5 use research-recommended design
    overrides (0.85/1.30) rather than the reactivity-derived formula, per
    spec §3.2 note.
    """
    sig_r = sigmoid_map(reactivity, 5.0, 0.5)

    p7 = 0.50 + 1.00 * sig_r  # impulse_scale_positive

    return TraitParameters(
        baseline_valence=0.10,  # P1: constant (caretaker warmth)
        baseline_arousal=0.50 * (energy - 0.50),  # P2
        decay_rate_phasic=0.03 + 0.05 * sig_r,  # P3
        decay_multiplier_positive=0.85,  # P4: design override
        decay_multiplier_negative=1.30,  # P5: design override
        decay_rate_tonic=0.0003 + 0.0006 * sig_r,  # P6
        impulse_scale_positive=p7,  # P7
        impulse_scale_negative=p7 * (0.30 + 0.70 * vulnerability),  # P8
        valence_min=-0.50 - 0.50 * vulnerability,  # P9
        valence_max=0.95,  # P10: constant
        arousal_min=-0.90,  # P11: constant
        arousal_max=0.50 + 0.40 * energy,  # P12
        noise_amplitude=0.05 * (1.0 - predictability),  # P13
        emotional_range=0.40 + 0.60 * sigmoid_map(reactivity, 4.0, 0.5),  # P14
        idle_impulse_magnitude=0.10 + 0.30 * initiative,  # P20
    )


# ── Affect Update (spec §2.4) ───────────────────────────────────────


# Memory bias weight — very weak per-tick influence (PE spec S2 §8.3).
# Strong memory (strength 1.0, valence_bias 0.10): +0.002 VA/s.
MEMORY_WEIGHT: float = 0.02


def update_affect(
    affect: AffectVector,
    trait: TraitParameters,
    pending_impulses: list[Impulse],
    dt: float,
    memories: list | None = None,
) -> None:
    """Run one tick of the decaying integrator.

    Steps (spec §2.4):
      1. Asymmetric decay toward baseline (tick-rate invariant)
      2. Apply pending impulses (drain queue)
      3. Memory bias (PE spec S2 §8.3)
      4. Add noise (Predictability axis)
      5. Clamp to bounds
    """
    if dt <= 0.0:
        # Drain impulses even for dt=0 (edge case: same-tick events).
        for imp in pending_impulses:
            apply_impulse(affect, imp, trait)
        pending_impulses.clear()
        return

    # 1. Asymmetric decay toward baseline
    if affect.valence >= trait.baseline_valence:
        lam_v = trait.decay_rate_phasic * trait.decay_multiplier_positive
    else:
        lam_v = trait.decay_rate_phasic * trait.decay_multiplier_negative
    alpha_v = 1.0 - math.exp(-lam_v * dt)
    affect.valence += (trait.baseline_valence - affect.valence) * alpha_v

    if affect.arousal >= trait.baseline_arousal:
        lam_a = trait.decay_rate_phasic * trait.decay_multiplier_positive
    else:
        lam_a = trait.decay_rate_phasic * trait.decay_multiplier_negative
    alpha_a = 1.0 - math.exp(-lam_a * dt)
    affect.arousal += (trait.baseline_arousal - affect.arousal) * alpha_a

    # 2. Apply pending impulses
    for imp in pending_impulses:
        apply_impulse(affect, imp, trait)
    pending_impulses.clear()

    # 3. Memory bias (PE spec S2 §8.3)
    if memories:
        for mem in memories:
            s = mem.current_strength()
            if s > 0.05:
                affect.valence += mem.valence_bias * s * MEMORY_WEIGHT * dt
                affect.arousal += mem.arousal_bias * s * MEMORY_WEIGHT * dt

    # 4. Noise (Brownian scaling: stddev * sqrt(dt))
    affect.valence += random.gauss(0.0, trait.noise_amplitude) * math.sqrt(dt)
    affect.arousal += random.gauss(0.0, trait.noise_amplitude) * math.sqrt(dt)

    # 5. Clamp to bounds
    affect.valence = max(trait.valence_min, min(trait.valence_max, affect.valence))
    affect.arousal = max(trait.arousal_min, min(trait.arousal_max, affect.arousal))


# ── Impulse Application (spec §5.3) ─────────────────────────────────


def apply_impulse(
    affect: AffectVector, impulse: Impulse, trait: TraitParameters
) -> None:
    """Apply a single impulse to the affect vector with trait-based scaling."""
    dv = impulse.target_valence - affect.valence
    da = impulse.target_arousal - affect.arousal
    norm = math.sqrt(dv * dv + da * da)
    if norm < 0.001:
        return  # already at target

    # Normalize direction
    unit_v = dv / norm
    unit_a = da / norm

    # Select scale based on valence direction (spec §5.3)
    if impulse.target_valence < affect.valence:
        scale = trait.impulse_scale_negative  # 0.55 — attenuated
    else:
        scale = trait.impulse_scale_positive  # 1.00 — full strength

    # Displacement: magnitude × scale, but never overshoot the target.
    displacement = min(impulse.magnitude * scale, norm)
    affect.valence += unit_v * displacement
    affect.arousal += unit_a * displacement


# ── Mood Projection (spec §4.2) ─────────────────────────────────────


def _distance(v: float, a: float, anchor: tuple[float, float]) -> float:
    """Euclidean distance from (v, a) to a mood anchor."""
    return math.sqrt((v - anchor[0]) ** 2 + (a - anchor[1]) ** 2)


def _hysteresis_threshold(current: str, candidate: str) -> float:
    """Asymmetric hysteresis thresholds (spec §4.3).

    Harder to enter negative moods, easier to leave them.
    """
    curr_neg = current in NEGATIVE_MOODS
    cand_neg = candidate in NEGATIVE_MOODS
    if curr_neg and not cand_neg:
        return 0.08  # leaving negative — easy
    if not curr_neg and cand_neg:
        return 0.15  # entering negative — hard
    if curr_neg and cand_neg:
        return 0.10  # between negatives
    return 0.12  # positive/neutral transitions


def project_mood(affect: AffectVector, current_mood: str) -> tuple[str, float]:
    """Project affect vector to the nearest discrete mood with hysteresis.

    Returns (mood_name, intensity) where intensity ∈ [0.0, 1.0].
    """
    d_current = _distance(affect.valence, affect.arousal, MOOD_ANCHORS[current_mood])

    nearest = min(
        MOOD_ANCHORS,
        key=lambda m: _distance(affect.valence, affect.arousal, MOOD_ANCHORS[m]),
    )
    d_nearest = _distance(affect.valence, affect.arousal, MOOD_ANCHORS[nearest])

    threshold = _hysteresis_threshold(current_mood, nearest)
    if d_current - d_nearest > threshold:
        current_mood = nearest
        d_current = d_nearest

    intensity = max(0.0, min(1.0, 1.0 - d_current / MAX_ANCHOR_DISTANCE))
    return current_mood, round(intensity, 2)


# ── Context Gate (spec §9.2) ────────────────────────────────────────


def enforce_context_gate(mood: str, conversation_active: bool) -> str:
    """Block negative moods outside conversation.

    Returns the mood unchanged if allowed, or "neutral" if blocked.
    """
    if mood in NEGATIVE_MOODS and not conversation_active:
        return "neutral"
    return mood
