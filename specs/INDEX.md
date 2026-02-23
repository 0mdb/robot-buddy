# Specifications Index

Quick reference for navigating the spec documents. Use section links for targeted reading.

## Face Communication

### [face-communication-spec-stage1.md](face-communication-spec-stage1.md)
Research foundations. Defines the research approach (3 buckets), verified system snapshot, and design methodology. Start here for understanding the research basis.

### [face-communication-spec-stage2.md](face-communication-spec-stage2.md)
**Full implementation-ready spec** (~1340 lines). The primary reference for face communication work.
- §1-2: Intent taxonomy, personality profile, channel allocation
- §3: Layer interaction rules (emotion suppression, queue-during/apply-on-speaking)
- §4: Visual grammar — 13 moods, 13 gestures, eye scale, color, expression targets
- §5: Mood transition choreography (blink → ramp-down → switch → ramp-up)
- §6: Latency targets (frame budget, command-to-pixel)
- §7: Negative affect guardrails (context gate, intensity caps, duration caps, auto-recovery)
- §8: Conversation states (8 states, transitions, auto-timeouts)
- §9: Protocol extensions (SET_CONV_STATE 0x25, SET_FLAGS 0x24)
- §12: Full conversation state machine with transition choreography

### [face-communication-eval-plan.md](face-communication-eval-plan.md)
Testing & evaluation framework with 4 tiers:
- T1: Automated CI (parity check, unit tests, linting)
- T2: Instrumented benchmarks (frame time, latency, SPI throughput)
- T3: Developer review (5 scenarios)
- T4: Child evaluation protocol (ages 4-6)

### [face-visual-language.md](face-visual-language.md)
Design reference for visual appearance. Defines intended look of all 13 moods, 13 gestures, and 8 conversation states. All parameter values marked [Provisional]. Includes:
- §1: Coordinate space, TN panel luma floor rule (L ≥ 85)
- §2-4: Per-mood eye scale, color, expression targets
- §5: Silhouette distinctiveness matrix, parity notes

## Personality Engine

### [personality-engine-spec-stage1.md](personality-engine-spec-stage1.md)
Research & decisions. 7 research buckets (safety psychology, temperament, memory, relationships, initiative, LLM selection, prompt engineering, device/server split). 10 decision points (PE-1 through PE-10) with approved options.

### [personality-engine-spec-stage2.md](personality-engine-spec-stage2.md)
**Full implementation-ready spec** (~1340 lines). The primary reference for personality engine work.
- §1-3: 5 personality axes, continuous affect vector (valence, arousal), decaying integrator
- §4: 13 mood anchors in VA space, asymmetric hysteresis projection
- §5: 20 axis-derived parameters
- §6: Impulse catalog (stimulus → affect delta)
- §7: Guardrails (duration caps, intensity caps, context gate)
- §8: Layer 0 (deterministic) vs Layer 1 (LLM-enhanced) architecture
- §9: Memory system (5 decay tiers, COPPA compliant)
- §10: Worker protocol (personality snapshot struct)
- §11: Tick loop integration (suppress-then-read model)
- §13: Evaluation metrics

### [pe-face-comm-alignment.md](pe-face-comm-alignment.md)
Alignment report reconciling the two independently-researched specs. 5 conflicts resolved:
1. Guardrail enforcement point (tiered model)
2. SURPRISED reclassification
3. Mood transition ownership
4. CONFUSED mood addition (13th mood)
5. Suppress-then-read model (replaces queue model)
