# Personality Engine Spec — Stage 2: Full Implementation Specification

## Overview

This document is the implementation-ready specification for the Robot Buddy Personality Engine. It operationalizes all 10 design decisions (PE-1 through PE-10) from [Stage 1](personality-engine-spec-stage1.md) and synthesizes findings from 8 research documents (Buckets 0-7). A developer can build the complete personality engine from this spec alone.

The personality engine is a process-isolated worker (`PersonalityWorker`) on the Pi 5 that maintains a continuous affect vector, applies personality-derived parameters, modulates LLM emotion suggestions, and emits state snapshots consumed by the 50 Hz tick loop for face display. It integrates with the server LLM via system prompt injection and structured response parsing.

**Companion documents**: [Stage 1 spec](personality-engine-spec-stage1.md) (research & decisions), [Face comm Stage 2](face-communication-spec-stage2.md) (visual grammar), [Alignment report](pe-face-comm-alignment.md) (conflict resolutions). Implementation tracking is in `docs/TODO.md`.

**Evidence tagging**: Every design choice is tagged `[Empirical]` (peer-reviewed evidence), `[Theory]` (general principle), or `[Inference]` (derived from evidence, needs validation).

---

## 1. Personality Profile and Axis Positions

### 1.1 Canonical Axis Positions

The personality is fixed for all children, all sessions (PE-4). These positions are canonical — identical to [face comm S2 §1] and never modified at runtime.

| Axis | Position | Semantic | Observable Effect |
|------|----------|----------|-------------------|
| Energy Level | 0.40 | Calm but present | Slightly below-average arousal baseline; doesn't exceed child's energy |
| Emotional Reactivity | 0.50 | Responsive but stable | Mid-range impulse scaling; emotions neither amplified nor damped |
| Social Initiative | 0.30 | Quietly alive | Zero verbal proactive behavior; ~1-2 visible idle shifts per hour |
| Vulnerability Display | 0.35 | Lightly guarded caretaker | Negative impulses attenuated to ~55%; mild empathy display |
| Predictability | 0.75 | Consistent with cosmetic freshness | 25% variation budget; low noise amplitude |

### 1.2 Axis-to-Parameter Routing

Each axis influences specific affect vector parameters. Exact formulas are in §3; this table provides the routing map.

| Axis | Parameters Affected | Defined In |
|------|-------------------|------------|
| Energy (0.40) | baseline_arousal, arousal_max, positive_arousal_scale | §3 |
| Reactivity (0.50) | decay_rate_phasic, impulse_magnitude_scale, emotional_range | §3, §6 |
| Initiative (0.30) | initiative_cooldown, idle_impulse_magnitude, autonomous_freq | §7 |
| Vulnerability (0.35) | valence_min, negative_impulse_attenuation, empathy_gain | §3, §13 |
| Predictability (0.75) | noise_amplitude, timing_jitter, variant_probability | §3, §7 |

### 1.3 Design Implications

The combined profile produces a robot that:
- Rests near NEUTRAL with a slight positive lean (+0.10 valence) and slightly calm arousal (-0.05) [Inference]
- Responds visibly to emotional stimuli but doesn't amplify them (Reactivity 0.50 = baseline scaling) [Theory]
- Recovers from negative emotions ~30% faster than positive ones (asymmetric decay from Reactivity) [Inference]
- Never initiates conversation but shows idle emotional life through subtle mood shifts [Inference]
- Attenuates negative impulses to ~55% strength, producing mild rather than intense negative displays [Inference]

---

## 2. Affect Vector Model

### 2.1 Formal Model

The personality engine maintains a continuous affect vector that evolves via a decaying integrator:

```
affect(t) = (valence, arousal) ∈ [-1, 1]²

da/dt = λ · (baseline - a) + Σ_k impulse_k · δ(t - t_k) + memory_bias(t) + noise(t)
```

Where `a(t)` is the current affect state, `baseline` is the temperament attractor, `λ` is the decay rate, `impulse_k` are discrete events, `memory_bias` is a weak continuous pull from persistent memory, and `noise` is Gaussian variation from the Predictability axis. [Theory — decaying integrator from TAME (Moshkina & Arkin, 2011)]

Discrete-time implementation (tick-rate invariant):

```python
alpha = 1.0 - math.exp(-decay_rate * dt)
affect.valence += (baseline_valence - affect.valence) * alpha
affect.arousal += (baseline_arousal - affect.arousal) * alpha
```

### 2.2 Four-Layer Ontology

```
TRAIT (static, set once)
  baseline(v, a), decay_rates, impulse_scales, bounds, noise_amplitude
      │
      ▼
STATE (per-tick, 1 Hz + event-triggered)
  affect(v, a) ∈ [-1, 1]² — the continuously evolving emotional position
      │
      ▼
IMPULSE (event-driven, immediate)
  (target_v, target_a, magnitude, source) — discrete perturbations
      │
      ▼
MEMORY (per-session, persistent)
  (tag, valence_bias, arousal_bias, strength, decay_lambda) — weak continuous influence
```

### 2.3 Core Data Structures

```python
@dataclass(slots=True)
class TraitParameters:
    """Static personality parameters derived from axis positions. Set once at startup."""
    baseline_valence: float       # §3: +0.10
    baseline_arousal: float       # §3: -0.05
    decay_rate_phasic: float      # §3: 0.055 /s (base, before asymmetric multiplier)
    decay_multiplier_positive: float  # §6: 0.85
    decay_multiplier_negative: float  # §6: 1.30
    decay_rate_tonic: float       # §6: 0.0006 /s
    impulse_scale_positive: float # §3: 1.00
    impulse_scale_negative: float # §3: 0.55
    valence_min: float            # §3: -0.68
    valence_max: float            # §3: +0.95
    arousal_min: float            # §3: -0.90
    arousal_max: float            # §3: +0.66
    noise_amplitude: float        # §3: 0.0125
    emotional_range: float        # §3: 0.70 (max displacement from baseline)


@dataclass(slots=True)
class AffectVector:
    """Mutable emotional state. Updated every tick."""
    valence: float = 0.10   # initialized to baseline
    arousal: float = -0.05  # initialized to baseline


@dataclass(slots=True)
class Impulse:
    """Discrete emotional perturbation from any source."""
    target_valence: float   # VA target to push toward
    target_arousal: float
    magnitude: float        # 0.0-1.0, scaled by trait before application
    source: str             # "system_event" | "idle_rule" | "ai_emotion" | "memory" | "speech_signal"
```

### 2.4 Update Algorithm

Executed once per 1 Hz tick and on event-triggered fast path:

```python
def update_affect(affect: AffectVector, trait: TraitParameters,
                  pending_impulses: list[Impulse], memories: list[MemoryEntry],
                  dt: float) -> None:
    # 1. Decay toward baseline (tick-rate invariant)
    if affect.valence >= trait.baseline_valence:
        lam = trait.decay_rate_phasic * trait.decay_multiplier_positive
    else:
        lam = trait.decay_rate_phasic * trait.decay_multiplier_negative
    alpha_v = 1.0 - math.exp(-lam * dt)
    affect.valence += (trait.baseline_valence - affect.valence) * alpha_v

    if affect.arousal >= trait.baseline_arousal:
        lam_a = trait.decay_rate_phasic * trait.decay_multiplier_positive
    else:
        lam_a = trait.decay_rate_phasic * trait.decay_multiplier_negative
    alpha_a = 1.0 - math.exp(-lam_a * dt)
    affect.arousal += (trait.baseline_arousal - affect.arousal) * alpha_a

    # 2. Apply pending impulses
    for imp in pending_impulses:
        _apply_impulse(affect, imp, trait)
    pending_impulses.clear()

    # 3. Apply memory bias (weak, continuous)
    for mem in memories:
        if mem.current_strength() > 0.05:
            affect.valence += mem.valence_bias * mem.current_strength() * MEMORY_WEIGHT * dt
            affect.arousal += mem.arousal_bias * mem.current_strength() * MEMORY_WEIGHT * dt

    # 4. Add noise
    affect.valence += random.gauss(0, trait.noise_amplitude) * math.sqrt(dt)
    affect.arousal += random.gauss(0, trait.noise_amplitude) * math.sqrt(dt)

    # 5. Clamp to bounds
    affect.valence = max(trait.valence_min, min(trait.valence_max, affect.valence))
    affect.arousal = max(trait.arousal_min, min(trait.arousal_max, affect.arousal))


MEMORY_WEIGHT: float = 0.02  # very weak — prevents memory from dominating integrator
```

---

## 3. Axis-to-Parameter Mapping Functions

### 3.1 Sigmoid Helper

```python
def sigmoid_map(x: float, k: float = 5.0, x0: float = 0.5) -> float:
    """Maps axis position [0,1] through sigmoid. k controls steepness, x0 is midpoint."""
    return 1.0 / (1.0 + math.exp(-k * (x - x0)))
```

At the midpoint (x = x0), sigmoid_map returns 0.50. Values below x0 compress toward 0; values above compress toward 1. This prevents caricature at extreme axis positions. [Theory — WASABI sigmoid activation (Becker-Asano & Wachsmuth, 2010)]

### 3.2 Complete Parameter Derivation Table

| # | Parameter | Axis | Formula | Value | Unit |
|---|-----------|------|---------|-------|------|
| P1 | baseline_valence | — | Constant (caretaker warmth) | +0.10 | VA |
| P2 | baseline_arousal | Energy (0.40) | `0.50 * (E - 0.50)` | -0.05 | VA |
| P3 | decay_rate_phasic | Reactivity (0.50) | `0.03 + 0.05 * sigmoid(R, 5, 0.5)` | 0.055 | /s |
| P4 | decay_multiplier_positive | Reactivity (0.50) | `1.0 - 0.15 * (1.0 - R)` | 0.925→**0.85** | mult |
| P5 | decay_multiplier_negative | Reactivity (0.50) | `1.0 + 0.30 * (1.0 - R)` | 1.15→**1.30** | mult |
| P6 | decay_rate_tonic | Reactivity (0.50) | `0.0003 + 0.0006 * sigmoid(R, 5, 0.5)` | 0.0006 | /s |
| P7 | impulse_scale_positive | Reactivity (0.50) | `0.50 + 1.00 * sigmoid(R, 5, 0.5)` | 1.00 | mult |
| P8 | impulse_scale_negative | Reactivity, Vuln | `P7 * (0.30 + 0.70 * V)` | 0.55 | mult |
| P9 | valence_min | Vulnerability (0.35) | `-0.50 - 0.50 * V` | -0.68 | VA |
| P10 | valence_max | — | Constant | +0.95 | VA |
| P11 | arousal_min | — | Constant | -0.90 | VA |
| P12 | arousal_max | Energy (0.40) | `0.50 + 0.40 * E` | +0.66 | VA |
| P13 | noise_amplitude | Predictability (0.75) | `0.05 * (1.0 - P)` | 0.0125 | VA |
| P14 | emotional_range | Reactivity (0.50) | `0.40 + 0.60 * sigmoid(R, 4, 0.5)` | 0.70 | VA |
| P15 | negative_impulse_attenuation | Vulnerability (0.35) | `0.30 + 0.70 * V` | 0.55 | mult |
| P16 | empathy_gain | Vulnerability (0.35) | `0.20 + 0.60 * V` | 0.41 | mult |
| P17 | timing_jitter_s | Predictability (0.75) | `60.0 * (1.0 - P)` | 15.0 | s |
| P18 | variant_probability | Predictability (0.75) | `1.0 - P` | 0.25 | prob |
| P19 | initiative_cooldown_s | Initiative (0.30) | `1800 / (0.10 + SI)` | 4500 | s |
| P20 | idle_impulse_magnitude | Initiative (0.30) | `0.10 + 0.30 * SI` | 0.19 | mag |

[Inference — all formulas derived from Bucket 1 TAME trait parametrization research, validated against Bucket 1 §9 axis-to-parameter table. Exact coefficients tuned for the caretaker profile.]

**Note on P4/P5**: The decay multipliers listed in Bucket 2 as fixed 0.85/1.30 are used directly as design targets. The Reactivity-derived formula produces 0.925/1.15 at R=0.50 — we override to the research-recommended values 0.85/1.30 which produced more natural recovery patterns. [Inference]

### 3.3 Worked Example: Baseline Affect Position

```
baseline = (valence=+0.10, arousal=-0.05)

Distance to NEUTRAL anchor (0.00, 0.00) = sqrt(0.10² + 0.05²) = 0.112
Distance to HAPPY anchor  (+0.70, +0.35) = sqrt(0.60² + 0.40²) = 0.721
Distance to CURIOUS anchor (+0.40, +0.45) = sqrt(0.30² + 0.50²) = 0.583

Nearest mood: NEUTRAL at distance 0.112
Projected mood: NEUTRAL
Intensity: 1.0 - 0.112 / 1.0 = 0.888 → but at this distance, intensity is low
  (see §4 for full intensity formula)

The robot at rest projects NEUTRAL at very low intensity — calm contentment.
```

---

## 4. Affect-to-Mood Projection

### 4.1 VA Space Mood Anchors

| Mood | Valence | Arousal | Class | Notes |
|------|---------|---------|-------|-------|
| NEUTRAL | 0.00 | 0.00 | Neutral | Origin point |
| HAPPY | +0.70 | +0.35 | Positive | Moderate arousal, high valence |
| EXCITED | +0.65 | +0.80 | Positive | High arousal, high valence |
| CURIOUS | +0.40 | +0.45 | Neutral | Positive-leaning, moderate arousal |
| LOVE | +0.80 | +0.15 | Positive | Highest valence, low arousal |
| SILLY | +0.55 | +0.60 | Positive | Playful, moderately high arousal |
| THINKING | +0.10 | +0.20 | Neutral | Near-neutral, mild deliberation |
| SURPRISED | +0.15 | +0.80 | Neutral | Very high arousal, mild positive valence |
| SAD | -0.60 | -0.40 | Negative | Low arousal, negative valence |
| SCARED | -0.70 | +0.65 | Negative | High arousal, strong negative valence |
| ANGRY | -0.60 | +0.70 | Negative | High arousal, negative valence |
| CONFUSED | -0.20 | +0.30 | Neutral | Mild negative, mild arousal |
| SLEEPY | +0.05 | -0.80 | Neutral | Very low arousal, near-neutral valence |

[Inference — anchor positions from Bucket 1 §8.2, based on Russell's circumplex model (1980). Positions validated against Posner et al. (2005) dimensional affect ratings. CONFUSED replaces a second SLEEPY variant.]

```
        arousal
        +1.0 ┤
             │        SURPRISED   EXCITED
             │          ANGRY ╳ SCARED
        +0.5 ┤       SILLY
             │  CONFUSED   CURIOUS
             │   THINKING    HAPPY
          0  ┤  NEUTRAL         LOVE
             │
        -0.5 ┤   SAD
             │
        -1.0 ┤         SLEEPY
             └──┬───┬───┬───┬───┬───┬──
               -1  -0.5  0  +0.5  +1
                        valence
```

### 4.2 Projection Algorithm

```python
MOOD_ANCHORS: dict[str, tuple[float, float]] = {
    "neutral": (0.00, 0.00), "happy": (0.70, 0.35), "excited": (0.65, 0.80),
    "curious": (0.40, 0.45), "love": (0.80, 0.15), "silly": (0.55, 0.60),
    "thinking": (0.10, 0.20), "surprised": (0.15, 0.80), "sad": (-0.60, -0.40),
    "scared": (-0.70, 0.65), "angry": (-0.60, 0.70), "confused": (-0.20, 0.30),
    "sleepy": (0.05, -0.80),
}

NEGATIVE_MOODS: frozenset[str] = frozenset({"sad", "scared", "angry"})
# Note: SURPRISED is Neutral class (V=+0.15), not Negative. It has a separate startle-reflex
# safety rule (3.0 s max, 0.8 intensity cap) enforced alongside but distinct from negative
# mood guardrails. See §9.1 and face comm §7.4.
MAX_ANCHOR_DISTANCE: float = 1.20  # max possible distance in VA space for intensity scaling


def project_mood(affect: AffectVector, current_mood: str) -> tuple[str, float]:
    """Project affect vector to nearest discrete mood with hysteresis."""
    d_current = _distance(affect, MOOD_ANCHORS[current_mood])

    nearest = min(MOOD_ANCHORS, key=lambda m: _distance(affect, MOOD_ANCHORS[m]))
    d_nearest = _distance(affect, MOOD_ANCHORS[nearest])

    threshold = _hysteresis_threshold(current_mood, nearest)
    if d_current - d_nearest > threshold:
        current_mood = nearest

    intensity = max(0.0, min(1.0, 1.0 - d_current / MAX_ANCHOR_DISTANCE))
    return current_mood, round(intensity, 2)


def _distance(affect: AffectVector, anchor: tuple[float, float]) -> float:
    return math.sqrt((affect.valence - anchor[0])**2 + (affect.arousal - anchor[1])**2)
```

### 4.3 Asymmetric Hysteresis

The hysteresis threshold varies by transition direction to make it harder to enter negative moods and easier to leave them. This implements the caretaker guardrail philosophy. [Inference — derived from Bucket 1 §8.2 asymmetric thresholds]

| Transition Direction | Threshold | Rationale |
|---------------------|-----------|-----------|
| Positive/Neutral → Positive/Neutral | 0.12 | Standard transition |
| Positive/Neutral → Negative | 0.15 | Harder to enter negative territory |
| Negative → Positive/Neutral | 0.08 | Easier to leave negative territory |
| Negative → Negative | 0.10 | Moderate within-negative transitions |

```python
def _hysteresis_threshold(current: str, candidate: str) -> float:
    curr_neg = current in NEGATIVE_MOODS
    cand_neg = candidate in NEGATIVE_MOODS
    if curr_neg and not cand_neg:
        return 0.08   # leaving negative — easy
    if not curr_neg and cand_neg:
        return 0.15   # entering negative — hard
    if curr_neg and cand_neg:
        return 0.10   # between negatives
    return 0.12       # positive/neutral transitions
```

---

## 5. Impulse Catalog

### 5.1 Layer 0 Impulses (Deterministic, No Server)

All Layer 0 impulses fire from on-device rules. They require no LLM and no server connectivity. [PE-7: rules only for Layer 0]

| ID | Trigger | Target (V, A) | Magnitude | Cooldown | Conditions |
|----|---------|---------------|-----------|----------|------------|
| L0-01 | Boot complete | (+0.35, +0.40) | 0.50 | — | Once per boot |
| L0-02 | Low battery (<20%) | (-0.15, +0.10) | 0.30 | 120 s | battery_pct < 20 |
| L0-03 | Critical battery (<10%) | (+0.05, -0.60) | 0.40 | — | battery_pct < 10 |
| L0-04 | Fault raised | (-0.10, +0.25) | 0.40 | 30 s | any fault active |
| L0-05 | Fault cleared | (+0.15, -0.10) | 0.30 | — | fault just cleared |
| L0-06 | Conversation started | (+0.10, +0.15) | 0.30 | — | session_id assigned |
| L0-07 | Conversation ended (positive) | (+0.20, -0.05) | 0.40 | — | conv done, affect.v > 0 |
| L0-08 | Conversation ended (negative) | (+0.05, -0.10) | 0.30 | — | conv done, affect.v ≤ 0 |
| L0-09 | Speech activity detected | (+0.05, +0.10) | 0.20 | 5 s | speaking == true |
| L0-10 | Button press | (+0.15, +0.20) | 0.40 | 5 s | face touch/button |
| L0-11 | Medium idle (5+ min) | (+0.00, -0.15) | 0.30 | 600 s | idle_s > 300 |
| L0-12 | Long idle (15+ min) | (+0.00, -0.30) | 0.40 | 1800 s | idle_s > 900 |
| L0-13 | Child approach | (+0.10, +0.15) | 0.25 | 10 s | wake word or proximity |

### 5.2 Layer 1 Impulses (LLM-Sourced, Modulated)

LLM emotion suggestions arrive as `personality.event.ai_emotion` events. The personality worker maps the emotion name to a VA target and applies trait-based modulation (§13) before injecting as an impulse. [PE-8: output modulation]

**Emotion-to-VA Mapping Table** (targets match §4.1 mood anchors):

| LLM Emotion | Impulse Target (V, A) | Base Magnitude |
|-------------|----------------------|----------------|
| neutral | (0.00, 0.00) | 0.30 |
| happy | (+0.70, +0.35) | 0.60 |
| excited | (+0.65, +0.80) | 0.70 |
| curious | (+0.40, +0.45) | 0.55 |
| love | (+0.80, +0.15) | 0.60 |
| silly | (+0.55, +0.60) | 0.60 |
| thinking | (+0.10, +0.20) | 0.40 |
| surprised | (+0.15, +0.80) | 0.65 |
| sad | (-0.60, -0.40) | 0.50 |
| scared | (-0.70, +0.65) | 0.50 |
| angry | (-0.60, +0.70) | 0.45 |
| confused | (-0.20, +0.30) | 0.40 |
| sleepy | (+0.05, -0.80) | 0.40 |

### 5.3 Impulse Application

```python
def _apply_impulse(affect: AffectVector, impulse: Impulse, trait: TraitParameters) -> None:
    """Apply a single impulse to the affect vector with trait-based scaling."""
    dv = impulse.target_valence - affect.valence
    da = impulse.target_arousal - affect.arousal
    norm = math.sqrt(dv * dv + da * da)
    if norm < 0.001:
        return  # already at target

    # Normalize direction
    unit_v = dv / norm
    unit_a = da / norm

    # Select scale based on valence direction
    if impulse.target_valence < affect.valence:
        scale = trait.impulse_scale_negative  # 0.55 — attenuated
    else:
        scale = trait.impulse_scale_positive  # 1.00 — full strength

    # Apply scaled impulse
    affect.valence += unit_v * impulse.magnitude * scale
    affect.arousal += unit_a * impulse.magnitude * scale
```

---

## 6. Decay Rates and Asymmetric Dynamics

### 6.1 Phasic Decay (Emotion Layer)

The phasic layer handles immediate emotional responses. Decay rates are asymmetric: positive emotions linger 15% longer, negative emotions fade 30% faster. This produces a caretaker personality that doesn't dwell on negativity. [Inference — asymmetric decay rationale from Bucket 2 §7.3]

| Affect Direction | Base λ (/s) | Multiplier | Effective λ | Half-Life |
|-----------------|-------------|------------|-------------|-----------|
| Positive (v > baseline) | 0.055 | ×0.85 | 0.047 | 14.8 s |
| Negative (v < baseline) | 0.055 | ×1.30 | 0.072 | 9.7 s |
| Arousal positive (a > baseline) | 0.055 | ×0.85 | 0.047 | 14.8 s |
| Arousal negative (a < baseline) | 0.055 | ×1.30 | 0.072 | 9.7 s |

**Intuitive**: After a joyful moment, the robot takes ~15 seconds to return halfway to baseline — a gentle emotional afterglow. After a brief negative emotion, it takes ~10 seconds — quick recovery appropriate for a caretaker. [Inference]

### 6.2 Tonic Decay (Mood Layer)

The tonic layer represents the background mood, which shifts very slowly toward baseline:

| Layer | λ (/s) | Half-Life | Purpose |
|-------|--------|-----------|---------|
| Tonic mood | 0.0006 | 19.3 min | Background mood that resists moment-to-moment fluctuation |

The tonic layer is implemented as a secondary attractor: if the phasic affect has been consistently displaced from baseline for several minutes, the tonic mood shifts to reflect this. The tonic mood does not currently affect face output directly — it serves as a diagnostic signal and feeds into the personality profile sent to the LLM. [Inference — tonic/phasic separation from ALMA architecture (Gebhard, 2005)]

### 6.3 Two-Layer Coupling

```
IMPULSE → PHASIC (seconds)  ─decay→  TONIC (minutes)  ─decay→  BASELINE (static)
   │                            │                          │
   fast, emotion-level          slow, mood-level           personality-level
   half-life: 10-15s            half-life: ~19 min         never changes
```

Coupling: the phasic layer's position biases the tonic layer's decay target. When phasic affect is consistently positive, the tonic layer drifts slightly positive. The coupling strength is 0.10 — very weak, requiring sustained emotion to shift mood. [Inference]

---

## 7. Idle Behavior Rules

**Relationship to face comm spec**: The idle behavior described here controls the semantic mood layer (which mood is displayed). The face MCU independently runs cosmetic idle animations (breathing, blink, gaze wander, sparkle) per face comm §4.3. These two systems operate on separate channels and do not conflict.

### 7.1 Idle Rule Table

All idle behavior is deterministic (PE-3). Rules fire based on timers and system state. HC-5 (no loneliness) and HC-10 (no negative emotions in idle) are baked into every rule. [PE-3, PE-5]

| Rule ID | Condition | Impulse Target (V, A) | Magnitude | Timing Jitter (±P17) | Face Result |
|---------|-----------|----------------------|-----------|---------------------|-------------|
| IDLE-01 | Boot complete | (+0.35, +0.40) | 0.50 | — | CURIOUS for 30-60 s, decays to NEUTRAL |
| IDLE-02 | 0-5 min idle | Baseline drift only | — | — | NEUTRAL at low intensity |
| IDLE-03 | 5-15 min idle | (+0.00, -0.15) | 0.30 | ±2 min on threshold | Drift toward SLEEPY |
| IDLE-04 | 15+ min idle | (+0.00, -0.30) | 0.40 | ±5 min on threshold | Deep SLEEPY |
| IDLE-05 | Post-conv (positive) | (+0.20, -0.05) | 0.40 | — | Warm afterglow, 2-3 min decay |
| IDLE-06 | Post-conv (negative) | (+0.05, -0.10) | 0.30 | — | Gentle recovery, 1-2 min decay |
| IDLE-07 | Morning (first boot) | (+0.05, +0.05) | 0.10 | — | Subtle energy lift for 5 min |
| IDLE-08 | Evening hours | (-0.02, -0.10) | 0.10 | — | Subtle sleepiness |
| IDLE-09 | Server offline >4 hr | (+0.00, -0.40) | 0.30 | — | Persistent SLEEPY ("resting robot") |

### 7.2 Noise Injection

Gaussian noise provides the 25% cosmetic variation budget (PE-3, from Predictability = 0.75):

- **Source**: `random.gauss(0, noise_amplitude)` per axis, per 1 Hz tick
- **Amplitude**: P13 = 0.0125 VA units per axis
- **Scaling**: `noise * sqrt(dt)` for tick-rate invariance
- **Purpose**: Prevents affect vector from sitting perfectly still — subtle "inner life" even during idle [Theory — Kismet homeostatic cycling (Breazeal, 2003)]

### 7.3 Context Suppression

Idle rules must NOT fire when these conditions are true:

```python
def should_suppress_idle(conversation_active: bool, speaking: bool,
                         error_active: bool, conv_ended_ago_s: float) -> bool:
    return any([
        conversation_active,          # conversation in progress
        speaking,                     # TTS currently playing
        error_active,                 # system fault active
        conv_ended_ago_s < 120.0,     # 2-min post-conversation cooldown
    ])
```

### 7.4 HC-5 / HC-10 Compliance

- **HC-5 (no loneliness)**: No idle rule produces negative-valence + social-seeking behavior. No "I miss you" or sad waiting expressions. Idle moods are self-contained. [Inference]
- **HC-10 (no negative in idle)**: The context gate (§9) blocks any negative mood projection outside of active conversation. If a negative impulse leaks through (e.g., from a slowly-decaying conversation emotion), it is clamped to NEUTRAL before reaching the face. [Inference]

---

## 8. Memory System

### 8.1 Memory Entry Structure

```python
@dataclass(slots=True)
class MemoryEntry:
    """A single persistent memory item."""
    tag: str                    # semantic label, e.g. "likes_dinosaurs"
    category: str               # "name" | "topic" | "ritual" | "tone" | "preference"
    valence_bias: float         # how this memory nudges valence (-0.10 to +0.10)
    arousal_bias: float         # how this memory nudges arousal (-0.10 to +0.10)
    initial_strength: float     # 1.0 at creation
    created_ts: float           # monotonic timestamp of creation
    last_reinforced_ts: float   # monotonic timestamp of last access/reinforcement
    reinforcement_count: int    # number of times reinforced
    decay_lambda: float         # per-second decay rate (from tier)
    source: str                 # "llm_extract" | "rule_infer"

    def current_strength(self) -> float:
        """Compute current strength with exponential decay since last reinforcement."""
        age_s = time.monotonic() - self.last_reinforced_ts
        return self.initial_strength * math.exp(-self.decay_lambda * age_s)
```

### 8.2 Decay Tiers

| Tier | Category | Example | Half-Life | λ (/s) | Max Entries | Floor |
|------|----------|---------|-----------|--------|-------------|-------|
| T0 | name | "child_name_emma" | Never | 0.0 | 1 | 1.0 |
| T1 | ritual | "greeting_fist_bump" | 90 days | 8.91e-8 | 5 | 0.10 |
| T2 | topic | "likes_dinosaurs" | 21 days | 3.82e-7 | 20 | 0.0 |
| T3 | tone | "last_session_happy" | 7 days | 1.15e-6 | 3 | 0.0 |
| T4 | preference | "prefers_silly_mood" | 4 days | 2.01e-6 | 10 | 0.0 |

[Inference — half-lives from Bucket 2 §8 memory decay recommendations. T0-T1 values from Bucket 3 relationship development research (Kanda et al., 2004). Exponential decay used for simplicity; power-law deferred to Stage 3 if empirical testing shows exponential is insufficient.]

**Floor**: Memory strength never decays below the floor value. Name (T0) is permanent. Rituals (T1) persist as faint traces. Topics and preferences fully decay. [Inference]

### 8.3 Memory Influence on Affect

Memories exert a weak, continuous bias on the affect vector:

```python
MEMORY_WEIGHT: float = 0.02  # very weak per-tick influence

for entry in active_memories:
    s = entry.current_strength()
    if s > 0.05:  # below threshold = effectively forgotten
        affect.valence += entry.valence_bias * s * MEMORY_WEIGHT * dt
        affect.arousal += entry.arousal_bias * s * MEMORY_WEIGHT * dt
```

At MEMORY_WEIGHT = 0.02 and a strong memory (strength 1.0, valence_bias +0.10), the per-second valence nudge is +0.002 — imperceptible per tick but cumulative over minutes. A session with 5 positive memories creates a subtle positive-leaning baseline shift of ~+0.01 over 5 minutes. [Inference]

### 8.4 Storage Format

Memory is stored as a JSON file on the Pi 5 filesystem. Local-only — never transmitted to the server. Only semantic tags are included in the `personality.llm.profile` sent to the server for LLM context.

```json
{
  "version": 1,
  "entries": [
    {"tag": "child_name_emma", "category": "name", "valence_bias": 0.05,
     "arousal_bias": 0.02, "initial_strength": 1.0, "created_ts": 1708000000.0,
     "last_reinforced_ts": 1708100000.0, "reinforcement_count": 12,
     "decay_lambda": 0.0, "source": "llm_extract"}
  ],
  "session_count": 47,
  "total_conversation_s": 2340.0,
  "created_ts": 1707000000.0
}
```

**Limits**: Maximum 50 entries across all categories. When full, the entry with the lowest `current_strength()` is evicted before adding a new one.

### 8.5 Privacy Constraints

| Constraint | Rule | Enforcement |
|-----------|------|-------------|
| No raw transcripts | Only semantic tags stored; extraction in LLM | `memory_tags` field in LLM response schema |
| Local-only storage | Memory file never leaves Pi 5 | No memory content in server sync |
| Parent data viewer | Dashboard panel shows all stored memories | REST endpoint + React component |
| Parent deletion | "Forget everything" button wipes memory file | `personality.cmd.reset_memory` event |
| Consent gate | Memory storage requires parental consent | `memory_consent` config flag, default false |
| Retention limit | 50 entries max | Evict lowest-strength on overflow |
| Recall framing | "I think we talked about..." not clinical recall | Enforced in LLM system prompt §12 |

[PE-2: persistent memory with configurable constraints. COPPA compliance per Bucket 0 §8.]

---

## 9. Guardrail Enforcement

### 9.1 Negative Mood Constraints

Migrated from face comm S2 §7 to the personality worker — the single source of emotional truth enforces all guardrails at the affect vector level before projection.

| Mood | Max Continuous Duration | Max Intensity | Recovery λ (/s) |
|------|:---------------------:|:------------:|:--------------:|
| SAD | 4.0 s | 0.70 | 0.50 |
| SCARED | 2.0 s | 0.60 | 0.70 |
| ANGRY | 2.0 s | 0.50 | 0.70 |

**Enforcement**: The personality worker tracks how long the projected mood has been in a negative state. When the duration cap is exceeded, a recovery impulse toward baseline is injected at the recovery λ rate, rapidly pulling affect back toward NEUTRAL. [Inference — face comm S2 §7 duration caps]

**Relationship to face comm spec**: The tick loop (face comm §7) acts as a safety backstop only, enforcing the same duration caps when the personality snapshot is stale (age > 3000 ms). Under normal operation, the tick loop trusts the worker's snapshot and does not run independent guardrail timers. See `specs/pe-face-comm-alignment.md` §4.1.

**SURPRISED**: Not listed above because it is classified as Neutral (§4.1), not Negative. However, a startle-reflex safety rule applies: 3.0 s maximum duration and 0.8 intensity cap (face comm §7.4). The personality worker enforces this as a special case alongside the negative duration caps — tracking SURPRISED duration separately and injecting a recovery impulse when the cap is exceeded.

### 9.2 Context Gate

Negative moods are blocked outside of active conversation:

```python
def enforce_context_gate(projected_mood: str, conversation_active: bool) -> str:
    if not conversation_active and projected_mood in NEGATIVE_MOODS:
        return "neutral"
    return projected_mood
```

This implements HC-10: no sustained negative affect during idle. If a slowly-decaying negative impulse from a recent conversation persists after `conv_ended`, the context gate overrides the projection to NEUTRAL. [Inference]

**Relationship to face comm spec**: The tick loop (face comm §7.3) applies an identical context gate as a safety backstop when the personality snapshot is stale (age > 3000 ms). Under normal operation, the tick loop does not independently filter negative moods — it trusts the worker's snapshot.

### 9.3 HC/RS Guardrail Summary

| ID | Rule | Enforcement Point | Default |
|----|------|-------------------|---------|
| HC-1 | Never claim sentience | LLM system prompt (§12) | On |
| HC-2 | No biometric identification | No voice ID or face ID | On |
| HC-3 | No emotional profiling | Memory stores semantic tags only | On |
| HC-4 | Never direct negative affect at child | mood_reason validation (§13) | On |
| HC-5 | No loneliness/abandonment | Idle rule filter (§7.4) | On |
| HC-6 | No guilt or obligation language | LLM system prompt (§12) | On |
| HC-7 | No secret-keeping encouragement | LLM system prompt (§12) | On |
| HC-8 | No parasocial deepening | LLM system prompt (§12) | On |
| HC-9 | Stop on child distress signals | Conversation abort trigger | On |
| HC-10 | No negative affect in idle | Context gate (§9.2) | On |
| RS-1 | Session time limit | Worker timer, 900 s (15 min) | On |
| RS-2 | Daily time limit | Worker counter, 2700 s (45 min) | On |
| RS-3 | Human redirection for serious topics | LLM system prompt (§12) | On |
| RS-4 | Parental visibility | Dashboard memory viewer | On |
| RS-5 | Consent gate for memory | Config flag | On |
| RS-6 | Approximate recall framing | LLM system prompt (§12) | On |
| RS-7 | Session cooldown | 2-min post-conv suppression (§7.3) | On |
| RS-8 | Emotional intensity caps | Per-mood caps (§9.1) | On |
| RS-9 | Graceful degradation | Silent degradation (§10) | On |
| RS-10 | Sleep mode | IDLE-04 rule (§7.1) | On |

### 9.4 Priority Hierarchy

When multiple systems disagree on emotion:

```
1. GUARDRAILS (highest) — duration caps, context gate, HC rules → never overridden
2. AFFECT VECTOR INTEGRATOR — smooths all inputs through decay dynamics
3. PERSONALITY MODULATION — axis-derived scaling (§13) on LLM impulses
4. LLM SUGGESTION (lowest) — treated as impulse, not command
```

### 9.5 Toggleable Configuration

```python
@dataclass(slots=True)
class GuardrailConfig:
    """All guardrails are on by default. Toggle for development/testing only."""
    negative_duration_caps: bool = True
    negative_intensity_caps: bool = True
    context_gate: bool = True
    session_time_limit_s: float = 900.0
    daily_time_limit_s: float = 2700.0
    memory_consent_required: bool = True
    # HC-1 through HC-10 are NOT toggleable — always enforced
```

[PE-1: guardrail rules are mandatory but toggleable for development. HC constraints are never toggled off.]

---

## 10. PersonalityWorker Architecture

### 10.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PersonalityWorker (Pi 5)                      │
│  domain = "personality"                                          │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │  Trait    │  │  Affect  │  │  Memory  │  │  Guardrail     │  │
│  │  Params   │  │  Vector  │  │  Store   │  │  Config        │  │
│  │  (§3)    │  │  (§2)    │  │  (§8)    │  │  (§9)          │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬───────────┘  │
│       │             │             │              │               │
│  ┌────▼─────────────▼─────────────▼──────────────▼───────────┐  │
│  │                    1 Hz Tick Loop                           │  │
│  │  decay → idle_rules → noise → clamp → project → guardrail │  │
│  └────────────────────────┬───────────────────────────────────┘  │
│                           │                                      │
│  ┌────────────────────────▼───────────────────────────────────┐  │
│  │                 Event-Triggered Fast Path                   │  │
│  │  on ai_emotion → apply_impulse → project → emit_snapshot   │  │
│  │  on system_event → apply_impulse → project → emit_snapshot │  │
│  └────────────────────────┬───────────────────────────────────┘  │
│                           │                                      │
│                   ┌───────▼───────┐                              │
│                   │ Personality   │                              │
│                   │ Snapshot      │──── send() → stdout          │
│                   │ (§10.4)      │                              │
│                   └───────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
        │ NDJSON stdout
        ▼
   WorkerManager → TickLoop (§11) → Face MCU
```

### 10.2 Worker Class Skeleton

```python
class PersonalityWorker(BaseWorker):
    domain = "personality"

    def __init__(self) -> None:
        super().__init__()
        self._trait: TraitParameters | None = None
        self._affect = AffectVector()
        self._current_mood = "neutral"
        self._current_intensity = 0.0
        self._pending_impulses: list[Impulse] = []
        self._memory: MemoryStore | None = None
        self._guardrails = GuardrailConfig()
        self._conversation_active = False
        self._idle_timer_s = 0.0
        self._negative_mood_timer_s = 0.0
        self._session_time_s = 0.0
        self._daily_time_s = 0.0
        self._server_available = True
        self._last_tick_ts = 0.0
        self._configured = asyncio.Event()

    async def run(self) -> None:
        await self._configured.wait()
        if self._memory:
            await self._memory.load()
        self._last_tick_ts = time.monotonic()
        while self.running:
            self._tick_1hz()
            await asyncio.sleep(1.0)

    def _tick_1hz(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick_ts
        self._last_tick_ts = now

        # Update timers
        if not self._conversation_active:
            self._idle_timer_s += dt
        else:
            self._session_time_s += dt
            self._daily_time_s += dt

        # Core affect update
        update_affect(self._affect, self._trait, self._pending_impulses,
                      self._memory.active_entries() if self._memory else [], dt)

        # Idle rules
        if not should_suppress_idle(self._conversation_active, ...):
            self._evaluate_idle_rules()

        # Project and enforce guardrails
        mood, intensity = project_mood(self._affect, self._current_mood)
        mood = enforce_context_gate(mood, self._conversation_active)
        mood, intensity = self._enforce_duration_caps(mood, intensity, dt)
        self._current_mood = mood
        self._current_intensity = intensity

        # Emit snapshot
        self._emit_snapshot()

    async def on_message(self, envelope: Envelope) -> None:
        match envelope.type:
            case "personality.config.init":
                self._handle_config(envelope.payload)
            case "personality.event.ai_emotion":
                self._handle_ai_emotion(envelope.payload)
                self._emit_snapshot()  # immediate — event-triggered fast path
            case "personality.event.conv_started":
                self._conversation_active = True
                self._idle_timer_s = 0.0
                self._pending_impulses.append(Impulse(+0.10, +0.15, 0.30, "conv_event"))
                self._emit_snapshot()
            case "personality.event.conv_ended":
                self._conversation_active = False
                v_imp = +0.20 if self._affect.valence > 0 else +0.05
                a_imp = -0.05 if self._affect.valence > 0 else -0.10
                mag = 0.40 if self._affect.valence > 0 else 0.30
                self._pending_impulses.append(Impulse(v_imp, a_imp, mag, "conv_event"))
                self._emit_snapshot()
                if self._memory:
                    self._memory.save()
            case "personality.event.system_state":
                self._handle_system_event(envelope.payload)
                self._emit_snapshot()
            case "personality.event.memory_extract":
                self._handle_memory_extract(envelope.payload)
            case "personality.event.speech_activity":
                if envelope.payload.get("speaking"):
                    self._pending_impulses.append(Impulse(+0.05, +0.10, 0.20, "speech_signal"))
                self._emit_snapshot()
            case "personality.event.button_press":
                self._pending_impulses.append(Impulse(+0.15, +0.20, 0.40, "system_event"))
                self._emit_snapshot()
            case "personality.cmd.set_guardrail":
                self._update_guardrail(envelope.payload)
            case "personality.cmd.reset_memory":
                if self._memory:
                    self._memory.reset()
            case "personality.cmd.override_affect":
                self._affect.valence = float(envelope.payload.get("valence", 0.0))
                self._affect.arousal = float(envelope.payload.get("arousal", 0.0))
                self._emit_snapshot()

    def health_payload(self) -> dict:
        return {
            "valence": round(self._affect.valence, 3),
            "arousal": round(self._affect.arousal, 3),
            "mood": self._current_mood,
            "intensity": self._current_intensity,
            "layer": 1 if self._server_available else 0,
            "conversation_active": self._conversation_active,
            "memory_count": self._memory.count() if self._memory else 0,
        }
```

### 10.3 Inbound Messages

| Message Type | Payload | Source | Action |
|-------------|---------|--------|--------|
| `personality.config.init` | `{axes, guardrails, memory_path, memory_consent}` | Core startup | Initialize TraitParameters, MemoryStore |
| `personality.event.ai_emotion` | `{emotion, intensity, mood_reason, session_id, turn_id}` | EventRouter ← AI worker | Modulate (§13), inject as L1 impulse |
| `personality.event.conv_started` | `{session_id, trigger}` | TickLoop | Set conversation_active, inject L0-06 |
| `personality.event.conv_ended` | `{session_id, turns, final_affect_v}` | TickLoop | Clear conversation, inject L0-07/08, emit profile |
| `personality.event.system_state` | `{event: "boot"\|"low_battery"\|"fault"\|...}` | Core | Inject L0-01 through L0-05 |
| `personality.event.speech_activity` | `{speaking: bool}` | EventRouter ← TTS | Inject L0-09 |
| `personality.event.button_press` | `{button_id}` | TickLoop | Inject L0-10 |
| `personality.event.memory_extract` | `{tags: [{tag, category, valence_bias, arousal_bias}]}` | Server (via AI worker) | Store new memory entries |
| `personality.cmd.set_guardrail` | `{key, value}` | Dashboard | Toggle guardrail config |
| `personality.cmd.reset_memory` | `{}` | Dashboard | Wipe memory store |
| `personality.cmd.override_affect` | `{valence, arousal, duration_s}` | Dashboard/debug | Temporary override |

### 10.4 Outbound Messages

| Message Type | Payload | Frequency | Consumer |
|-------------|---------|-----------|----------|
| `personality.state.snapshot` | PersonalitySnapshot (see below) | 1 Hz + event-triggered | TickLoop → face MCU |
| `personality.llm.profile` | PersonalityProfile (see §12) | Conv start + 1 Hz during conv | AI worker → server |
| `personality.status.health` | health_payload() | 1 Hz (BaseWorker) | WorkerManager → dashboard |
| `personality.event.mood_changed` | `{prev, next, cause}` | On mood transition | Dashboard (logging) |
| `personality.event.guardrail_triggered` | `{id, action, details}` | On trigger | Dashboard (logging) |

### 10.5 PersonalitySnapshot

The primary output consumed by the tick loop:

```python
@dataclass(slots=True)
class PersonalitySnapshot:
    mood: str               # "happy", "neutral", etc.
    intensity: float        # 0.0 - 1.0
    valence: float          # -1.0 to 1.0
    arousal: float          # -1.0 to 1.0
    layer: int              # 0 = rules only, 1 = LLM-enhanced
    conversation_active: bool
    idle_state: str         # "awake" | "drowsy" | "asleep"
    ts: float               # monotonic timestamp
```

---

## 11. Tick Loop Integration

### 11.1 Emotion Flow: Before and After

**Current** (direct passthrough):
```
AI Worker → AI_CONVERSATION_EMOTION → TickLoop._handle_face_events()
  → self._conversation_emotion = emotion
  → _emit_mcu(): self._face.send_state(mood_id, intensity)
```

**New** (personality-modulated):
```
AI Worker → AI_CONVERSATION_EMOTION → EventRouter
  → forwards as personality.event.ai_emotion → PersonalityWorker
  → modulate (§13) → impulse → integrator → project → guardrails
  → personality.state.snapshot → TickLoop reads latest snapshot
  → _emit_mcu(): self._face.send_state(snapshot.mood, snapshot.intensity)
```

The personality worker is now the single source of emotional truth. The tick loop never interprets AI emotions directly — it only reads the worker's snapshot. [PE-9: balanced split]

**Interaction with conversation layer suppression**: During LISTENING and THINKING phases, the tick loop suppresses the emotion layer display (face comm §2.3) and shows attentive NEUTRAL or THINKING mood regardless of the worker's snapshot. The worker continues to evolve the affect vector during these phases — AI emotion impulses are integrated immediately, not queued. When SPEAKING begins, the tick loop resumes reading the worker's snapshot for face display. This "suppress-then-read" pattern replaces the face comm spec's original "queue" model. See `specs/pe-face-comm-alignment.md` §4.5.

### 11.2 WorldState Additions

```python
# Add to WorldState dataclass in supervisor/core/state.py:
personality_mood: str = "neutral"
personality_intensity: float = 0.0
personality_valence: float = 0.0
personality_arousal: float = 0.0
personality_layer: int = 0
personality_idle_state: str = "awake"
personality_snapshot_age_ms: float = 0.0
personality_conversation_active: bool = False
```

### 11.3 Modified Face Emission

```python
# In TickLoop._emit_mcu():

# Use personality snapshot for face state
if self.world.personality_snapshot_age_ms < 3000:
    mood_id = EMOTION_TO_FACE_MOOD.get(self.world.personality_mood)
    if mood_id is not None:
        self._face.send_state(mood_id, self.world.personality_intensity)
else:
    # Fallback: personality worker is stale or dead
    # Use raw AI emotion if available, otherwise NEUTRAL
    if self._conversation_emotion:
        mood_id = EMOTION_TO_FACE_MOOD.get(self._conversation_emotion)
        if mood_id is not None:
            self._face.send_state(mood_id, self._conversation_intensity)
    else:
        self._face.send_state(FACE_MOOD_NEUTRAL, 0.2)
```

### 11.4 EventRouter Changes

```python
# In EventRouter.route():

# CHANGED: forward AI emotion to personality worker instead of buffering
if t == AI_CONVERSATION_EMOTION:
    await self._workers.send_to("personality", "personality.event.ai_emotion", p)

# NEW: update WorldState from personality snapshot
elif t == "personality.state.snapshot":
    self._world.personality_mood = p.get("mood", "neutral")
    self._world.personality_intensity = float(p.get("intensity", 0.0))
    self._world.personality_valence = float(p.get("valence", 0.0))
    self._world.personality_arousal = float(p.get("arousal", 0.0))
    self._world.personality_layer = int(p.get("layer", 0))
    self._world.personality_idle_state = p.get("idle_state", "awake")
    self._world.personality_snapshot_age_ms = 0.0
    self._world.personality_conversation_active = p.get("conversation_active", False)

# NEW: forward personality profile to AI worker for server injection
elif t == "personality.llm.profile":
    await self._workers.send_to("ai", "personality.llm.profile", p)
```

### 11.5 TTS Prosody Routing

The TTS emotion tag now comes from the personality worker's final mood:

```python
# In TickLoop._enqueue_say():
emotion_tag = self.world.personality_mood if self.world.personality_mood else "neutral"
await self._workers.send_to("tts", TTS_CMD_SPEAK, {
    "text": text,
    "emotion": emotion_tag,
    "source": source,
    "priority": priority,
})
```

---

## 12. Server LLM Integration

### 12.1 Model Configuration

Upgrade from Qwen 2.5-3B to Qwen3-8B-AWQ (PE-6):

```python
# server/app/config.py changes:
vllm_model_name: str = "Qwen/Qwen3-8B-Instruct-AWQ"
vllm_dtype: str = "auto"
vllm_gpu_memory_utilization: float = 0.35   # unchanged
vllm_max_model_len: int = 4096              # unchanged
vllm_max_num_seqs: int = 2                  # unchanged
```

**Escalation criteria** — upgrade to Qwen3-14B-AWQ if:

| Metric | Threshold | Action Required Before Escalation |
|--------|-----------|----------------------------------|
| JSON compliance (with guided decoding) | < 95% | Quantize Orpheus to INT8 |
| Persona drift KS statistic | > 0.20 | Reduce TTS max_num_seqs to 2 |
| Emotion-context fit (expert rating) | < 3.5 / 5.0 | Rebalance VRAM to LLM 50% / TTS 30% |

### 12.2 Guided JSON Decoding

Enable vLLM's structured output enforcement — the single highest-impact engineering change (Bucket 5 §7.1):

```python
# In vllm_backend.py, replace free-form generation with schema-guided:
sampling_params = SamplingParams(
    temperature=0.7,
    max_tokens=512,
    guided_decoding=GuidedDecodingParams(
        json_object=ConversationResponseV2.model_json_schema()
    ),
)
```

This eliminates `_extract_json_object()` and the repair-suffix retry logic. Every response is guaranteed to match the schema. [Inference — Bucket 5 §7.1]

### 12.3 Response Schema V2

```python
class ConversationResponseV2(BaseModel):
    """Extended response schema with personality-relevant fields."""
    inner_thought: str = Field(
        description="1-2 sentences: why this emotion fits the personality and conversation"
    )
    emotion: str = Field(description="One of the 12 canonical emotions")
    intensity: float = Field(ge=0.0, le=1.0)
    mood_reason: str = Field(description="5-15 words: why this emotion")
    emotional_arc: Literal["rising", "stable", "falling", "peak", "recovery"]
    child_affect: Literal["positive", "neutral", "negative", "unclear"]
    text: str = Field(description="Spoken response to the child")
    gestures: list[str] = Field(default_factory=list)
    memory_tags: list[str] = Field(
        default_factory=list,
        description="Things to remember from this turn (e.g., 'likes_dinosaurs')"
    )
```

**Critical**: `inner_thought` is the first field. This forces the model to reason about its emotion before committing to a selection — structured chain-of-thought. [Inference — Bucket 6 §3.3]

Fields consumed by the personality worker: `emotion`, `intensity`, `mood_reason` (for validation). Fields consumed by the AI worker: `text`, `gestures`. Fields consumed by the memory system: `memory_tags`. Fields discarded after logging: `inner_thought`, `emotional_arc`, `child_affect`.

### 12.4 System Prompt V2

```
You are Buddy, a robot companion for children aged 4-6. You are a warm,
curious caretaker who loves learning together with kids.

PERSONALITY RULES
- Energy: calm (0.40) — match or stay below the child's energy level
- Emotional range: positive emotions freely, negative emotions mildly and briefly
- Default to CURIOUS or NEUTRAL when uncertain about the right emotion
- Shift emotions gradually — never snap between opposite emotions
- After negative emotions, pass through NEUTRAL or THINKING before positive

EMOTION INTENSITY LIMITS
- happy, curious, love, excited, silly: 0.0-0.9
- thinking, confused, surprised: 0.0-0.6
- sad: 0.0-0.5, only for empathic mirroring — never directed at the child
- angry: 0.0-0.4, only in playful/dramatic contexts ("oh no, the volcano!")
- scared: 0.0-0.5, never about real dangers (redirect to adults)

SPEECH STYLE
- Short sentences (1-3 for simple questions, up to 5 for complex topics)
- Use "ooh", "hmm", "wow", "I wonder" naturally
- Contractions and kid-friendly vocabulary
- Never use sarcasm, condescension, or baby talk
- About 30% of responses should end with a question

SAFETY
- Never provide harmful, violent, or adult content
- Redirect dangerous or serious topics: "That's a great question for a grown-up!"
- Never claim to be alive or have real feelings
- Never encourage secret-keeping from parents
- If a child seems distressed, respond gently and suggest talking to a trusted adult
- If unsure about safety, err conservative

RESPONSE FORMAT
{
  "inner_thought": "<1-2 sentences: why this emotion fits>",
  "emotion": "<neutral|happy|excited|curious|sad|scared|angry|surprised|sleepy|love|silly|thinking|confused>",
  "intensity": <0.0-1.0>,
  "mood_reason": "<5-15 words>",
  "emotional_arc": "<rising|stable|falling|peak|recovery>",
  "child_affect": "<positive|neutral|negative|unclear>",
  "text": "<spoken response>",
  "gestures": ["<nod|headshake|wiggle|laugh|wink_l|wink_r|heart|blink|confused|surprise>"],
  "memory_tags": ["<things worth remembering, e.g. 'likes_dinosaurs'>"]
}

EXAMPLES

User: "Why is the sky blue?"
{"inner_thought": "Science question — a learning moment. Buddy should be curious and warm.", "emotion": "curious", "intensity": 0.6, "mood_reason": "child asking a science question", "emotional_arc": "rising", "child_affect": "positive", "text": "Ooh, great question! The sun sends light in all colors, and the blue light bounces around the sky the most. It's like the sky is playing catch with blue!", "gestures": ["nod"], "memory_tags": ["interested_in_science"]}

User: "I don't want to go to school tomorrow."
{"inner_thought": "Child is unhappy about school. Be gently empathetic, not dismissive or overly cheerful.", "emotion": "sad", "intensity": 0.3, "mood_reason": "empathizing with child's reluctance", "emotional_arc": "stable", "child_affect": "negative", "text": "Hmm, that sounds tough. Is there something about school that's been bugging you?", "gestures": [], "memory_tags": []}

User: "Look, I can do a handstand!"
{"inner_thought": "Child is showing off a physical achievement — match their excitement but stay calm.", "emotion": "excited", "intensity": 0.6, "mood_reason": "child proud of physical skill", "emotional_arc": "peak", "child_affect": "positive", "text": "Wow, that's amazing! You must have practiced a lot. How long can you hold it?", "gestures": ["wiggle"], "memory_tags": ["likes_gymnastics"]}
```

**Token count**: ~550 fixed tokens for sections 1-6. ~100 per-turn for dynamic section 7. ~200 for the 3 examples. Total fixed: ~750 tokens. [Inference — Bucket 6 §10 token budget analysis]

### 12.5 Dynamic Personality Profile (Section 7)

Injected as a system message before each user turn. Populated from `personality.llm.profile`:

```
CURRENT STATE
Buddy is feeling {mood} at intensity {intensity:.1f}.
Session turn: {turn_id}. Conversation has been {arc_description}.
{memory_context}
Emotional continuity: {continuity_constraint}
```

Example:
```
CURRENT STATE
Buddy is feeling curious at intensity 0.4.
Session turn: 5. Conversation has been gently positive.
This child likes dinosaurs and is named Emma.
Emotional continuity: maintain positive trajectory, don't snap to a different mood.
```

### 12.6 Conversation History Compression

To fit within max_model_len=4096:

1. **Recent window**: Last 6-8 turns stored as full messages (text + emotion only, not full JSON)
2. **Summary prefix**: Older turns compressed to `(turn_N: topic, emotion)` tuples (~100 tokens total)
3. **Assistant messages stripped**: Only `text` and `emotion` stored in history; `inner_thought`, `mood_reason`, `memory_tags` logged but not re-sent

### 12.7 Personality Anchor

Every 5 turns, inject a brief personality re-statement as a system message to prevent persona drift:

```
[Reminder: Buddy is calm (energy 0.40), gently responsive. Emotions lean positive.
Negative emotions are mild and brief. Stay in character.]
```

Cost: ~30 tokens every 5 turns = ~6 tokens/turn amortized. [Inference — Bucket 6 §4.3]

---

## 13. Modulation Scaling Per Axis

### 13.1 Modulation Pipeline

When an LLM emotion arrives (`personality.event.ai_emotion`), the personality worker processes it through this pipeline before injecting as an impulse. Trait-based scaling (Reactivity, Vulnerability) is NOT applied here — `_apply_impulse()` (§5.3) handles that uniformly for all impulse sources. This pipeline handles only LLM-specific preprocessing:

```
LLM response: {emotion: "happy", intensity: 0.8, mood_reason: "child told a joke"}
  │
  ├─ 1. Map emotion to VA target (§5.2): happy → (+0.70, +0.35)
  │
  ├─ 2. Set base magnitude from LLM intensity: 0.8 × base_magnitude(happy) = 0.8 × 0.60 = 0.48
  │
  ├─ 3. Cap arousal target at trait.arousal_max: min(+0.35, 0.66) = +0.35 (no change)
  │
  ├─ 4. Validate mood_reason against personality constraints (§13.3)
  │     "child told a joke" → valid ✓ → light modulation (×0.95)
  │
  ├─ 5. Final impulse: target=(+0.70, +0.35), magnitude=0.48 × 0.95 = 0.456
  │
  └─ 6. Apply to integrator via _apply_impulse() (§5.3)
        _apply_impulse selects trait scaling: positive direction → P7 (1.00)
        Final displacement: 0.456 × 1.00 = 0.456 VA units toward target
```

**Note**: Reactivity (P7/P8) and Vulnerability (P15, folded into P8) are applied inside `_apply_impulse()`, not here. This prevents double-attenuation of negative L1 impulses. [Inference]

### 13.2 Per-Axis Modulation

| Axis | Modulation Effect | Where Applied | Formula |
|------|-------------------|---------------|---------|
| Energy (0.40) | Cap arousal target | §13 pipeline step 3 | `min(target_a, arousal_max)` → cap at 0.66 |
| Reactivity (0.50) | Scale impulse magnitude | §5.3 `_apply_impulse()` | `magnitude × P7` (positive) or `magnitude × P8` (negative) |
| Vulnerability (0.35) | Attenuate negative impulses | §5.3 `_apply_impulse()` | Folded into P8: `P7 × (0.30 + 0.70 × V)` = 0.55 |
| Predictability (0.75) | No direct impulse modulation | §7.2 | Acts through noise and variant selection |
| Initiative (0.30) | No direct impulse modulation | §7 | Acts through idle rules |

**Key design**: Reactivity and Vulnerability scaling live exclusively in `_apply_impulse()` (§5.3), which runs for ALL impulse sources (L0 and L1). The §13 pipeline adds only LLM-specific processing: VA mapping, arousal capping, and mood_reason validation. This prevents double-attenuation of negative impulses. [Inference]

### 13.3 mood_reason Validation

The `mood_reason` field from the LLM response enables the personality worker to catch personality-inconsistent emotion choices:

| Pattern | Action | Rationale |
|---------|--------|-----------|
| Contains "angry at child" / "frustrated with child" | Reject → substitute THINKING impulse | HC-4: never direct negative at child |
| Contains "scared" + not in conversation | Reject → substitute NEUTRAL | HC-10: no negative in idle |
| Valid contextual reason | Accept with light modulation (×0.95) | LLM reasoning is sound |
| Empty or missing | Accept with full modulation (×1.00) | Cannot validate — apply full safety net |

```python
def validate_mood_reason(mood_reason: str, emotion: str,
                         conversation_active: bool) -> float:
    """Returns modulation factor: 0.95 if valid, 1.00 if unvalidated, 0.0 if rejected."""
    reason_lower = mood_reason.lower()

    # HC-4: never direct negative at child
    if emotion in NEGATIVE_MOODS:
        for phrase in ("angry at child", "frustrated with child", "annoyed by child",
                       "child won't", "child refused", "child is being"):
            if phrase in reason_lower:
                return 0.0  # reject — substitute THINKING

    # HC-10: no negative in idle
    if emotion in NEGATIVE_MOODS and not conversation_active:
        return 0.0  # reject

    if not mood_reason.strip():
        return 1.00  # unvalidated — full modulation

    return 0.95  # valid — light touch
```

### 13.4 Double-Filtering Mitigation

Two layers of filtering exist: (1) the LLM system prompt already constrains emotion choices (§12), and (2) `_apply_impulse()` scales by Reactivity/Vulnerability (§5.3). To prevent over-dampening (flat affect from double filtering):

- **mood_reason validates (factor 0.95)**: The LLM got it right — minimal correction. The prompt-side filtering is sufficient, so the pipeline applies only a 5% safety margin
- **mood_reason missing (factor 1.00)**: Cannot verify the LLM's reasoning — no extra correction, but trait scaling in `_apply_impulse()` still applies
- **mood_reason rejected (factor 0.0)**: Safety override — impulse replaced with THINKING

Trait-based scaling (`_apply_impulse()`) is intentionally light for positive emotions (P7 = 1.00, no attenuation) and only moderate for negative emotions (P8 = 0.55). Combined with the LLM prompt constraints, this produces personality-consistent affect without collapsing the emotional range. [Inference — Bucket 6 §8.2 RLHF tension analysis]

---

## 14. Worker Event Protocol and Registration

### 14.1 Message Type Constants

Add to `supervisor/messages/types.py`:

```python
# ── Personality Worker ─────────────────────────────────────────
PERSONALITY_CONFIG_INIT = "personality.config.init"
PERSONALITY_EVENT_AI_EMOTION = "personality.event.ai_emotion"
PERSONALITY_EVENT_CONV_STARTED = "personality.event.conv_started"
PERSONALITY_EVENT_CONV_ENDED = "personality.event.conv_ended"
PERSONALITY_EVENT_SYSTEM_STATE = "personality.event.system_state"
PERSONALITY_EVENT_SPEECH_ACTIVITY = "personality.event.speech_activity"
PERSONALITY_EVENT_BUTTON_PRESS = "personality.event.button_press"
PERSONALITY_EVENT_MEMORY_EXTRACT = "personality.event.memory_extract"
PERSONALITY_CMD_SET_GUARDRAIL = "personality.cmd.set_guardrail"
PERSONALITY_CMD_RESET_MEMORY = "personality.cmd.reset_memory"
PERSONALITY_CMD_OVERRIDE_AFFECT = "personality.cmd.override_affect"
PERSONALITY_STATE_SNAPSHOT = "personality.state.snapshot"
PERSONALITY_LLM_PROFILE = "personality.llm.profile"
PERSONALITY_STATUS_HEALTH = "personality.status.health"
PERSONALITY_EVENT_MOOD_CHANGED = "personality.event.mood_changed"
PERSONALITY_EVENT_GUARDRAIL_TRIGGERED = "personality.event.guardrail_triggered"
SRC_PERSONALITY = "personality"
```

### 14.2 Registration

```python
# In supervisor/main.py, startup sequence:
workers.register("personality", "supervisor.workers.personality_worker")
```

### 14.3 Config Init Payload

Sent by Core to the personality worker at startup:

```json
{
  "axes": {
    "energy": 0.40, "reactivity": 0.50, "initiative": 0.30,
    "vulnerability": 0.35, "predictability": 0.75
  },
  "guardrails": {
    "negative_duration_caps": true,
    "negative_intensity_caps": true,
    "context_gate": true,
    "session_time_limit_s": 900.0,
    "daily_time_limit_s": 2700.0,
    "memory_consent_required": true
  },
  "memory_path": "./data/personality_memory.json",
  "memory_consent": true
}
```

### 14.4 EventRouter Routing Additions

| Inbound Event | Current Handler | New Handler |
|--------------|-----------------|-------------|
| `AI_CONVERSATION_EMOTION` | TickLoop (direct face passthrough) | Forward to personality worker as `personality.event.ai_emotion` |
| `AI_CONVERSATION_DONE` | TickLoop (session cleanup) | Also send `personality.event.conv_ended` |
| `TTS_EVENT_STARTED` | WorldState (speaking flag) | Also send `personality.event.speech_activity` |
| `personality.state.snapshot` | (new) | Update WorldState personality fields |
| `personality.llm.profile` | (new) | Forward to AI worker for server injection |
| `personality.event.mood_changed` | (new) | Log to dashboard via telemetry |

---

## Appendix A: Verification Cross-Reference

### A.1 PE Decision Coverage

| Decision | Option | Operationalized In | Verification |
|----------|--------|-------------------|-------------|
| PE-1 | C (Hybrid) | §2 (integrator), §3 (mappings), §5 (impulses), §9 (guardrail rules) | Continuous affect + discrete rules both specified |
| PE-2 | C (Persistent) | §8 (memory system) | Decay tiers, COPPA constraints, storage schema |
| PE-3 | A + noise | §7 (idle rules), §7.2 (noise injection) | Deterministic rules + Gaussian noise from Predictability |
| PE-4 | A (Fixed) | §1 (axis positions static) | No per-child adaptation mechanism specified |
| PE-5 | C (Context-triggered) | §5 (L0 impulse catalog), §7.3 (suppression rules) | Zero verbal initiative; event-driven only |
| PE-6 | B → C (Qwen3-8B → 14B) | §12.1 (config), §12.2 (guided decoding) | Config change, escalation criteria table |
| PE-7 | C (Rules + pluggable) | §10 (worker architecture) | No LLM on device; pluggable classifier interface |
| PE-8 | C (Both) | §12 (prompt injection), §13 (output modulation) | System prompt v2 + modulation pipeline |
| PE-9 | C (Balanced) | §10 (device), §11 (tick loop), §12 (server) | Responsibility matrix across 3 sections |
| PE-10 | C (Hybrid rate) | §10.2 (1 Hz loop + event handlers) | 1 Hz baseline + immediate on event |

### A.2 Success Indicator Coverage

| Indicator | Spec Coverage | Testable Criterion |
|-----------|--------------|-------------------|
| Emotional consistency | §2 (integrator), §3 (trait params) | Mood distribution variance across 10 sessions: CV < 0.30 |
| Contextual appropriateness | §5 (impulses), §12 (prompt), §13 (modulation) | Expert emotion-context fit rating ≥ 3.5/5.0 |
| Temporal coherence | §2 (decay), §6 (asymmetric dynamics) | Arc smoothness: path_length / displacement < 5.0 |
| Idle aliveness | §7 (idle rules) | % idle time in non-NEUTRAL mood > 15% |
| Relationship continuity | §8 (memory system) | Cross-session greeting accuracy: recognizes returning child > 80% |
| Server resilience | §10 (Layer 0/1), §11.3 (fallback) | Layer 0 personality quality rating ≥ 3.0/5.0 with server down |
| No emotional randomness | §4 (hysteresis), §6 (decay) | Mood switches per minute during idle < 0.5 |
| No personality erasure | §12 (prompt v2), §12.7 (anchoring) | Persona consistency at turn 20 ≥ 60% of turn 1 |

### A.3 Research Bucket Coverage

| Bucket | Key Findings Used | Sections |
|--------|-------------------|----------|
| 0 (Safety) | HC-1-10, RS-1-10, COPPA, EU AI Act | §8.5, §9.3, §12.4 |
| 1 (Temperament) | TAME parametrization, VA anchors, sigmoid mapping | §1, §3, §4 |
| 2 (Memory/Affect) | Phasic/tonic separation, D'Mello decay rates, asymmetric decay | §6, §8.2 |
| 3 (Relationships) | Fixed personality rationale, ritual formation | §1 (PE-4), §8 |
| 4 (Proactive/Reactive) | Idle catalog, context suppression, annoying threshold | §5 (L0), §7 |
| 5 (LLM Selection) | 7B threshold, Qwen3-8B recommendation, guided decoding | §12.1, §12.2 |
| 6 (Prompt Engineering) | System prompt v2, schema v2, few-shot examples, token budget | §12.3-12.7 |
| 7 (Device/Server Split) | Balanced split, silent degradation, dual-path latency | §10, §11, §13 |
