# Face Communication Spec — Stage 1: Research & Design Approach Proposal

## Context

The robot face must communicate **intention and awareness** so its actions feel natural and real rather than random for children ages 4–6. The face currently has a rich vocabulary (12 moods, 13 gestures) and a conversation state prototype (sim-only), but no unified design language governing *when*, *why*, and *how* expressions compose into legible behavior.

This document is **Stage 1 only** — it defines research grounding, design method, and key decision points. It proposes **design principles and option categories only**. It does not define numeric thresholds, exact mappings, durations, color values, or choreography details. Those belong in Stage 2.

---

## A) Verified System Snapshot

Only constraints that affect **interaction semantics or timing** are included here.

### Semantic Constraints
- **Display**: 320×240 px, 30 FPS render loop — small screen, limited spatial resolution for expression detail
- **Visual channels available**: eyes (shape, gaze, eyelids), mouth (curve, openness, width), face color (per-mood hue), screen border (4 px frame + glow), single RGB LED, backlight brightness
- **Touch input**: capacitive, supports press/release/drag + two soft buttons (PTT, ACTION)
- **Command surfaces**: 5 commands from supervisor → face MCU (SET_STATE, GESTURE, SET_SYSTEM, SET_TALKING, SET_FLAGS). Planned 6th: SET_CONV_STATE (0x25, not yet implemented)
- **Telemetry back**: face status at 20 Hz, button/touch events on change, heartbeat at 1 Hz

### Timing Constraints
- **Supervisor tick**: 50 Hz (20 ms) — face commands emitted per-tick on change
- **MCU render**: 30 FPS (33 ms frame budget)
- **Talking update**: energy at ~20 Hz from TTS worker, MCU timeout at 450 ms if no update
- **Blink cadence (MCU)**: 2.0–5.0 s between blinks
- **Idle gaze wander (MCU)**: new target every 1.5–4.0 s
- **Gaze dynamics**: spring model (not instant snap), settles over ~200–300 ms
- **Easing**: exponential tween for most parameters; spring physics for gaze

### Existing Priority Layers (top wins)
```
System overlay (BOOTING / ERROR / LOW_BATTERY / UPDATING / SHUTTING_DOWN)
  → Talking (TTS energy, lip sync)
    → Conversation emotion/gesture (AI worker)
      → Planner emote/gesture (behavior engine)
        → Idle (neutral, auto-blink, gaze wander)
```

### Existing Conversation Flow
Wake word OR PTT → start session → start listening → audio capture → VAD end-of-utterance → AI processing → TTS playback → session done.

**Current visual gap**: No face-level signaling for LISTENING, THINKING, or transition states. Only TTS talking animation and AI-chosen emotions during the SPEAKING phase. The conversation border prototype exists in sim only (`conv_border.py`) with 8 states (IDLE, ATTENTION, LISTENING, PTT, THINKING, SPEAKING, ERROR, DONE) — not yet ported to firmware.

### Verified Divergences vs Baseline Inventory

| Claim in Baseline | Actual (Verified) | Status |
|-------------------|-------------------|--------|
| X_EYES: 2.5 s (sim) vs 1.5 s (MCU) | MCU uses 2.5 s — `face_state.cpp:819` | **Baseline WRONG** — both 2.5 s |
| Neutral mouth_curve: 0.2 (sim) vs 0.1 (MCU) | Both set NEUTRAL target to 0.1 — `face_state_v2.py:247`, `face_state.cpp:259` | **Baseline MISLEADING** — both converge to 0.1 |
| THINKING color: sim falls through to NEUTRAL | Confirmed — sim has no case, MCU has explicit mapping | **Baseline CORRECT** |
| Blink interval: sim 3–7 s, MCU 2–5 s | Confirmed | **Baseline CORRECT** |
| Idle gaze: sim 1–3 s, MCU 1.5–4 s | Confirmed | **Baseline CORRECT** |
| Talking phase speed: sim variable, MCU fixed | Confirmed | **Baseline CORRECT** |
| Background color: sim (10,10,14), MCU (0,0,0) | Confirmed | **Baseline CORRECT** |
| SET_FLAGS undocumented in protocols.md | Confirmed | **Baseline CORRECT** |
| LOW_BATTERY: no supervisor trigger | Confirmed — protocol exists, no code sends it | **Baseline CORRECT** |

### Unverified Assumptions

These could not be confirmed from code and are treated as provisional:

1. **Pupil color on MCU** — sim uses (10,15,30) but MCU value was not located in audit. Assumed hardcoded in render path.
2. **Touch calibration preset in production** — default index 3 per config; actual unit may differ.
3. **Effective LED visibility** — physical placement and diffuser optics determine real-world visibility at angles. No measurements available.
4. **Audio latency** — wake word detection latency (inference + frame buffering) is unverified; only the 80 ms frame size is confirmed.
5. **Display viewing angle** — ILI9341 TN panel; color shift at steep angles assumed but not characterized.

---

## B) Research Plan

### Rigor Constraints

- All sources cited in APA-style inline (Author, Year).
- For each citation: 1–2 sentences explaining how it **constrains** a design decision.
- Each claim labeled: **[Empirical]** (published experimental result), **[Theory]** (widely accepted framework), or **[Inference]** (speculative extrapolation — must be validated in testing).
- At least one source per bucket published within the last 10 years.

### Bucket 1: Developmental Psychology (Ages 4–6)

**Design questions**: Which emotions can 4–6 year olds reliably identify on a non-human face? What display features drive recognition vs confusion? How do children this age attribute mental states to robots?

**Keystone sources**:
1. **Widen & Russell (2003)** — "A closer look at preschoolers' freely produced labels for facial expressions." **[Empirical]** Preschoolers reliably label happy, sad, angry, scared but confuse surprise/disgust/contempt. *Constrains*: the "safe" emotion set for autonomous display, and which moods need extra disambiguation.
2. **Denham (1986)** — "Social cognition, prosocial behavior, and emotion in preschoolers." **[Empirical]** Children use context + face together; face alone is insufficient for nuanced recognition. *Constrains*: expressions must be paired with behavioral context to be legible.
3. **Wellman, Cross & Watson (2001)** — Meta-analysis of false-belief understanding. **[Empirical]** Theory of mind emerges ~4–5 but is fragile. *Constrains*: ambiguous expressions risk over-attribution; face language must be unambiguous.
4. **Kahn et al. (2012)** — "Robovie, you'll have to go into the closet now." **[Empirical]** Children attribute social/moral standing to robots. *Constrains*: guardrails for negative affect — children may take the robot's distress seriously.
5. **Di Dio et al. (2020)** — "Children's recognition of emotions from robot faces." **[Empirical, recent]** Tests emotion recognition on stylized robot faces with children 4–8. *Constrains*: which geometric simplifications preserve legibility.

### Bucket 2: HRI / Social Robotics (Gaze, Turn-Taking, Trust)

**Design questions**: How should gaze signal attention vs disengagement? What timing for turn-taking cues? What sustains vs erodes trust?

**Keystone sources**:
1. **Admoni & Scassellati (2017)** — "Social eye gaze in human-robot interaction: A review." **[Theory/Empirical review]** *Constrains*: functional roles gaze must serve (attention signaling, turn-taking, referencing).
2. **Skantze, Hjalmarsson & Oertel (2014)** — "Turn-taking cues in a multiparty human-robot dialogue system." **[Empirical]** *Constrains*: latency bounds for conversational state transitions.
3. **Kanda, Hirano, Eaton & Ishiguro (2004)** — "Interactive robots as social partners and peer tutors for children." **[Empirical]** *Constrains*: consistency and predictability build trust over days/weeks.
4. **Leite, Martinho & Paiva (2013)** — "Social robots for long-term interaction: A survey." **[Theory/Empirical review]** *Constrains*: which patterns sustain engagement vs habituate or annoy.

### Bucket 3: Affective Computing Models

**Design questions**: Discrete emotions or dimensional model? How does the 12-mood set map onto child perception? How should intensity scale?

**Keystone sources**:
1. **Russell (1980)** — "A circumplex model of affect." **[Theory]** *Constrains*: whether blending should use a 2D space or remain discrete.
2. **Breazeal (2003)** — "Emotion and sociable humanoid robots." **[Theory/Empirical]** *Constrains*: approaches for composing emotion from low-dimensional parameters vs lookup tables.
3. **Löffler, Schmidt & Magerkurth (2018)** — "Multimodal emotion expression of a social robot." **[Empirical, recent]** *Constrains*: when face alone is sufficient vs when reinforcement is needed.
4. **Cauchard, Zhai, Spadafora & Landay (2016)** — "Emotion encoding in human–drone interaction." **[Empirical]** *Constrains*: design potential of LED and border as affective channels.

### Bucket 4: Animation & Timing Principles

**Design questions**: What transition timing is legible at 320×240? How do ease curves affect readability? What makes movement feel alive vs mechanical?

**Keystone sources**:
1. **Thomas & Johnston (1981)** — *The Illusion of Life: Disney Animation*. **[Theory]** *Constrains*: anticipation, follow-through, ease requirements.
2. **Takayama, Dooley & Merritt (2011)** — "Expressing thought: Improving robot readability with animation principles." **[Empirical]** *Constrains*: evidence for anticipation frames improving recognition.
3. **Ribeiro & Paiva (2012)** — "The illusion of robotic life." **[Theory/Empirical]** *Constrains*: practical timing ranges for transition legibility.
4. **Schulz, Kratzer & Loffler (2019)** — "Let's talk about robot animation." **[Empirical, recent]** *Constrains*: which principles matter most at small scale and low resolution.

### Bucket 5: Conversation State Signaling

**Design questions**: How should listening/thinking/speaking be distinguished visually? Face-intrinsic or peripheral? What latency feels natural?

**Keystone sources**:
1. **Clark (1996)** — *Using Language*. **[Theory]** *Constrains*: what visual cues map to each conversational grounding act.
2. **Andrist, Mutlu & Gleicher (2014)** — "Conversational gaze aversion for humanlike robots." **[Empirical]** *Constrains*: gaze direction policy during processing/thinking states.
3. **Meena, Skantze & Gustafson (2014)** — "Data-driven models for timing feedback responses." **[Empirical]** *Constrains*: acceptable latency between user speech end and robot visual response.

---

## C) Design Method

### Steps

1. **Operationalize "Randomness" and "Awareness"** — Define both in measurable terms. Identify current failure modes. (§C.1)
2. **Define the Robot's Relational Role** — What is the robot to the child? (§C.2)
3. **Define Personality Axes** — Formal dimensions that constrain all design decisions. (§C.3)
4. **Define Intent Taxonomy** — Everything the face must communicate, grouped as *tonic* (sustained) vs *phasic* (transient).
5. **Define Channel Allocation Policy** — Which visual channels are owned by which priority layers. (§C.4)
6. **Define Visual Grammar** — For each intent, which allocated channels carry it; composition rules for concurrent intents.
7. **Map to Protocol Surfaces** — For each visual grammar element, which command controls it. Identify gaps.
8. **Define Timing Principles** — Categories of transitions and the philosophy for each.
9. **Define Guardrails** — Child safety, negative affect limits, startle prevention, fallbacks, color accessibility.
10. **Define Evaluation Framework** — Test types, metric categories, pass/fail philosophy. (§C.5)

### C.1 — Operationalizing "Randomness" and "Awareness" [S1-C1]

#### What "Random" Looks Like (Failure Modes)

**[Inference]** Based on code analysis, the current system has these randomness failure modes:

1. **Uncorrelated gaze shifts during conversation** — When the robot is in LISTENING state, MCU idle gaze wander continues (supervisor doesn't override). The eyes drift randomly while the child is speaking, breaking the impression of attention.

2. **Unexplained emotion transitions** — When AI worker emits `AI_CONVERSATION_EMOTION`, the face snaps to a new mood with no anticipation or contextual bridge. From the child's perspective, the face changes for no visible reason if the audio context isn't clear.

3. **No visual signal for state transitions** — Between "I finished speaking" and "robot starts talking," there is no visual THINKING indicator. The face sits in whatever mood it was last sent, appearing frozen or indifferent during the ~1–3 s processing delay.

4. **Talking stops before speech ends** — Known bug (`docs/TODO.md:12`). Face reverts to neutral while audio still plays, breaking lip sync illusion.

5. **Conversation starts with no visual acknowledgment** — After wake word detection, there is no immediate face change signaling "I heard you." The chime plays but the face remains neutral.

#### What "Awareness" Looks Like (Behavioral Indicators)

**[Inference]** "Awareness" should be operationally defined as the conjunction of:

| Indicator | Observable Behavior | Measurable Proxy |
|-----------|-------------------|------------------|
| **Temporal correlation** | Face changes are synchronized with external events (speech, wake word, button press) | Latency from trigger → visual change (ms) |
| **Gaze coherence** | Eyes point at relevant target (user during listening, away during thinking) | Gaze variance during each conversation state (low = coherent) |
| **Predictive cueing** | Face signals *before* an action (anticipation before speaking, blink before mood change) | Presence of anticipation frame before transitions (binary) |
| **State continuity** | Expression holds long enough to be read, transitions are smooth not jarring | Minimum hold time before transition; absence of single-frame expression flickers |
| **Acknowledgment** | Face visibly responds to user input within a perceptible window | Time from user action → first visible face change (must be < perceptual threshold) |

A face that satisfies all five reads as "aware." A face that fails on any one reads as "random" or "broken" for that moment. The spec must ensure each indicator is maintained across all operating modes.

### C.2 — The Robot's Relational Role [S1-C2]

> **DECIDED: Caretaker/guide with playful elements.** Predominantly calm and reassuring, but with warmth and occasional playfulness. Robot's emotions should not destabilize the child.

The negative affect policy, personality calibration, and vulnerability display all depend on a prior question:

**What is this robot's emotional authority relative to the child?**

| Role | Implication for Face Design |
|------|---------------------------|
| **Peer / playmate** | Shows emotions freely, including vulnerability. Can be scared, confused, sad. Emotional range mirrors the child's. |
| **Caretaker / guide** | Predominantly calm and reassuring. Negative affect is rare and brief. Emotional authority is higher — the robot's emotions should not destabilize the child. |
| **Toy / tool** | Emotions are performative, not "real." The face is entertainment, not empathy. Negative affect is comedic, not distressing. |
| **Companion animal** | Shows simple emotions. Can be happy, curious, sleepy. Negative affect is limited to startled or confused — not angry or sad. |

This is a **framing decision** that precedes D2 (negative affect) and D4 (idle personality). It should be resolved first.

### C.3 — Personality Axes [S1-C3]

> **DECIDED: 5 axes confirmed as defined.** Stage 2 will specify exact positions on each axis.

The personality references (Sony Astro, Wall-E, EVE) imply positions on formal dimensions. Stage 2 will specify exact positions; Stage 1 defines the axes:

| Axis | Low End | High End | Design Impact |
|------|---------|----------|---------------|
| **Energy Level** | Calm, slow, ambient | Bouncy, fast, reactive | Idle amplitude, transition speeds, gesture frequency |
| **Emotional Reactivity** | Reserved, mild, slow onset | Expressive, full-range, fast onset | Intensity range, ramp rates, mirror strength |
| **Social Initiative** | Passive, waits, responds only | Proactive, seeks attention, initiates | Idle gaze behavior, attention-seeking vs ambient |
| **Vulnerability Display** | Guarded, neutral baseline | Open, shows confusion/sadness/fear | Negative affect policy, uncertainty display |
| **Predictability** | Highly consistent (same in → same out) | Variable (expressive variety, timing jitter) | Addressed in D10 as a standalone decision |

### C.4 — Channel Allocation Policy (Principles Only) [S1-C4]

The face has 6 visual channels: eyes, mouth, face color, border, LED, backlight. The question is which priority layers **own** which channels.

Three candidate policies to evaluate in Stage 2:

**Policy A — Layer-Exclusive Channels**: Each layer owns dedicated channels. No sharing, no collisions.

**Policy B — Shared Channels with Priority Override**: All layers can write to all channels, higher-priority layers mask lower ones. (Current approach for mood/system, extended.)

**Policy C — Hybrid**: Some channels reserved (border = conversation only), others shared with priority (eyes/mouth = emotion with conversation override for gaze).

Each has different tradeoffs. Stage 2 evaluates these against research.

### C.5 — Evaluation Framework (Philosophy, Not Thresholds) [S1-C5]

**Types of tests** the spec must support:

| Test Type | What It Measures | When to Run |
|-----------|------------------|-------------|
| **Emotion recognition** | Can children identify the displayed mood? | After visual grammar defined, before firmware port |
| **Conversation state legibility** | Can children distinguish listening/thinking/speaking? | After conversation signaling implemented |
| **Transition naturalness** | Do expression changes feel intentional or glitchy? | During timing rule tuning |
| **Comfort/safety** | Does the child feel safe? Parent feels appropriate? | End-to-end with real interactions |
| **Latency** | Is the face responsive enough to feel immediate? | Instrumented at each pipeline stage |
| **Consistency** | Does same input → recognizably similar output? | Automated regression over logged sessions |
| **Over-interpretation** | Does the child attribute intent the robot doesn't have? | Observation + prompted interview ("What is the robot looking at?" "Why did it do that?") |

The **over-interpretation** test is critical. It directly measures whether "awareness" cues are calibrated — too strong and the child expects follow-through the robot can't deliver (e.g., "it's looking at my toy"); too weak and the robot appears random. This test guards against the failure mode where the design solves randomness but creates false expectations.

**Metric categories** (exact thresholds deferred to Stage 2):
- Recognition rate (% correct identification)
- Subjective comfort (parent/child rating scale)
- Response latency (ms from trigger → visual change)
- Hold time (minimum ms an expression is displayed)
- Startle incidents (count of distress reports)
- Over-interpretation rate (% of prompted responses attributing unintended meaning)

**Evidence classification** for all design claims:
- **[Empirical]**: Backed by published experimental results
- **[Theory]**: Backed by widely accepted framework
- **[Inference]**: Speculative extrapolation — must be validated in testing

---

## D) Decision Points Requiring User Input

### Decision Criticality Classification

Each decision is classified by cost-to-change-later:

| Class | Meaning | Examples |
|-------|---------|---------|
| **Architectural** | Changes protocol, data model, or control flow. Hard to reverse after firmware ships. | D8, D9 |
| **Structural** | Changes which code modules do what. Medium effort to revise. | D1, D3, D6 |
| **Behavioral** | Changes expression behavior within existing architecture. Moderate effort. | D2, D7, D10 |
| **Tuning** | Changes parameter values. Cheap to iterate. | D4, D5 |

Decisions are presented in priority order: architectural first, then structural, behavioral, tuning.

### Comparison Dimensions

Each option is evaluated on four axes:
- **Eng. complexity**: Implementation and ongoing maintenance burden
- **Child cognitive load**: How much the child must learn or parse
- **Failure mode risk**: What goes wrong and how badly
- **Extensibility**: How well it accommodates future features

---

### D8. Affect Model Class — ARCHITECTURAL [S1-D8]

> **DECIDED: Option C — Discrete with intensity blending.** Keep 12 named moods; use existing `intensity` parameter for ramp-down → switch → ramp-up transitions. Supervisor manages transition timing. No protocol changes.

This decision cascades into protocol evolution, supervisor ownership model, and whether personality axes can be expressed continuously. It determines whether the face MCU or the supervisor owns expression blending, and whether emotional transitions are controllable in time.

**Option A — Discrete emotions (current)**

Keep the 12 named moods as atomic states. Supervisor selects by name.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no changes to firmware or protocol |
| Child cognitive load | Low — each expression is a recognizable "face" |
| Failure mode risk | Abrupt transitions may read as random; over-specified set (12) may confuse if subtle moods are poorly differentiated |
| Extensibility | Adding moods requires firmware enum changes; no blending capability for future personality tuning |

**Option B — Dimensional model (valence/arousal)**

Replace or supplement mood selection with a 2D coordinate. Supervisor sends (valence, arousal) instead of mood_id. MCU interpolates between expression anchors.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — new protocol field, new firmware interpolation engine, supervisor refactor |
| Child cognitive load | Lowest for the child (smoother = more natural), but harder for the planner/AI to reason about |
| Failure mode risk | Interpolation between moods could produce ambiguous intermediate faces; debugging is harder |
| Extensibility | Highest — personality axes map directly to V/A bias; new "moods" are just new anchor points |

**Option C — Discrete with intensity blending (minimal extension)**

Keep discrete moods but use existing `intensity` parameter for ramp-down → switch → ramp-up transitions. Supervisor manages transition timing.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — no protocol change; supervisor adds transition sequencing in tick_loop |
| Child cognitive load | Low — still discrete recognizable faces, but transitions feel smoother |
| Failure mode risk | Transition timing is now a supervisor responsibility — bugs produce "melting face" if ramp-down/switch/ramp-up desync |
| Extensibility | Moderate — intensity ramp is a coarse tool; doesn't enable true blending |

**Open questions**: Does Breazeal (2003) provide implementation guidance for dimensional models on constrained hardware? Is 12 moods the right granularity given Widen & Russell (2003)?

---

### D9. Sim/MCU Divergence Resolution — ARCHITECTURAL [S1-D9]

> **DECIDED: Option C — Audit each divergence, then establish sim as design authoring surface with CI-enforced parity.**

This is not a tooling decision. It determines:
- Whether hardware tuning has design authority
- Whether simulation is the design reference
- Whether future research testing and iteration happens primarily in sim or on hardware
- The iteration speed for Stage 2 evaluation (sim tests are fast; hardware tests are slow)

**Option A — MCU is canonical**

All sim values updated to match MCU.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — one-directional sync |
| Child cognitive load | N/A (internal) |
| Failure mode risk | May discard intentional sim-side design explorations; sim becomes purely derivative |
| Extensibility | Future design work must happen on hardware first; sim follows |

**Option B — Sim is the design reference**

MCU values updated to match sim. Sim represents intended design; MCU drifted.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — one-directional sync |
| Child cognitive load | N/A (internal) |
| Failure mode risk | MCU values may have been improved through real-world testing; reverting loses those gains |
| Extensibility | Enables rapid design iteration in sim before hardware deploy |

**Option C — Audit each divergence, then establish single source going forward**

Evaluate each difference. Pick the best value. Establish a policy: sim is the design authoring surface, MCU must match within a defined tolerance, divergence is a CI-detectable error.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — one-time audit + ongoing enforcement (could be automated) |
| Child cognitive load | N/A (internal) |
| Failure mode risk | Lowest long-term — prevents future silent drift |
| Extensibility | Best — sim becomes the safe iteration surface with guaranteed hardware fidelity |

**Open questions**: Is there documentation of *why* MCU values diverged? Were they intentional hardware tuning or accidental drift?

---

### D1. Color Semantics: How Do Color Channels Layer? — STRUCTURAL [S1-D1]

> **DECIDED: Option A — Separated channels.** Face color = emotion. Border color = conversation state. LED = conversation state. Each channel carries one type of information.

**Option A — Separated channels**

Face color = emotion. Border color = conversation state. LED = conversation state.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — requires clear ownership boundaries in code; border and face are independent |
| Child cognitive load | Moderate — child must parse two independent color vocabularies (face vs periphery) |
| Failure mode risk | If child conflates the two, color cues cancel out; separation only works if channels are visually distinct |
| Extensibility | Clean — adding new conversation states or emotions doesn't affect the other channel |

**Option B — Unified color**

All channels share one color from highest-priority active state.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — single color decision point |
| Child cognitive load | Lowest — one color = one meaning at any moment |
| Failure mode risk | Loses emotional nuance during conversation; emotion layer is invisible when conversation is active |
| Extensibility | Rigid — adding layers means more priority conflicts |

**Option C — Emotion-tinted conversation**

Border/LED = conversation state color tinted by emotion. Face = emotion only.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — requires color blending logic, tinting calculations |
| Child cognitive load | Highest — subtle tinting may not be perceptible at 320×240 for young children |
| Failure mode risk | Tinting may produce muddy or ambiguous colors; hard to tune |
| Extensibility | Rich — new states/emotions compose naturally |

**Open questions**: How much simultaneous color information can 4–6 year olds process? Does multimodal redundancy research (Löffler et al., 2018) favor separation or unification?

---

### D3. Conversation State Signaling: Which Channels Carry It? — STRUCTURAL [S1-D3]

> **DECIDED: Option C — Multimodal.** Coordinated border + LED + gaze behavior + mood hints per conversation state. Requires firmware border port AND supervisor gaze control.

**Option A — Peripheral only (border + LED)**

Face expressions remain under emotion layer. Gaze under MCU idle wander.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — port border from sim to firmware; no supervisor gaze logic |
| Child cognitive load | Moderate — child must notice the border (peripheral vision) to know conversation state |
| Failure mode risk | Border may be too subtle at 320×240; child's attention is on the face, not the frame edge. Misses gaze as an attention signal. |
| Extensibility | Easy to add states (just add border colors) |

**Option B — Face-intrinsic only (gaze + mood + blink patterns)**

No border system. Conversation state drives eye and mood behavior.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — supervisor gaze control, mood overrides per conversation phase; but border prototype is abandoned/deferred |
| Child cognitive load | Lowest — child reads the face naturally; no peripheral channel to learn |
| Failure mode risk | Conversation state and emotion compete for the same channels (eyes, mood). Collisions when AI sends an emotion during LISTENING. |
| Extensibility | Adding states requires new face behaviors; harder to add states without crowding the expression space |

**Option C — Multimodal (all channels)**

Coordinated border + LED + gaze + mood per state.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — firmware border port + supervisor gaze control + coordination logic |
| Child cognitive load | Lowest at recognition time (redundant cues reinforce); highest to learn initially (more channels to notice) |
| Failure mode risk | Coordination bugs produce incoherent states (border says LISTENING, eyes say THINKING). More moving parts. |
| Extensibility | Most flexible — new states can use different channel combinations |

**Open questions**: Does multimodal redundancy research (Löffler et al., 2018; Cauchard et al., 2016) favor one approach for this age group? What is the engineering cost delta between options A and C?

---

### D6. Gaze Ownership During Conversation — STRUCTURAL [S1-D6]

> **DECIDED: Option C — Hybrid.** Supervisor controls gaze during LISTENING (center lock). MCU handles other states via mood. Incrementally extensible.

**Option A — Supervisor takes full gaze control**

During active conversation, supervisor sends explicit gaze coordinates, disables MCU idle wander via SET_FLAGS.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — new state in tick_loop, flag management, gaze target per conversation phase |
| Child cognitive load | Lowest — gaze is maximally intentional |
| Failure mode risk | Supervisor must release gaze control correctly on session end; bugs produce stuck gaze |
| Extensibility | Easy to add gaze behaviors per new conversation state |

**Option B — MCU handles gaze via mood**

Conversation states set moods with built-in gaze targets. No explicit gaze override.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no new supervisor logic; moods already have gaze behavior |
| Child cognitive load | Moderate — gaze during LISTENING depends on which mood is set; "attentive neutral" doesn't exist as a mood |
| Failure mode risk | Mood palette too coarse — no way to say "look at user" without setting a mood that also changes eyes/mouth |
| Extensibility | Limited by the mood set; adding gaze-only behaviors requires a new mood or a protocol extension |

**Option C — Hybrid**

Supervisor controls gaze only for highest-value state (LISTENING = center lock). MCU handles the rest via mood.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — one conditional gaze override in tick_loop |
| Child cognitive load | Moderate — attention signal is clear during listening; other states are less controlled |
| Failure mode risk | Inconsistency — intentional gaze during LISTENING, random during other states. May be jarring. |
| Extensibility | Easy to add more overrides incrementally |

**Open questions**: Does Admoni & Scassellati (2017) identify specific gaze behaviors per conversational phase? Is the spring model fast enough for intentional-looking gaze snaps?

---

### D2. Negative Affect Policy — BEHAVIORAL [S1-D2]

> **DECIDED: Option B — Full palette with guardrails.** All 12 moods available, but negative moods get mandatory anticipation frames, duration limits, and auto-recovery to neutral. Tunable per-mood.

**Prerequisite**: This decision depends on the robot's relational role (§C.2). The correct policy differs significantly between "peer" and "caretaker."

**Option A — Restricted palette**

Autonomous face limited to positive + neutral (happy, curious, excited, neutral, thinking, sleepy). Negative moods only via explicit AI commands with guardrails.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — allowlist in tick_loop |
| Child cognitive load | Lowest — fewer states to parse |
| Failure mode risk | Robot may feel emotionally flat or inauthentic during conversations about sad/scary topics |
| Extensibility | Easy to relax later by expanding the allowlist |

**Option B — Full palette with guardrails**

All 12 moods available, but negative moods get mandatory anticipation, duration limits, auto-recovery to neutral.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — guardrail logic in tick_loop or face_client |
| Child cognitive load | Higher — more emotional states to interpret |
| Failure mode risk | Guardrails must be tuned per-mood; too aggressive = clipped expressions, too loose = distress |
| Extensibility | Guardrail params are tunable; policy can be adjusted per-child via config |

**Option C — Context-gated**

Negative moods only during active conversation. Outside conversation, positive + neutral only.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — context check in tick_loop |
| Child cognitive load | Moderate — negative moods have conversational context, which aids recognition (Denham, 1986) |
| Failure mode risk | Edge cases: what if conversation ends abruptly while showing anger? Need recovery logic. |
| Extensibility | Context boundary is clear; easy to add other context types later |

**Open questions**: What is the robot's relational role (§C.2)? Does Kahn et al. (2012) show harm from robot negative affect in this age group?

---

### D7. Transition Timing Philosophy — BEHAVIORAL [S1-D7]

> **DECIDED: Option B — Choreographed major transitions.** Major changes (mood switch, conversation phase change) include anticipation micro-gesture. Minor changes (intensity, gaze) use current tween.

**Option A — Always tween (current)**

All changes use exponential interpolation. No anticipation frames.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — already implemented |
| Child cognitive load | Moderate — smooth but unexplained; changes may still feel random |
| Failure mode risk | Fails on "awareness" indicator #3 (predictive cueing) — no "tells" before changes |
| Extensibility | Easy to maintain; hard to add intentionality later without refactoring |

**Option B — Choreographed major transitions**

Major changes (mood switch, conversation phase) include anticipation micro-gesture. Minor changes (intensity, gaze) use current tween.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — transition sequencer in supervisor or MCU, defines "major" vs "minor" |
| Child cognitive load | Lowest — changes feel intentional; the "tell" provides a perceptual anchor |
| Failure mode risk | Adds latency to major transitions; must fit within conversation timing budget |
| Extensibility | New transitions just need new choreography sequences |

**Option C — Fully choreographed**

Every change follows anticipation → change → settle → follow-through.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — full transition engine, per-parameter choreography |
| Child cognitive load | Lowest per-transition, but may feel sluggish in fast dialogue |
| Failure mode risk | Latency may exceed conversation timing budget; face feels "laggy" |
| Extensibility | Maximum expressiveness; also maximum maintenance surface |

**Open questions**: Does Takayama et al. (2011) quantify recognition improvement from anticipation? What's the latency budget for adding anticipation within conversation flow?

---

### D10. Determinism vs Expressive Variability — BEHAVIORAL [S1-D10]

> **DECIDED: Option B — Bounded stochastic variation.** Semantic signals are deterministic (same conversation phase → same face behavior). Variation limited to cosmetic parameters (blink jitter, saccade, breathing phase, sparkle).

For 4–6 year olds, too much variability = perceived randomness; too little = perceived lifelessness. This is the core tension underlying the "awareness" goal and deserves explicit treatment beyond the personality axis.

**Option A — Fully deterministic**

Same input → same output, always. No timing jitter, no gesture variation, no intensity randomization. Every conversation start looks identical.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — remove all random() calls from face logic |
| Child cognitive load | Lowest — maximally predictable, child learns exact patterns |
| Failure mode risk | Robot feels robotic and lifeless. Habituation is fast — child loses interest. |
| Extensibility | Adding variety later requires reintroducing randomness infrastructure |

**Option B — Bounded stochastic variation**

Core behavior is deterministic (same conversation phase → same face behavior). Variation is limited to parameters that don't carry semantic meaning: blink timing jitter, saccade micromotion, breathing phase, sparkle position.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — current MCU already implements this for blink/saccade/breathing |
| Child cognitive load | Low — semantic signals are predictable; variation is subliminal "aliveness" |
| Failure mode risk | Must clearly define which parameters are "semantic" (no jitter) vs "cosmetic" (jitter OK). Misclassification = perceived randomness. |
| Extensibility | Easy to tune the boundary between semantic and cosmetic |

**Option C — Expressive variation**

Allow meaningful variation: same mood trigger could produce different gesture responses, different gaze patterns, variable intensity. Robot has "moods within moods."

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Moderate — variation logic, seed management, ensuring variation stays legible |
| Child cognitive load | Highest — child must generalize across varied expressions of the same intent |
| Failure mode risk | Directly conflicts with "awareness" goal — variation may read as randomness if not anchored to context |
| Extensibility | Richest — enables personality emergence over time |

**Open questions**: Where is the line between "alive" and "random" for this age group? Does Kanda et al. (2004) measure the effect of behavioral consistency on trust formation?

---

### D4. Idle Personality: How Alive at Rest? — TUNING [S1-D4]

> **DECIDED: Option B — Moderate liveliness (current MCU behavior).** Breathing + auto-blink + idle gaze wander + saccade jitter + sparkle. No autonomous mood or gesture changes.

**Option A — Minimal life signs**

Breathing + auto-blink only. No gaze wander, sparkle, or variation.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — disable idle wander via flags |
| Child cognitive load | Lowest — nothing to interpret |
| Failure mode risk | Robot feels "dead" or "off" even when connected |
| Extensibility | Easy to add features later |

**Option B — Moderate liveliness (current MCU behavior)**

Breathing + auto-blink + idle gaze wander + saccade jitter + sparkle. No autonomous mood or gesture changes.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — already implemented |
| Child cognitive load | Low — but random gaze wander may be over-interpreted ("it's looking at something") |
| Failure mode risk | Gaze wander triggers over-interpretation (see §C.5 over-interpretation metric) |
| Extensibility | Already has the infrastructure for variation |

**Option C — Socially responsive idle**

All of B, plus periodic glances toward detected user and micro-expressions.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — requires face tracking or proximity sensor input |
| Child cognitive load | Moderate — implies attention the robot may not sustain |
| Failure mode risk | Highest over-interpretation risk. Creates expectations the conversation system must meet. |
| Extensibility | Richest — but requires sensor infrastructure |

**Open questions**: Is face tracking available as a future input? Should the idle spec account for it? What does "Social Initiative" axis dictate?

---

### D5. LED Role — TUNING [S1-D5]

> **DECIDED: Option A — Mirror conversation state.** LED tracks border/conversation state color at reduced brightness. System modes override.

**Option A — Mirror conversation state**

LED tracks border/conversation state color at reduced brightness.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — read conv state, set LED color |
| Child cognitive load | Low — reinforces border if visible; angle-independent if not |
| Failure mode risk | Minimal — LED is supplementary |
| Extensibility | Scales with conversation states |

**Option B — Mirror face emotion**

LED tracks face emotion color.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — already partially implemented |
| Child cognitive load | Lowest — redundant with face |
| Failure mode risk | Minimal — purely reinforcing |
| Extensibility | Scales with mood set |

**Option C — Independent status**

LED = system status only (connected, error, low battery).

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — fixed mapping |
| Child cognitive load | Lowest — parent-facing information |
| Failure mode risk | Underutilized during normal operation |
| Extensibility | Limited |

**Open questions**: Physical LED placement relative to screen? Visible when screen is visible, or only from other angles?

---

## E) Approved Decisions

All items confirmed 2026-02-21.

### Framing
- [x] **Robot's relational role** (§C.2) — **Caretaker/guide with playful elements.** Predominantly calm and reassuring, but with warmth and occasional playfulness. Robot's emotions should not destabilize the child.
- [x] **Personality axis definitions** (§C.3) — **5 axes confirmed as defined.**

### Architectural decisions
- [x] **Affect model class** (D8) — **C: Discrete with intensity blending.** Keep 12 named moods; use existing `intensity` parameter for ramp-down → switch → ramp-up transitions. Supervisor manages transition timing. No protocol changes.
- [x] **Sim/MCU authority & research workflow** (D9) — **C: Audit each divergence, then establish sim as design authoring surface with CI-enforced parity.** One-time audit of all divergences, pick best value per case, then sim is canonical going forward.

### Structural decisions
- [x] **Channel separation philosophy** (D1) — **A: Separated channels.** Face color = emotion. Border color = conversation state. LED = conversation state. Each channel carries one type of information.
- [x] **Conversation signaling strategy** (D3) — **C: Multimodal.** Coordinated border + LED + gaze behavior + mood hints per conversation state. Requires firmware border port AND supervisor gaze control.
- [x] **Gaze ownership** (D6) — **C: Hybrid.** Supervisor controls gaze during LISTENING (center lock). MCU handles other states via mood. Incrementally extensible.

### Behavioral decisions
- [x] **Negative affect policy** (D2) — **B: Full palette with guardrails.** All 12 moods available, but negative moods get mandatory anticipation frames, duration limits, and auto-recovery to neutral. Tunable per-mood.
- [x] **Transition timing** (D7) — **B: Choreographed major transitions.** Major changes (mood switch, conversation phase change) include anticipation micro-gesture. Minor changes (intensity, gaze) use current tween.
- [x] **Determinism vs variability** (D10) — **B: Bounded stochastic variation.** Semantic signals are deterministic (same conversation phase → same face behavior). Variation limited to cosmetic parameters (blink jitter, saccade, breathing phase, sparkle).

### Tuning decisions
- [x] **Idle personality** (D4) — **B: Moderate liveliness (current MCU behavior).** Breathing + auto-blink + idle gaze wander + saccade jitter + sparkle. No autonomous mood or gesture changes.
- [x] **LED role** (D5) — **A: Mirror conversation state.** LED tracks border/conversation state color at reduced brightness. System modes override.

### Validation
- [x] **Research direction** (§B) — **Confirmed.** 5 buckets and ~20 keystone sources approved.
- [x] **Failure modes** (§C.1) — **Confirmed.** 5 randomness failures + 5 awareness indicators accepted as accurate.
- [x] **Evaluation framework** (§C.5) — **Confirmed.** 7 test types and 6 metric categories approved, including over-interpretation.

---

Stage 1 complete. Proceed to Stage 2.
