# Face Communication Spec — Stage 2: Full Specification

**Prerequisite**: Stage 1 (Research & Design Approach Proposal) — all decisions approved 2026-02-21.

**Scope**: This document defines the complete visual language for the robot face — every expression, transition, timing rule, and protocol mapping needed to implement "intention and awareness" for children ages 4–6. All values are implementation-ready. All claims are evidence-tagged per Stage 1 rigor constraints.

**Companion documents**: Stage 2 Implementation Plan, Stage 2 Evaluation Plan (separate files).

---

## 1. Personality Profile

**Relational role**: Caretaker/guide with playful elements. Predominantly calm and reassuring. Emotional authority is higher than the child's — the robot's affect should not destabilize.

**Axis positions** (0.0 = low end, 1.0 = high end per [S1-C3] definitions):

| Axis | Position | Rationale |
|------|----------|-----------|
| **Energy Level** | 0.40 | Calm baseline with enough responsiveness to feel warm, not sluggish. Caretaker pacing — slightly slower than the child's energy. **[Inference]** |
| **Emotional Reactivity** | 0.50 | Moderate — expressive enough to validate the child's emotions, restrained enough not to mirror distress. **[Empirical]** Kahn et al. (2012) shows children attribute real feelings to robots. **[Inference]** We set reactivity at 0.50 to prevent over-attribution while remaining warm. Must be validated in T4 child evaluation. |
| **Social Initiative** | 0.30 | Mostly responsive. Initiates only through idle aliveness cues (breathing, gaze wander), not through autonomous mood changes or attention-seeking gestures. **[Empirical]** Leite et al. (2013) notes proactive behaviors sustain engagement but risk habituation. **[Inference]** We set initiative at 0.30 to stay responsive without risking habituation. |
| **Vulnerability Display** | 0.35 | Lightly guarded. Can show confusion (THINKING mood) and mild concern but avoids overt sadness, fear, or anger outside conversation context. Consistent with caretaker authority. **[Inference]** |
| **Predictability** | 0.75 | High consistency. Same conversation phase → same core face behavior. Variation limited to cosmetic parameters per D10:B. **[Empirical]** Kanda et al. (2004) shows consistency builds trust over repeated interactions. **[Inference]** We set predictability at 0.75, reserving 0.25 for cosmetic variation (blink, breathing, sparkle) that provides aliveness without semantic variability. |

**Design implications of this profile**:
- Transitions are smooth, never snappy (Energy 0.40)
- Emotional onset is gradual, not instant (Reactivity 0.50)
- Robot never autonomously changes mood outside conversation (Initiative 0.30)
- Negative emotions are always brief, contextualized, and recovered (Vulnerability 0.35)
- A child who interacts daily should develop reliable expectations (Predictability 0.75)

---

## 2. Intent Taxonomy

Everything the face must communicate, classified by temporal profile.

### 2.1 Tonic Intents (Sustained States)

Held for extended periods. The face "rests" in one of these.

| Intent | Description | Primary Channel | Duration |
|--------|-------------|----------------|----------|
| **Idle** | Robot is on, no conversation active | Eyes (neutral) + breathing + blink + gaze wander | Indefinite |
| **Conversation: Listening** | Child is speaking, robot is attending | Gaze (center lock) + border (teal breathing) + LED | Until VAD end-of-utterance |
| **Conversation: PTT** | Tap-to-talk active | Gaze (center lock) + border (amber steady) + LED | Until toggled off |
| **Conversation: Thinking** | Processing user input | Gaze (aversion) + border (blue-violet orbit) + LED | Until TTS starts (~1–3 s typical) |
| **Conversation: Speaking** | TTS playback active | Mouth (lip sync) + border (white-teal energy) + LED | Until TTS finishes |
| **Emotion** | AI/planner-set mood | Eyes + mouth + face color | Until next mood command or recovery |
| **System overlay** | BOOTING, ERROR, LOW_BATTERY, UPDATING, SHUTTING_DOWN | Face-based expression + status icon (§4.4) | Until condition clears |

### 2.3 Layer Interaction Rules

The conversation layer can temporarily **clamp** the emotion layer during specific phases. This resolves the tension between emotion as a tonic intent ("until next mood command") and conversation states that force specific moods.

| Conversation Phase | Emotion Layer Status | Behavior |
|-------------------|---------------------|----------|
| **LISTENING / PTT** | Suppressed | Face shows attentive neutral (NEUTRAL @ 0.3). The personality worker continues integrating AI emotion impulses into the affect vector, but the tick loop does not display the worker's projected mood during this phase. |
| **THINKING** | Suppressed | Face shows THINKING mood @ 0.5. The personality worker continues integrating impulses. |
| **SPEAKING** | **Active** | Tick loop reads the personality worker's current snapshot and displays its projected mood via mood switch choreography (§5.1.1). The snapshot already reflects all impulses integrated during LISTENING/THINKING — no explicit queue or replay step. |
| **ATTENTION** | Held | Current mood held unchanged. |
| **ERROR** | Held | Current mood held unchanged. |
| **DONE** | Released | Mood intensity ramps to 0.0 (return to neutral). The personality worker's affect vector decays naturally toward baseline. Emotion layer returns to idle control. |

**Rationale**: During LISTENING and THINKING, the child sees the robot "paying attention" and "processing" — these are social signals that should not be contaminated by premature emotion display. Emotions become visible during SPEAKING, when the audio context makes them legible (per Denham, 1986: children use context + face together).

**Suppress-then-read model**: The personality worker's affect integrator runs continuously during LISTENING/THINKING (PE spec §10). AI emotion impulses are integrated immediately — they are never buffered in a queue. The integrator provides natural smoothing: if the AI sends HAPPY during LISTENING and then SAD during THINKING, the affect vector ends up between them (weighted by decay and recency), producing emotionally coherent behavior. On SPEAKING entry, the tick loop reads the worker's current snapshot, which already reflects all integrated impulses.

### 2.2 Phasic Intents (Transient Events)

Brief events that overlay or punctuate tonic states.

| Intent | Description | Duration | Trigger |
|--------|-------------|----------|---------|
| **Acknowledgment** | "I heard you" response to wake word or PTT press | 400 ms | Wake word detection / PTT down |
| **Mood transition** | Choreographed switch between emotions | 350–550 ms | SET_STATE with new mood_id |
| **Conversation phase transition** | Visual bridge between conversation states | 200–500 ms | State machine edge |
| **Gesture** | One-shot expressive animation (blink, nod, laugh, etc.) | 180 ms – 3.0 s | GESTURE command |
| **Negative affect recovery** | Mandatory return to neutral/positive after negative mood | 300–500 ms | Guardrail timer expiry |
| **Error flash** | Brief visual error indicator | 800 ms | Conversation error event |

---

## 3. Channel Allocation Policy

**Policy**: Hybrid ([S1-C4], informed by [S1-D1]:A, [S1-D3]:C, [S1-D5]:A, [S1-D6]:C).

### 3.1 Channel Ownership Table

| Channel | Emotion Layer | Conversation Layer | System Layer | Idle Layer |
|---------|:---:|:---:|:---:|:---:|
| **Eyes (shape, eyelids)** | OWNS | mood hints only | overlay | neutral defaults |
| **Mouth (curve, open, width)** | OWNS | — | overlay | neutral defaults |
| **Gaze (eye position)** | — | All active conv states (extended from D6:C) | — | OWNS (wander) |
| **Face color** | OWNS | — | overlay | neutral color |
| **Border** | — | OWNS | — | off |
| **LED** | — | OWNS (mirrors border) | override | off |
| **Backlight** | — | — | OWNS | default brightness |

**Collision rules** (highest priority wins):
1. System overlay → overrides everything
2. Talking animation → overrides mouth (lip sync), coexists with emotion eyes
3. Conversation gaze → overrides idle gaze wander during all active conversation states (ATTENTION, LISTENING, PTT, THINKING, SPEAKING, ERROR). [S1-D6]:C specified "hybrid, incrementally extensible" — extended to all states for coherence.
4. Conversation border/LED → independent channel, no collision with emotion
5. Emotion → sets eyes/mouth/face color
6. Idle → fills anything not claimed above

### 3.2 Semantic vs Cosmetic Parameters (D10:B)

**Semantic** (deterministic — same input → same output):
- Mood selection (mood_id)
- Mood intensity target
- Conversation state (border color, animation type)
- Gaze target during LISTENING (center)
- Gaze direction during THINKING (aversion target)
- Transition choreography sequence
- Negative affect guardrail timers

**Cosmetic** (bounded stochastic — jitter permitted):
- Blink interval (2.0–5.0 s, uniform random)
- Idle gaze wander target (random within ±MAX_GAZE)
- Idle gaze wander interval (1.5–4.0 s, uniform random)
- Saccade micromotion (existing MCU implementation)
- Breathing phase (continuous, free-running)
- Sparkle activation (Bernoulli per frame, p=0.05)
- Sparkle position (uniform random across screen)

---

## 4. Visual Grammar

### 4.1 Emotion Expressions

#### 4.1.1 Mood Classification

| Class | Moods | Autonomous Use | Guardrails |
|-------|-------|----------------|------------|
| **Positive** | HAPPY, EXCITED, LOVE, SILLY | Unrestricted | None |
| **Neutral** | NEUTRAL, CURIOUS, THINKING, SLEEPY, SURPRISED, CONFUSED | Unrestricted | SURPRISED: startle reflex safety (§7.4) |
| **Negative** | SAD, SCARED, ANGRY | Conversation context only (D2:B) | See §7 |

**[Empirical]** Widen & Russell (2003): Children ages 4–6 reliably label happy, sad, angry, scared. Surprise and disgust are often confused. This informs the "safe set" — HAPPY, SAD, ANGRY, SCARED are the most legible. SURPRISED requires extra disambiguation via context.

**SURPRISED reclassification**: PE spec §4.1 places SURPRISED at (V=+0.15, A=+0.80) — positive valence, high arousal. Classifying it as Neutral is more principled than the original Negative classification, since surprise is positive-valent and often positive-contextual. High arousal warrants a safety cap (§7.4), but not a negative-affect guardrail.

**CONFUSED**: Added per PE spec §4.1 (V=-0.20, A=+0.30). Mild negative valence, low arousal — conveys uncertainty without distress. Classified as Neutral because the expression reads as "uncertain/puzzled" rather than "upset."

**[Empirical]** Di Dio et al. (2020): On stylized robot faces, children 4–8 achieve 68–99% recognition accuracy. Happiness and sadness are easiest (>90%); anger and fear are moderate (70–85%); surprise is hardest (<70%).

#### 4.1.2 Mood Parameter Targets

All parameters blend from neutral baseline via intensity (§4.1.3). Values are the full-intensity (1.0) targets.

| Mood | mouth_curve | mouth_width | mouth_open | lid_slope | lid_top | lid_bot | Face Color (R,G,B) |
|------|:-----------:|:-----------:|:----------:|:---------:|:-------:|:-------:|:-------------------:|
| NEUTRAL | 0.1 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | (50, 150, 255) |
| HAPPY | 0.8 | 1.1 | 0.0 | 0.0 | 0.0 | 0.4 | (0, 255, 200) |
| EXCITED | 0.9 | 1.2 | 0.2 | 0.0 | 0.0 | 0.3 | (100, 255, 100) |
| CURIOUS | 0.0 | 0.9 | 0.0 | -0.3 | 0.0 | 0.0 | (255, 180, 50) |
| SAD | -0.5 | 1.0 | 0.0 | -0.6 | 0.3 | 0.0 | (50, 80, 200) |
| SCARED | -0.3 | 0.8 | 0.3 | 0.0 | 0.0 | 0.0 | (180, 50, 255) |
| ANGRY | -0.6 | 1.0 | 0.0 | 0.8 | 0.4 | 0.0 | (255, 0, 0) |
| SURPRISED | 0.0 | 0.4 | 0.6 | 0.0 | 0.0 | 0.0 | (255, 255, 200) |
| SLEEPY | 0.0 | 1.0 | 0.0 | -0.2 | 0.6 | 0.0 | (40, 60, 100) |
| LOVE | 0.6 | 1.0 | 0.0 | 0.0 | 0.0 | 0.3 | (255, 100, 150) |
| SILLY | 0.5 | 1.1 | 0.0 | 0.0 | 0.0 | 0.0 | (200, 255, 50) |
| THINKING | -0.1 | 1.0 | 0.0 | 0.4 | 0.2 | 0.0 | (80, 135, 220) |
| CONFUSED | -0.2 | 1.0 | 0.0 | -0.15 | 0.1 | 0.0 | (200, 160, 80) |

**CONFUSED design rationale**: Mild furrowed brow (lid_slope -0.15), slightly raised upper lid (0.1). Very slight frown (mouth_curve -0.2), mouth closed. Warm amber-brown face color, distinct from all other moods. Less expressive than CURIOUS (lid_slope -0.3) to convey "uncertain" rather than "interested." Note: the CONFUSED *gesture* (GestureId::CONFUSED = 3) already exists and is distinct from this sustained *mood*. **[Provisional]** Parameters need sim prototyping in Stage 3 and child recognition testing in T3/T4 evaluation.

*Source: Verified from `face_state.cpp:257–321` and `face_state.cpp:620–680`.*

#### 4.1.3 Intensity Blending

**Mechanism** (D8:C — discrete with intensity blending):

```
displayed_value = neutral_value + (mood_target - neutral_value) × intensity
```

Applied identically to all 6 face parameters and to face color (RGB channels independently).

**Neutral baseline values**:
- mouth_curve: 0.1, mouth_width: 1.0, mouth_open: 0.0
- lid_slope: 0.0, lid_top: 0.0, lid_bot: 0.0
- Face color: (50, 150, 255) — cyan-blue

**Intensity range**: 0.0 (fully neutral) to 1.0 (full expression). Wire encoding: uint8 0–255.

**Typical intensity values**:
- AI conversation emotion: 0.7 (allows headroom for gesture overlay)
- Planner emotion: 0.5–1.0 (context-dependent)
- Recovery target: 0.0 (returns face to neutral)

### 4.2 Conversation State Signaling

**[Empirical]** Löffler et al. (2018): Color + motion multimodal coding offers the best cost/benefit ratio for robot emotion expression. Redundant cues across channels improve recognition. This supports the multimodal approach (D3:C) — border + LED + gaze + mood hints for each state.

**[Empirical]** Andrist et al. (2014): Gaze aversion during cognitive processing (thinking) is expected by humans and helps regulate turn-taking. Direct gaze during listening signals attention.

#### 4.2.1 State Definitions

Eight conversation states, matching the sim prototype (`conv_border.py:25–33`):

```
IDLE → ATTENTION → LISTENING → THINKING → SPEAKING → DONE → IDLE
                 ↘ PTT ↗                  ↗ ERROR ↗
```

#### 4.2.2 Per-State Visual Specification

**IDLE** (no conversation active)

| Channel | Behavior |
|---------|----------|
| Border | Off (alpha = 0) |
| LED | Off (0, 0, 0) |
| Gaze | MCU idle wander (1.5–4.0 s interval, spring dynamics) |
| Mood | Last set mood, or NEUTRAL if none |
| Flags | All idle defaults: IDLE_WANDER=1, AUTOBLINK=1, SPARKLE=1 |

---

**ATTENTION** (wake word detected or PTT first press — acknowledgment phase)

| Channel | Behavior |
|---------|----------|
| Border | Flash to light cyan (180, 240, 255), inward sweep animation over 400 ms |
| LED | Light cyan at 16% border alpha |
| Gaze | Snap to center (0, 0) — supervisor sends gaze override |
| Mood | Hold current mood (no change) |
| Flags | IDLE_WANDER=0 (disable wander for gaze lock) |
| Duration | 400 ms, then auto-advance to LISTENING |

**Awareness indicators addressed**: Acknowledgment (immediate visual response to wake word), temporal correlation (face changes synchronized with trigger).

**Timing budget**: Wake word detection latency (~80 ms frame + inference) + supervisor event propagation (~20 ms tick) + MCU render (~33 ms) = ~133 ms worst case from speech end to first visible pixel change. Well within the 200–300 ms perceptual threshold for "immediate" response. **[Inference — needs measurement]**

---

**LISTENING** (child is speaking, robot is attending)

| Channel | Behavior |
|---------|----------|
| Border | Teal (0, 200, 220), breathing alpha: 0.6 + 0.3 × sin(t × 2π × 1.5) |
| LED | Teal at 16% of border alpha |
| Gaze | Center lock (0, 0) — supervisor overrides MCU idle wander (D6:C) |
| Mood | NEUTRAL at intensity 0.3 (attentive neutral — slight engagement) |
| Flags | IDLE_WANDER=0, AUTOBLINK=1 |

**Awareness indicators addressed**: Gaze coherence (eyes locked on user), state continuity (steady breathing border).

**[Empirical]** Admoni & Scassellati (2017): Direct gaze signals attention and willingness to engage. During listening, the robot's gaze should be directed at the speaker.

---

**PTT** (tap-to-talk — variant of listening, toggled on/off by tapping PTT button)

| Channel | Behavior |
|---------|----------|
| Border | Warm amber (255, 200, 80), subtle pulse: 0.8 + 0.1 × sin(t × 2π × 0.8) |
| LED | Amber at 16% of border alpha |
| Gaze | Center lock (0, 0) |
| Mood | NEUTRAL at intensity 0.3 |
| Flags | IDLE_WANDER=0, AUTOBLINK=1 |

Visually distinct from LISTENING (amber vs teal) so the child/parent can confirm PTT is active. Same gaze and mood behavior.

---

**THINKING** (processing user input, waiting for AI response)

| Channel | Behavior |
|---------|----------|
| Border | Blue-violet (120, 100, 255), orbiting comet dots: 3 dots, 0.5 rev/s, base alpha 0.3 |
| LED | Blue-violet at 16% of border alpha |
| Gaze | Aversion — look up-right (gaze_x = +0.5, gaze_y = -0.3) — supervisor sends explicit target |
| Mood | THINKING at intensity 0.5 (mild: slight lid droop + slight frown) |
| Flags | IDLE_WANDER=0, AUTOBLINK=1 |

**[Empirical]** Andrist et al. (2014): Gaze aversion during processing is natural and expected. Looking away signals "I'm working on it" rather than "I'm ignoring you." The key finding is that *away* matters, not which specific direction. **[Theory]** Up-right is the conventional direction for cognitive processing (visual-constructed in NLP terms, though the neuroscience evidence for directionality is weak). **[Inference]** We use up-right (gaze_x=+0.5, gaze_y=-0.3) as a recognizable "thinking" direction. The exact direction should be validated in T3/T4 evaluation.

**Awareness indicators addressed**: Predictive cueing (gaze aversion signals processing before speech begins), gaze coherence (deliberate direction, not random wander).

---

**SPEAKING** (TTS playback active)

| Channel | Behavior |
|---------|----------|
| Border | White-teal (200, 240, 255), energy-reactive alpha: 0.3 + 0.7 × energy |
| LED | White-teal at 16% of border alpha |
| Gaze | Return to center (0, 0) on entry, then MCU handles via mood |
| Mood | Set by AI worker (emotion matching response content) |
| Mouth | Talking animation driven by TTS energy (0–255) at ~20 Hz |
| Flags | IDLE_WANDER=0, AUTOBLINK=1 |

**Transition into SPEAKING**: Gaze returns to center (anticipation blink, see §5.2), then talking begins. The gaze return from THINKING aversion to center functions as the predictive cue: "I'm about to speak."

**[Empirical]** Takayama et al. (2011, N=273): Applying animation principles (anticipation, follow-through) to robot motion significantly improves perceived quality of robot behavior overall. The study measures general quality ratings, not specific transition timing or gaze parameters. **[Inference]** We apply the anticipation principle specifically to gaze return before speaking as a predictive cue.

---

**ERROR** (conversation error — ASR failure, network timeout, etc.)

| Channel | Behavior |
|---------|----------|
| Border | Orange (255, 160, 60), flash for 100 ms then exponential decay over 700 ms |
| LED | Orange at 16% of border alpha, decays with border |
| Gaze | Quick look-away then return (gaze_x = -0.3 for 200 ms, then center) |
| Mood | Hold current; do not change mood on error |
| Flags | Inherit from previous state (preserve current wander/blink settings). On recovery, set target state defaults. |
| Duration | 800 ms total, then auto-return to IDLE or LISTENING (depending on session state) |

---

**DONE** (conversation session ending)

| Channel | Behavior |
|---------|----------|
| Border | Fade current color to black over 500 ms (alpha → 0) |
| LED | Fade with border |
| Gaze | Release to MCU idle wander (set IDLE_WANDER=1) |
| Mood | Fade intensity to 0.0 over 500 ms (return to neutral) |
| Flags | Restore idle defaults: IDLE_WANDER=1, AUTOBLINK=1, SPARKLE=1 |
| Duration | 500 ms, then state → IDLE |

### 4.3 Idle Behavior (D4:B)

When no conversation is active and no system overlay is shown.

| Feature | Specification | Parameter Type |
|---------|--------------|----------------|
| **Breathing** | Continuous sinusoidal eye scale modulation at 1.8 rad/s | Cosmetic |
| **Auto-blink** | Random interval 2.0–5.0 s, duration 180 ms | Cosmetic |
| **Gaze wander** | New random target every 1.5–4.0 s, spring dynamics (k=0.25, d=0.65) | Cosmetic |
| **Saccade jitter** | Small random perturbations on gaze position | Cosmetic |
| **Sparkle** | Random activation p=0.05/frame, random position, white pixel | Cosmetic |
| **Mood** | Set by personality worker snapshot. Default NEUTRAL at low intensity. During extended idle, the worker may project SLEEPY or CURIOUS per PE spec §7 idle rules. Context gate (§7.3) prevents negative moods during idle. | Semantic |
| **Border** | Off | Semantic |
| **LED** | Off | Semantic |
| **Backlight** | Default brightness (200/255) | Semantic |

**Emotional idle vs cosmetic idle**: The personality worker (PE spec §7) drives idle mood shifts at 1 Hz (semantic layer), while the MCU drives visual cosmetics (breathing, blink, gaze wander, sparkle) at 30 FPS (cosmetic layer). These operate on separate channels per §3.1 and do not interact. The MCU's cosmetic animations continue regardless of which mood the worker projects.

**Over-interpretation risk**: Idle gaze wander may cause children to believe the robot is "looking at something." This is the primary over-interpretation vector for idle state.

**Gaze displacement math** (verified from `config.h` and `face_ui.cpp`):
- MAX_GAZE = 12.0 — MCU picks random wander targets in [-12, 12]
- GAZE_EYE_SHIFT = 3.0 → max eye body displacement = ±36 px
- GAZE_PUPIL_SHIFT = 8.0 → max pupil displacement = ±96 px (clamped by eye bounds)
- On a 320 px wide screen, this is significant — pupils can visibly track to corners.

**Mitigation**: Idle gaze wander is *intentionally* large enough to read as "looking around" — it creates the impression of environmental awareness that makes the face feel alive. The spring dynamics (k=0.25, d=0.65) produce smooth, unhurried motion that avoids the "darting eyes" effect of instant snaps. The bounded stochastic policy (D10:B) means wander is cosmetic, not semantic — the same wander pattern in every idle session, with no correlation to actual objects.

**[Inference]** Over-interpretation risk is real and must be measured in T4 child evaluation (Phase 4 of eval plan). If testing shows excessive over-interpretation (>20% strong attribution), the fix is to reduce MAX_GAZE or idle wander target range — a Tuning-class change that does not require architectural revision.

### 4.4 System Overlays

System overlays use Buddy's face features to communicate system states — the same expressive language the child already understands. Each mode drives eyes, mouth, eyelids, and color directly through FaceState, with a small SDF status icon overlaid in the lower-right corner for additional context.

| System Mode | Face Expression | Status Icon | Priority |
|-------------|----------------|-------------|----------|
| BOOTING | Sleepy eyes opening → yawn → settle to neutral (~3 s) | None | Highest |
| ERROR_DISPLAY | Confused expression, slow headshake, warm orange/amber | Warning triangle (lower-right) | Highest |
| LOW_BATTERY | Heavy eyelids, periodic yawns, blue tone with brightness dim | Battery bar (lower-right, param: 0–255 fill level) | Highest |
| UPDATING | Thinking expression, gaze drifts up-right, blue-violet | Progress bar (bottom) | Highest |
| SHUTTING_DOWN | Reverse of boot — yawn, droop, eyelids close, fade to black (~2.5 s) | None | Highest |

System overlays suppress all other layers, including conversation border rendering and corner buttons. Corner button hit-testing is disabled while `SystemMode != NONE`. When a system overlay clears, the face returns to whatever tonic state was active (idle or conversation), and the border + buttons resume from their current conversation state.

---

## 5. Transition Choreography (D7:B)

**Principle**: Major transitions include anticipation micro-gestures. Minor transitions use the existing exponential tween. This addresses awareness indicator #3 (predictive cueing).

**[Empirical]** Takayama et al. (2011): Applying animation principles to robot motion improves perceived legibility. Thomas & Johnston (1981) codify "anticipation" — a preparatory motion before the main action — as one of the twelve principles of animation. **[Inference]** We implement anticipation as micro-gestures (blinks, gaze shifts) preceding major state transitions. The specific choreography timings (100 ms blink, 150 ms ramp-down, etc.) are design choices, not empirically derived values.

### 5.1 Major Transitions (Choreographed)

#### 5.1.1 Mood Switch Sequence

Triggered when the personality worker's snapshot contains a different mood than the currently displayed mood. The tick loop detects the mood change and orchestrates the visual transition. (In backstop mode — worker snapshot stale > 3000 ms — triggered when a raw AI emotion differs from the current mood.)

**Supervisor-managed sequence** (D8:C — intensity blending):

| Step | Duration | Action |
|------|----------|--------|
| 1. Anticipation blink | 100 ms | Trigger BLINK gesture (eyes close briefly) |
| 2. Intensity ramp-down | 150 ms | Current mood intensity 1.0 → 0.0 (linear ramp via tick_loop, ~8 SET_STATE commands at 50 Hz) |
| 3. Mood switch | 1 tick (20 ms) | Send new mood_id at intensity 0.0 |
| 4. Intensity ramp-up | 200 ms | New mood intensity 0.0 → target (linear ramp, ~10 SET_STATE commands) |

**Total duration**: ~470 ms

**Timing budget**: This sequence adds ~470 ms of latency to mood changes. **[Empirical]** Denham (1986) found that children use context + face together for emotion recognition; face alone is insufficient for nuanced recognition. **[Inference]** During conversation, 470 ms is acceptable because AI-chosen emotions arrive during SPEAKING phase where TTS audio provides the contextual bridge. The child hears the robot's tone before seeing the full mood shift, which should aid recognition. Must be validated in T3 developer review.

**Interrupt behavior**: If a new mood arrives during an active transition, the current transition is abandoned at its current intensity, and a new sequence starts from the current intensity value. No "melting face" — the ramp always moves toward a valid mood.

#### 5.1.2 Conversation Phase Transitions

Implemented in `ConvTransitionChoreographer` (sim: `tools/face_sim_v3/state/conv_choreographer.py`, supervisor: `supervisor/core/conv_choreographer.py`). The choreographer fires timed actions on state transitions and does not mutate face state directly — tick_loop reads outputs.

| Transition | Choreography | Duration | Implementation |
|-----------|-------------|----------|----------------|
| IDLE → ATTENTION | Border inward sweep + gaze snap to center | 400 ms | MCU border sweep + conv_state gaze override |
| ATTENTION → LISTENING | Border color blend (cyan → teal) + alpha settles to breathing | 200 ms (blended at BLEND_RATE=8.0/s) | MCU border BLEND_RATE |
| LISTENING → THINKING | Gaze ramp (ease-out, center → up-right) + border color shift + orbit dots start | 300 ms | Choreographer `_GazeRamp` (TRANS_LT_GAZE_RAMP_MS) + MCU spring |
| THINKING → SPEAKING | Anticipation blink + gaze ramp (ease-out, up-right → center, 50 ms delay) + border color shift | 350 ms | Choreographer blink gesture + `_GazeRamp` (TRANS_TS_GAZE_RAMP_MS). Double-blink prevention: choreographer blink suppresses MoodSequencer anticipation blink |
| SPEAKING → LISTENING | Re-engagement NOD (100 ms delay) | 450 ms | Choreographer nod gesture (TRANS_SL_NOD_DELAY_MS). Backchannel NOD suppressed while choreographer active |
| SPEAKING → DONE | Mood nudge to NEUTRAL @ 0.0 + mood pipeline suppressed (500 ms) + border fade | 500 ms | Choreographer mood_nudge + suppress_mood_pipeline (TRANS_SD_SUPPRESS_MS). MoodSequencer handles 470 ms ramp |
| Any → ERROR | Border flash (immediate) + gaze micro-aversion (200 ms) | 800 ms total | MCU border flash + conv_state micro-aversion override |

**Gaze priority chain** (tick_loop): choreographer ramp > conv_state static override > default.

**Interrupt behavior**: A new state transition cancels any active choreography sequence. The `on_transition()` method resets all state and loads the new transition's actions.

### 5.2 Minor Transitions (Tween)

These use the existing MCU exponential interpolation. No anticipation frames.

| Parameter | Tween Speed | Settle Time (~95%) |
|-----------|:-----------:|:------------------:|
| Gaze X/Y | Spring k=0.25, d=0.65 | ~200–300 ms |
| Eyelid top | 0.6 (rising) / 0.4 (falling) | ~100–150 ms |
| Eyelid bottom | 0.3 | ~150 ms |
| Eyelid slope | 0.3 | ~150 ms |
| Eye scale | 0.2 | ~250 ms |
| Eye openness | 0.4 | ~120 ms |
| Mouth curve | 0.2 | ~250 ms |
| Mouth open | 0.4 | ~120 ms |
| Mouth width | 0.2 | ~250 ms |
| Mouth wave | 0.1 | ~400 ms |

*Settle times are approximate at 30 FPS. Tween factor f applied per frame: after n frames, remaining distance = (1-f)^n.*

---

## 6. Timing Rules

### 6.1 Latency Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| Wake word → first visual change | < 200 ms | Must feel "immediate." **[Theory]** Clark (1996) discusses grounding in communication — listeners expect timely acknowledgment of communicative acts. **[Inference]** The 200–300 ms perceptual threshold for "immediate" causal attribution is drawn from general psychophysics (Exner, 1875; Pöppel, 2009), not Clark specifically. We adopt < 200 ms as our target. |
| PTT press → first visual change | < 100 ms | Button press has stronger immediacy expectation than voice. |
| End-of-utterance → THINKING visual | < 300 ms | Child should see the robot "start thinking" before silence feels awkward. |
| THINKING → SPEAKING visual | < 100 ms after TTS audio begins | Gaze return and border shift must lead or coincide with first audio frame. |
| Mood command → visible change begins | < 50 ms | MCU response time (1–2 render frames). |

### 6.2 Hold Times

Minimum duration an expression must be displayed before the next transition is permitted.

| Expression Type | Minimum Hold | Rationale |
|----------------|:------------:|-----------|
| Any mood | 500 ms | **[Empirical]** Widen & Russell (2003): Children categorize facial expressions with high accuracy, but the study measures categorization, not minimum display duration. **[Inference]** We set 500 ms as the minimum hold to ensure the expression is perceptible and not subliminal. Must be validated in T4 evaluation. |
| Conversation state border | 300 ms | Border is peripheral; needs less hold time. But transitions faster than 300 ms cause flicker. **[Inference]** |
| Gesture | Full gesture duration | Gestures are self-timed (80 ms – 10 s). Never interrupt mid-gesture. |
| Negative mood | See §7 (guardrails) | Minimum 500 ms, maximum per-mood. |

### 6.3 Talking Animation Timing

| Parameter | Value | Source |
|-----------|-------|--------|
| Energy update rate | ~20 Hz (from TTS worker) | `tts_worker.py` LipSyncTracker |
| MCU talking timeout | 450 ms | `face_ui.cpp:25` — if no SET_TALKING received within 450 ms, MCU auto-stops talking animation |
| Mouth wave frequency | 8.0 rad/s phase advance | `face_state.cpp` mouth render |
| Mouth wave spatial frequency | 12.0 cycles across width | `face_ui.cpp` render_mouth |

**Prosody selection**: The emotion tag used for TTS prosody (voice pitch, speed, emphasis) is derived from the personality worker's projected mood (PE spec §11.5), not from the face communication layer. This spec covers only the visual lip sync mechanism.

---

## 7. Negative Affect Guardrails (D2:B)

**Framing**: As a caretaker/guide, the robot uses negative emotions to validate the child's feelings during conversation ("I understand that's scary") but never displays sustained distress. Kahn et al. (2012) demonstrates that children attribute genuine emotional states to robots — prolonged negative affect may cause real concern in 4–6 year olds. **[Empirical]**

**Operational definition of "destabilizing"**: The child exhibits distress behaviors — crying, flinching, backing away, asking parent for help — or reports negative feelings attributed to the robot's expression (not to conversational content). The guardrails below are calibrated to prevent this by: (a) limiting duration so negative affect is always brief, (b) capping intensity so expressions read as "mild concern" not "real distress," (c) mandatory recovery so the face always returns to neutral/positive.

**Distinguishing expression from content**: The robot may *discuss* sad or scary topics (conversational content) while displaying mild empathetic affect. The face should not independently produce distress beyond what the conversation warrants. "Allowed to mirror the child" is explicitly scoped: the AI may choose SAD to empathize with a child's sadness, but the intensity cap ensures the robot looks "understanding" not "distraught."

### 7.1 Per-Mood Guardrails

| Mood | Max Duration | Anticipation Required | Recovery Target | Recovery Time |
|------|:----------:|:-----:|:---------------:|:------------:|
| SAD | 4.0 s | Yes (blink) | NEUTRAL @ 0.0 | 500 ms ramp-down |
| SCARED | 2.0 s | Yes (blink) | NEUTRAL @ 0.0 | 300 ms ramp-down |
| ANGRY | 2.0 s | Yes (blink) | NEUTRAL @ 0.0 | 300 ms ramp-down |

For SURPRISED (Neutral class, high-arousal safety), see §7.4.

**Primary enforcement**: The personality worker (PE spec §9) tracks how long the projected mood has been in a negative state. When the duration cap is exceeded, a recovery impulse toward baseline is injected, pulling affect toward NEUTRAL. The worker's snapshot, consumed by the tick loop, reflects this recovery automatically.

**Safety backstop**: If the personality worker's snapshot is stale (age > 3000 ms, indicating the worker is dead or hung), the tick loop enforces the same duration caps directly. This prevents a failed worker from leaving a negative mood stuck on the face. The backstop uses the same durations and intensity caps as the primary enforcement.

Under normal operation, only the personality worker enforces. The tick loop backstop is a safety net, not a parallel enforcement path.

**AI override**: If the AI sends a new (different) mood before the guardrail timer expires, the new mood is accepted (via the personality worker's integrator) and the timer resets. This allows the AI to sequence emotions naturally (e.g., SAD → NEUTRAL → HAPPY) without the guardrail interrupting.

### 7.2 Intensity Limits for Negative Moods

In the caretaker role, negative moods are displayed at reduced intensity to soften their visual impact:

| Mood | Max Intensity | Rationale |
|------|:------------:|-----------|
| SAD | 0.7 | Recognizable but not overwhelming. Reduced lid droop + mouth curve. |
| SCARED | 0.6 | Wide eyes moderated. Mouth open reduced. |
| ANGRY | 0.5 | Strongest restriction. Furrowed brows at half-strength read as "concerned" rather than "furious." |

For SURPRISED intensity cap (0.8), see §7.4.

If the AI sends intensity above the cap, the personality worker clamps it via the affect vector integrator. In backstop mode (stale snapshot), the tick loop clamps it directly.

### 7.3 Context Gate

Outside active conversation (no session in progress), negative moods (SAD, SCARED, ANGRY) are **blocked entirely**.

**Primary enforcement**: The personality worker's context gate (PE spec §9.2) prevents negative mood projection outside active conversation. If the affect vector decays through negative territory after conversation ends, the context gate overrides the projection to NEUTRAL before the snapshot reaches the tick loop.

**Safety backstop**: If the personality worker snapshot is stale (age > 3000 ms) and the tick loop falls back to raw AI emotion passthrough (PE spec §11.3), the tick loop applies the same context gate: it rejects negative moods when `conversation_active == False`.

SURPRISED is not context-gated (Neutral class). It may be used in any context, subject to the startle reflex safety cap (§7.4).

### 7.4 Startle Reflex Safety (SURPRISED)

SURPRISED is classified as Neutral (§4.1.1) — not Negative — but its high arousal (+0.80 in VA space) warrants a duration and intensity cap to prevent sustained startle:

| Mood | Max Duration | Max Intensity | Recovery Target | Recovery Time |
|------|:----------:|:------------:|:---------------:|:------------:|
| SURPRISED | 3.0 s | 0.8 | NEUTRAL @ 0.0 | 400 ms ramp-down |

This rule applies in all contexts (conversation and idle). Enforcement follows the same tiered model as negative mood guardrails: personality worker primary (PE spec §9.1), tick loop backstop.

---

## 8. Gesture Catalog

Gestures are phasic — they overlay the current tonic state and expire after their duration.

| GestureId | Default Duration | Use Context | Semantic Weight |
|-----------|:---------------:|-------------|:---------------:|
| BLINK | 180 ms | Transition choreography, natural rhythm | Cosmetic |
| WINK_L | 200 ms | Playful acknowledgment | Semantic |
| WINK_R | 200 ms | Playful acknowledgment | Semantic |
| NOD | 350 ms | Agreement, understanding | Semantic |
| HEADSHAKE | 350 ms | Disagreement, negation | Semantic |
| LAUGH | 500 ms | Joy, humor response | Semantic |
| CONFUSED | 500 ms | Uncertainty, didn't understand | Semantic |
| WIGGLE | 600 ms | Playful energy, excitement | Semantic |
| SURPRISE | 800 ms | Startle, amazement | Semantic |
| HEART | 2.0 s | Affection (solid eye heart shape) | Semantic |
| X_EYES | 2.5 s | Comedic "dizzy" / overload | Semantic |
| SLEEPY | 3.0 s | Tired, winding down | Semantic |
| RAGE | 3.0 s | Comedic anger (fire effect) | Semantic |

**Semantic vs cosmetic**: BLINK is the only cosmetic gesture (used for transitions and auto-blink). All others carry meaning and should only be triggered by AI/planner commands, not autonomously.

**Guardrail note**: RAGE and X_EYES trigger special visual effects (fire particles, X-shaped eyes) that override normal rendering. Per the caretaker role, these should be used sparingly and only in clearly playful/comedic conversational contexts. The AI system prompt should restrict their use.

---

## 9. Protocol Mapping

### 9.1 Existing Commands (Sufficient)

| Behavior | Command | Payload | Notes |
|----------|---------|---------|-------|
| Set emotion + intensity + gaze | SET_STATE (0x20) | mood_id, intensity_u8, gaze_x_i8, gaze_y_i8, brightness_u8 | Gaze override for LISTENING sent here |
| Trigger gesture | GESTURE (0x21) | gesture_id, duration_ms | Anticipation blinks use this |
| System overlay | SET_SYSTEM (0x22) | mode, phase, param | Unchanged |
| Talking animation | SET_TALKING (0x23) | talking, energy | Unchanged |
| Feature flags | SET_FLAGS (0x24) | flags bitfield | IDLE_WANDER control for gaze lock |

### 9.2 New Command Required: SET_CONV_STATE (0x25)

The conversation border is currently sim-only (`conv_border.py`). Porting it to firmware requires a new command.

**Proposed payload**:

```
struct __attribute__((packed)) FaceSetConvStatePayload {
    uint8_t conv_state;  // ConvState enum (0–7)
};
```

**Byte layout** (1 byte):
- Offset 0: conv_state (uint8_t) — maps to ConvState enum

**Energy for SPEAKING border**: The MCU border renderer reads audio energy from `fs.talking_energy`, which is already latched by the SET_TALKING (0x23) command at ~20 Hz. During SPEAKING, border alpha = 0.3 + 0.7 × fs.talking_energy. This avoids duplicating the energy field — SET_TALKING is the single source of truth for audio energy.

**ConvState enum** (firmware side):

```cpp
enum class ConvState : uint8_t {
    IDLE      = 0,
    ATTENTION = 1,
    LISTENING = 2,
    PTT       = 3,
    THINKING  = 4,
    SPEAKING  = 5,
    ERROR     = 6,
    DONE      = 7,
};
```

**MCU responsibilities** (border rendering moves to firmware):
- Maintain border state machine (color, alpha, animation timers)
- Render border frame (4 px) + glow (3 px) via SDF
- Render orbit dots for THINKING state
- Blend border alpha based on state (breathing, pulse, energy-reactive)
- Set LED color = border color × 0.16

**Supervisor responsibilities**:
- Track conversation state and send SET_CONV_STATE on **state transitions only** (no per-tick energy — border reads `fs.talking_energy` from SET_TALKING)
- Continue sending SET_TALKING with energy at ~20 Hz during SPEAKING (already implemented)
- Manage gaze overrides via SET_STATE (gaze_x, gaze_y fields)
- Manage flag overrides via SET_FLAGS (IDLE_WANDER bit)

### 9.3 Flag Usage Per Conversation State

| Conv State | IDLE_WANDER | AUTOBLINK | SPARKLE | Notes |
|-----------|:-----------:|:---------:|:-------:|-------|
| IDLE | 1 | 1 | 1 | All defaults |
| ATTENTION | 0 | 1 | 1 | Wander off for gaze snap |
| LISTENING | 0 | 1 | 1 | Wander off for center lock |
| PTT | 0 | 1 | 1 | Same as LISTENING |
| THINKING | 0 | 1 | 0 | Wander off; sparkle off (cleaner thinking visual) |
| SPEAKING | 0 | 1 | 1 | Wander off during speech |
| ERROR | — | — | — | No flag change |
| DONE | 1 | 1 | 1 | Restore defaults |

### 9.4 Link Assumptions

The supervisor communicates with the face MCU over USB-CDC serial (COBS-encoded binary packets with CRC16-CCITT).

**Reliability**: USB-CDC serial is reliable and ordered — no packet loss, no reordering. The COBS framing + CRC provides error detection; corrupted packets are discarded by the receiver.

**Throughput**: During SPEAKING (peak load), supervisor sends up to 3 command types per tick: SET_STATE (5 bytes payload), SET_TALKING (2 bytes payload), SET_CONV_STATE (1 byte payload). With COBS overhead (~2 bytes) + CRC (2 bytes) + delimiter (1 byte) per packet, total is ~39 bytes/tick × 50 Hz = ~1950 bytes/s — well within USB full-speed bandwidth.

**Timing**: MCU applies last-value-wins per command type per render frame (33 ms). If a packet is delayed by >1 tick (20 ms), the next tick's packet supersedes it. No accumulation or queuing on the MCU side — only the most recent value of each command type is rendered.

**Mood transition bandwidth**: The mood switch choreography (§5.1.1) sends ~18 SET_STATE packets over 350 ms (intensity ramp). This is well within link capacity and each packet supersedes the previous if delayed.

### 9.5 Touch Semantics for Conversation Control

**PTT button** (FaceButtonId.PTT): Tap-toggle — each tap in the PTT zone inverts the listening state. First tap → ATTENTION → PTT (listening active). Second tap → THINKING (listening ended). Toggle fires on touch release within the same hit zone. Already defined in protocol.

**ACTION button** (FaceButtonId.ACTION): Context-gated behavior:
- **During active conversation** (`conversation_active == True`): CLICK → cancel session (→ DONE state). Provides a way to abort a conversation that's stuck or unwanted.
- **Outside conversation** (`conversation_active == False`): CLICK → greet routine (current behavior, `tick_loop.py:331-337`).

**Implementation note**: Requires modifying the ACTION button handler in `tick_loop.py` to check `conversation_active` before deciding greet vs cancel.

**Soft buttons**: Corner button hit zones are flush with screen edges (Fitts's Law — edge targets benefit from infinite depth). Constants defined in `BTN_CORNER_*` (parity-checked between sim and firmware):
- PTT: bottom-left, 60×46 px zone — x ∈ [0, 60], y ∈ [194, 240], icon center (30, 217)
- Cancel: bottom-right, 60×46 px zone — x ∈ [260, 320], y ∈ [194, 240], icon center (290, 217)

Corner buttons are hidden and hit-testing is disabled during system overlays (§4.4).

### 9.6 Supervisor Tick Loop Integration

The conversation state machine runs in `tick_loop` at 50 Hz. On each tick:

1. **Check for conversation events** (wake word, end-of-utterance, TTS start/finish, errors)
2. **Advance conversation state** based on events
3. **On state change**:
   a. Send SET_CONV_STATE with new state
   b. Send SET_FLAGS with updated flag byte
   c. If entering LISTENING/ATTENTION: send SET_STATE with gaze (0, 0)
   d. If entering THINKING: send SET_STATE with gaze (0.5, -0.3) and mood THINKING @ 0.5
   e. If entering SPEAKING: send SET_STATE with gaze (0, 0), initiate anticipation blink
   f. If entering DONE: begin mood intensity ramp-down over 500 ms
4. **During SPEAKING**: TTS energy continues flowing via SET_TALKING at ~20 Hz (already implemented). MCU border reads `fs.talking_energy` directly — no additional energy commands needed.
5. **Mood transition choreography**: if the personality worker's snapshot contains a new mood different from the currently displayed mood, run §5.1.1 sequence via tick-by-tick intensity ramping. The tick loop does not interpret AI emotions directly — it reads the worker's projected mood from the snapshot. (In backstop mode — stale snapshot — falls back to raw AI emotion.)

---

## 10. Sim/MCU Divergence Audit (D9:C)

One-time audit. After resolution, sim is the design authoring surface. MCU must match within tolerance. Divergence is a CI-detectable error.

### 10.1 Known Divergences and Resolutions

| Parameter | Sim Value | MCU Value | Resolution | Rationale |
|-----------|-----------|-----------|:----------:|-----------|
| Blink interval | 3.0–7.0 s | 2.0–5.0 s | **MCU** (2.0–5.0 s) | More natural blink rate. Human adult rate is ~3–4 s average; children blink faster. |
| Idle gaze interval | 1.0–3.0 s | 1.5–4.0 s | **MCU** (1.5–4.0 s) | Slower wander feels more intentional, less jittery. |
| Background color | (10, 10, 14) | (0, 0, 0) | **MCU** (0, 0, 0) | Pure black maximizes contrast on ILI9341 TN panel. Sim's dark gray was aesthetic choice for pygame. |
| THINKING color | Falls through to NEUTRAL | (80, 135, 220) | **MCU** (80, 135, 220) | Explicit color is correct — THINKING should be visually distinct. Sim bug. |
| Talking phase speed | Variable | Fixed | **MCU** (fixed) | Consistent wave speed simplifies debugging and matches TTS energy rhythm. |

### 10.2 Enforcement Policy

After this audit, all parameter values are defined in this spec (§4, §6). Going forward:

1. **Sim is the design authoring surface** — new values are prototyped in sim first
2. **MCU must match within tolerance** — facial parameter targets must be identical; timing may differ by ±1 frame (33 ms) due to frame rate differences
3. **CI check**: A script compares sim constants (`face_state_v2.py`) against MCU constants (`face_state.cpp`, `config.h`) and fails on divergence
4. **Exception process**: If hardware testing reveals a value that must differ (e.g., display gamma), the exception is documented in this spec with rationale

---

## 11. Priority Layer Composition

Updated priority stack incorporating conversation state:

```
┌─────────────────────────────────────────────────┐
│ Layer 0: System Overlay                         │  BOOTING / ERROR / LOW_BATTERY / UPDATING / SHUTTING_DOWN
│          (full screen takeover)                  │  Source: robot.mode
├─────────────────────────────────────────────────┤
│ Layer 1: Talking Animation                      │  Lip sync (mouth only)
│          (mouth override)                        │  Source: TTS worker energy
├─────────────────────────────────────────────────┤
│ Layer 2: Conversation State                     │  Border + LED + gaze override + mood hints
│          (multimodal, D3:C)                     │  Source: tick_loop state machine
├─────────────────────────────────────────────────┤
│ Layer 3: Emotion                                │  Eyes + mouth + face color
│          (personality worker snapshot)           │  Source: personality worker → tick loop
├─────────────────────────────────────────────────┤
│ Layer 4: Idle                                   │  Neutral + breathing + blink + gaze wander + sparkle
│          (MCU autonomous)                        │  Source: MCU defaults
└─────────────────────────────────────────────────┘
```

**Key changes from current**: Layer 2 (Conversation State) is new. It owns the border, LED, and gaze-during-LISTENING. It does *not* own eyes/mouth — those remain under the Emotion layer. The two layers coexist on separate channels per §3.1. Layer 3 source updated: the personality worker is now the single source of emotional truth (PE spec §11.1). AI worker and planner emotions are processed as impulses by the personality worker, which projects a final mood + intensity consumed by the tick loop.

**Collision resolution**:
- If Layer 2 sets gaze (LISTENING center lock) while Layer 3 sets a mood, the gaze from Layer 2 wins. Mood still controls eyes/mouth/color.
- If Layer 1 (talking) is active while Layer 3 (emotion) sets a mood, talking controls the mouth. Emotion controls eyes and color.
- If Layer 0 (system) is active, everything else is suppressed.

---

## 12. Conversation State Machine — Full Specification

### 12.1 State Transition Table

| Current State | Event | Next State | Actions |
|--------------|-------|-----------|---------|
| IDLE | wake_word_detected | ATTENTION | Send CONV_STATE(ATTENTION), SET_FLAGS(wander=0), SET_STATE(gaze=center) |
| IDLE | ptt_toggled_on | ATTENTION | Same as wake word. PTT flag set → advance to PTT after ATTENTION completes. If toggled off during ATTENTION → auto-advance to LISTENING. |
| ATTENTION | 400 ms elapsed (PTT not active) | LISTENING | Send CONV_STATE(LISTENING), SET_STATE(gaze=center) |
| ATTENTION | 400 ms elapsed (PTT active) | PTT | Send CONV_STATE(PTT) — tap-to-talk active, enter PTT listening |
| ATTENTION | ptt_toggled_on (during ATTENTION) | PTT | Send CONV_STATE(PTT) — late tap also enters PTT |
| LISTENING | vad_end_of_utterance | THINKING | Send CONV_STATE(THINKING), SET_STATE(gaze=aversion, mood=THINKING@0.5) |
| LISTENING | session_cancelled | DONE | Send CONV_STATE(DONE) |
| PTT | ptt_toggled_off | THINKING | Send CONV_STATE(THINKING), SET_STATE(gaze=aversion, mood=THINKING@0.5) |
| PTT | session_cancelled | DONE | Send CONV_STATE(DONE) |
| THINKING | tts_started | SPEAKING | Anticipation blink, send CONV_STATE(SPEAKING), SET_STATE(gaze=center) |
| THINKING | ai_error | ERROR | Send CONV_STATE(ERROR) |
| THINKING | 30 s timeout | ERROR | Send CONV_STATE(ERROR) — AI hung |
| SPEAKING | tts_finished | LISTENING or DONE | If multi-turn: → LISTENING. If session done: → DONE |
| SPEAKING | tts_cancelled | DONE | Send CONV_STATE(DONE) |
| ERROR | 800 ms elapsed | IDLE or LISTENING | If session still active: → LISTENING. Otherwise: → IDLE |
| DONE | 500 ms elapsed | IDLE | Restore idle flags, clear conversation state |

### 12.2 Multi-Turn Handling

A conversation session may include multiple turns (child speaks → robot responds → child speaks again). The state machine loops:

```
LISTENING → THINKING → SPEAKING → LISTENING → THINKING → SPEAKING → ... → DONE
```

Session end is signaled by `AI_CONVERSATION_DONE` event. The SPEAKING → DONE transition only fires when the AI signals the session is complete *and* TTS has finished.

### 12.3 Edge Cases

| Scenario | Behavior |
|----------|----------|
| Wake word during SPEAKING | Ignored — robot finishes its turn. New wake word after DONE/IDLE starts fresh session. |
| PTT during SPEAKING | Session interrupts. Stop TTS, → LISTENING (PTT variant). |
| Touch cancel during any state | → DONE immediately. Graceful shutdown. |
| Network loss during THINKING | 30 s timeout → ERROR → IDLE. |
| AI emotion during LISTENING | Integrated into personality worker's affect vector immediately, but not displayed on face until SPEAKING entry (§2.3 suppress-then-read). Face stays attentive neutral during LISTENING. On SPEAKING entry, tick loop reads current snapshot (which already reflects the integrated emotion). |
| Rapid mood commands during SPEAKING | Each triggers mood switch sequence (§5.1.1). Minimum hold (500 ms) enforced — second mood queued if too fast. |

---

## 13. Summary of Awareness Indicators Coverage

Cross-reference against the 5 awareness indicators from [S1-C1]:

| Indicator | How This Spec Addresses It | Measured By |
|-----------|---------------------------|-------------|
| **Temporal correlation** | Wake word → ATTENTION in <200 ms. PTT → visual in <100 ms. Every conversation event has a corresponding visual change. | Response latency (§6.1) |
| **Gaze coherence** | LISTENING = center lock. THINKING = deliberate aversion. SPEAKING = return to center. No random wander during conversation. | Gaze variance per state (automated) |
| **Predictive cueing** | Anticipation blink before mood switch. Gaze return before speaking. Border color shift before state change. | Presence of anticipation frame (binary per transition) |
| **State continuity** | 500 ms minimum hold for moods. 300 ms minimum hold for border states. No single-frame flickers. | Hold time compliance (automated) |
| **Acknowledgment** | ATTENTION state with border flash + gaze snap within perceptual threshold of wake word/PTT. | Time-to-first-visual-change (instrumented) |

---

## 14. Summary of Randomness Failure Mode Fixes

Cross-reference against the 5 randomness failure modes from [S1-C1]:

| Failure Mode | Fix in This Spec |
|-------------|-----------------|
| **Uncorrelated gaze during conversation** | §4.2 — IDLE_WANDER=0 during all conversation states. Gaze is supervisor-controlled (center lock or deliberate aversion). |
| **Unexplained emotion transitions** | §5.1.1 — Mood switch sequence with anticipation blink + intensity ramp. Changes feel intentional. §6.2 — 500 ms minimum hold prevents flickers. |
| **No THINKING visual signal** | §4.2.2 THINKING state — blue-violet orbit border + gaze aversion + THINKING mood. Processing delay is now visible and intentional. |
| **Talking stops before speech ends** | §6.3 — MCU talking timeout is 450 ms. Supervisor must send SET_TALKING updates at ≥2 Hz during TTS playback. Existing bug to fix in implementation. |
| **No wake word acknowledgment** | §4.2.2 ATTENTION state — border flash + gaze snap within <200 ms of detection. |
