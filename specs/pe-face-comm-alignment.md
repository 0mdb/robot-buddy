# PE / Face Communication Alignment Report

**Date**: 2026-02-22
**Specs reconciled**:
- Face Communication Spec — Stage 2 (`face-communication-spec-stage2.md`)
- Personality Engine Spec — Stage 2 (`personality-engine-spec-stage2.md`)

---

## 1. Executive Summary

Five conflicts identified between the independently-researched PE and face communication specs. All five resolved via amendments to both specs. Key architectural decision: the personality worker is the **single source of emotional truth**; the tick loop is the **visual orchestrator and safety backstop**.

Both specs are now internally consistent and can serve as authoritative implementation references without contradiction.

## 2. Conflict Resolution Summary

| # | Conflict | Resolution | FC Sections Amended | PE Sections Amended |
|---|----------|------------|---------------------|---------------------|
| 1 | Guardrail enforcement point | Tiered: PE worker primary, tick_loop backstop (stale > 3 s) | §7, §7.3 | §9.1, §9.2 |
| 2 | SURPRISED classification | Reclassify as Neutral; keep 3.0 s / 0.8 cap as startle reflex safety in new §7.4 | §4.1.1, §7.1, §7.2, §7.3, §7.4 (new) | §4.2 (comment), §9.1 (note) |
| 3 | Mood transition ownership | PE worker decides mood; tick_loop orchestrates visual choreography (§5.1.1) | §5.1.1, §9.6 | §11.1 |
| 4 | 13 vs 12 moods (CONFUSED) | Add CONFUSED to FC with face parameter targets (provisional) | §4.1.1, §4.1.2 | (none) |
| 5 | Emotion "queue" during suppression | Replace "queue" with suppress-then-read model | §2.3, §12.3 | §11.1 |

## 3. Alignment Points (No Conflict)

| Area | FC Scope | PE Scope | Relationship |
|------|----------|----------|-------------|
| TTS Prosody | Visual lip sync only (§6.3) | Prosody tag routing (§11.5) | Complementary scopes |
| Idle Behavior | MCU cosmetic: breathing, blink, gaze wander (§4.3) | Worker emotional: idle mood shifts, SLEEPY drift (§7) | Clean channel separation |
| Context Gate | Safety backstop (§7.3) | Primary enforcement (§9.2) | Tiered (resolved with Conflict 1) |
| Personality Axes | §1 axis table | §1.1 axis table | Identical values |
| Channel Allocation | §3 ownership table | §11.1 emotion flow | PE feeds into existing Layer 3 |
| Gesture Catalog | §8 gesture IDs | §12.3 gestures field | Same gesture set |
| Conversation State Machine | §12 full state machine | §10.3 conv events | PE receives events; does not control state machine |

## 4. Detailed Conflict Analysis

### 4.1 Conflict 1: Guardrail Enforcement Point

**The problem**: FC §7 says the supervisor `tick_loop` tracks negative mood duration and enforces caps. PE §9 says the personality worker tracks duration and injects recovery impulses. Both use the same numbers (SAD 4 s, SCARED/ANGRY 2 s, intensity caps SAD 0.7 / SCARED 0.6 / ANGRY 0.5). Running both would cause double enforcement — the worker would recover and then the tick_loop would redundantly recover again.

**Resolution**: Tiered enforcement.

- **Primary (normal operation)**: The personality worker enforces all guardrails. Its recovery impulse pulls the affect vector toward baseline, and the projected mood in the snapshot reflects this recovery automatically. The tick_loop trusts the snapshot.
- **Backstop (worker failure)**: If the personality worker's snapshot is stale (age > 3000 ms), the tick_loop falls back to raw AI emotion passthrough (PE §11.3) and independently enforces the same duration caps and context gate. This prevents a dead worker from leaving a negative mood stuck on the face.

**Why PE worker is primary**: The worker owns the affect vector integrator, which already naturally decays negative impulses (decay_multiplier_negative = 1.30, faster than positive). Duration caps are a secondary safety net. Having the worker enforce them means the recovery is smooth (impulse-based, through the integrator) rather than abrupt (tick_loop forcing a mood switch). The tick_loop backstop is intentionally identical in limits but cruder in execution — it's a safety net, not the happy path.

**Stale threshold (3000 ms)**: Chosen as 3x the worker's 1 Hz baseline tick. Short enough that a crashed worker is detected within seconds; long enough that GC pauses or event bursts don't trigger false backstop activation. Recommend making this a tunable constant.

### 4.2 Conflict 2: SURPRISED Classification

**The problem**: FC §4.1.1 classifies SURPRISED as Negative (alongside SAD, SCARED, ANGRY). PE §4.1 places SURPRISED at (V=+0.15, A=+0.80) — positive valence, high arousal — and classifies it as Neutral. PE's `NEGATIVE_MOODS` frozenset is `{"sad", "scared", "angry"}` and explicitly excludes SURPRISED.

**Resolution**: Reclassify SURPRISED as Neutral in the face comm spec.

**Rationale**: PE's VA-space placement is principled — SURPRISED has positive valence (+0.15), which is definitionally not negative. The original Negative classification in FC was based on caution (high arousal can be startling), not on the emotion's valence. The FC spec already noted "surprise is brief and often positive-valent" (§7.2) and provided a context-gate exception for SURPRISED outside conversation (§7.3), both of which are more consistent with Neutral classification.

**What stays**: The 3.0 s maximum duration and 0.8 intensity cap remain, but move to a new §7.4 "Startle Reflex Safety" subsection. High arousal shouldn't persist regardless of valence class. The caps are a **startle reflex safety rule**, not a negative-affect guardrail.

**Context gate impact**: SURPRISED is no longer context-gated (Neutral moods are unrestricted). The §7.3 "exception" language is removed because there's nothing to except from. The startle reflex safety (§7.4) applies in all contexts.

### 4.3 Conflict 3: Mood Transition Ownership

**The problem**: FC §5.1.1 says mood transitions are "triggered when supervisor sends SET_STATE with a different mood_id than the current mood." This implies the supervisor directly chooses moods. PE §4/§10/§11 says the personality worker projects mood from the affect vector via hysteresis, and emits snapshots. The tick_loop reads snapshots and passes them through.

**Resolution**: Two-part ownership. PE worker decides **what** mood. Tick_loop decides **how** to display it.

1. PE worker: Integrates impulses → decays → projects mood via hysteresis → applies guardrails → emits snapshot with (mood, intensity)
2. Tick_loop: Reads snapshot → detects mood change (new mood differs from currently displayed mood) → initiates §5.1.1 choreography (blink → ramp-down → switch → ramp-up)

The tick_loop does not choose moods. It is a visual orchestrator that translates mood decisions into smooth face transitions. FC §5.1.1 is correct about the choreography mechanics; it just needed to clarify the trigger source.

### 4.4 Conflict 4: CONFUSED Mood Addition

**The problem**: PE spec defines 13 mood anchors including CONFUSED (V=-0.20, A=+0.30, Neutral class). FC spec defines only 12 — no CONFUSED mood or face parameter targets. If the PE worker projects CONFUSED, the tick_loop has no `FaceMood.CONFUSED` to send to the MCU, and the MCU has no parameter targets to render.

**Resolution**: Add CONFUSED to FC §4.1.1 (Neutral class) and §4.1.2 (face parameter targets).

**Proposed face parameters** (provisional — need sim prototyping):

| Mood | mouth_curve | mouth_width | mouth_open | lid_slope | lid_top | lid_bot | Face Color (R,G,B) |
|------|:-----------:|:-----------:|:----------:|:---------:|:-------:|:-------:|:-------------------:|
| CONFUSED | -0.2 | 1.0 | 0.0 | -0.15 | 0.1 | 0.0 | (200, 160, 80) |

**Design rationale**: Mild furrowed brow (lid_slope -0.15), slightly raised upper lid (0.1). Very slight frown (mouth_curve -0.2), mouth closed. Warm amber-brown face color, distinct from all 12 existing moods. Less expressive than CURIOUS (lid_slope -0.3) to convey "uncertain" rather than "interested."

**Firmware impact**: Requires `Mood::CONFUSED = 12` in MCU face_state.h enum, parameter targets in face_state.cpp, `CONFUSED = 12` in supervisor FaceMood enum, and expression map update. This is a Stage 3/Phase 0 firmware change, not done during this alignment review.

**Note**: The CONFUSED *gesture* (GestureId::CONFUSED = 3) already exists on the MCU. The CONFUSED *mood* is distinct — a sustained tonic state rather than a transient phasic animation.

### 4.5 Conflict 5: Emotion Queue During Suppression

**The problem**: FC §2.3 says during LISTENING/THINKING, incoming AI emotion commands are "queued" and "applied on SPEAKING entry." But in the PE architecture, there is no queue. The personality worker's affect integrator runs continuously — AI emotion impulses are integrated immediately into the affect vector, even during LISTENING/THINKING. The vector evolves continuously via decay, impulses, and noise.

**Resolution**: Replace "queue" with "suppress-then-read."

1. During LISTENING/THINKING: The tick_loop suppresses the emotion layer display (shows attentive NEUTRAL @ 0.3 or THINKING @ 0.5 per FC §4.2.2). The PE worker continues receiving and integrating AI emotion impulses into the affect vector.
2. On SPEAKING entry: The tick_loop reads the PE worker's current snapshot. The snapshot's mood already reflects all impulses integrated during LISTENING/THINKING (smoothed by the integrator, not raw). The tick_loop initiates §5.1.1 choreography toward this mood.

**Why this is better than a queue**: The integrator provides natural smoothing. If the AI sends HAPPY during LISTENING and then SAD during THINKING, the affect vector ends up somewhere between them (weighted by decay and recency), not at the last-queued value. This produces more emotionally coherent face behavior.

## 5. Data Flow Diagram (Post-Alignment)

```
AI Worker ─── AI_CONVERSATION_EMOTION ──> EventRouter
                                              |
                               personality.event.ai_emotion
                                              |
                                              v
                                    PersonalityWorker
                                    |-- modulate (PE §13)
                                    |-- impulse -> integrator
                                    |-- decay -> project -> guardrails
                                    '-- emit snapshot
                                              |
                               personality.state.snapshot
                                              |
                                              v
                                    WorldState update
                                              |
                                              v
                                    TickLoop._emit_mcu()
                                    |-- snapshot fresh? -> use worker mood
                                    |-- snapshot stale? -> fallback to raw AI emotion
                                    |-- detect mood change? -> choreography (FC §5.1.1)
                                    '-- conv suppression? -> show NEUTRAL/THINKING
                                              |
                                         SET_STATE
                                              |
                                              v
                                         Face MCU
                                    |-- apply mood parameters
                                    |-- MCU cosmetic idle (breathing, blink, gaze)
                                    '-- render -> display
```

## 6. Firmware Impact

| Change | File | Description | When |
|--------|------|-------------|------|
| Add CONFUSED mood enum | `esp32-face-v2/main/face_state.h` | `CONFUSED = 12` in Mood enum | Stage 3 / Phase 0 |
| CONFUSED parameters | `esp32-face-v2/main/face_state.cpp` | Add target table entry + color | Stage 3 / Phase 0 |
| Protocol enum | `supervisor_v2/devices/protocol.py` | `CONFUSED = 12` in FaceMood | Stage 3 / Phase 0 |
| Expression map | `supervisor_v2/devices/expressions.py` | Add "confused" mapping | Stage 3 / Phase 0 |

No firmware changes are made during the alignment review. These are recorded for Stage 3.

## 7. Implementation Priority

When implementing Stage 3+:

1. **CONFUSED mood firmware addition** (C4) — blocks face display of PE's 13th mood
2. **Tiered enforcement wiring** (C1) — safety-critical, implement early
3. **Suppress-then-read in tick loop** (C5) — behavior change during conversation
4. **Mood transition ownership wiring** (C3) — requires snapshot consumption
5. **Cross-reference annotations** (all) — documentation consistency

## 8. Open Questions

1. **CONFUSED face parameters are provisional**. The values (lid_slope=-0.15, lid_top=0.1, color=(200,160,80)) need sim prototyping (Stage 3) and child recognition testing in T3/T4 evaluation phases.
2. **Stale threshold of 3000 ms for safety backstop** — is this the right value? Too short may cause false backstop activation during GC pauses. Too long may leave a negative mood visible for several seconds after worker crash. Recommend 3000 ms as default, tunable in config.
3. **SURPRISED startle reflex timing**: The 3.0 s / 0.8 cap values were chosen when SURPRISED was classified as Negative. Now that it's Neutral, are these still appropriate? Keeping them for now — high arousal shouldn't persist regardless of valence. Revisit if T3/T4 testing shows SURPRISED feels artificially cut short.
