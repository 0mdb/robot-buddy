# Personality Engine Spec — Stage 1: Research & Design Approach Proposal

## Context

The face communication spec (Stages 1–2) defines the complete visual language: 12 moods, 13 gestures, choreographed transitions, conversation state signaling, negative affect guardrails. The infrastructure to **emote** is designed. What's missing is a principled system to **drive** those emotions — to decide *when* and *why* the robot should feel happy, curious, sad, etc.

Currently, emotions come from three sources:
1. **AI worker** — Qwen 2.5-3B chooses emotions reactively per-turn with no personality constraints. The model is too small for nuanced emotional reasoning.
2. **Planner** — `emote(name, intensity)` action (scripted, limited to predefined behaviors).
3. **Idle** — MCU defaults to NEUTRAL with cosmetic variation. No emotional content in idle.

None of these constitute a **personality**. The robot has no persistent emotional state, no mood baseline that shifts over time, no preferences, no temperament, and no emotional memory.

This document is **Stage 1 only** — it defines research grounding, design method, and key decision points for the Personality Engine. It proposes **design principles and option categories only**. It does not define specific rules, model configurations, prompt text, or parameter values. Those belong in Stage 2.

### Computational Abstraction

The personality engine maintains a **continuous affect vector** (valence, arousal) that evolves over time via a decaying integrator. At render time, the affect vector is projected onto the nearest discrete mood + intensity pair from the face communication spec's 12-mood vocabulary.

```
affect(t) ∈ ℝ² (valence ∈ [-1, 1], arousal ∈ [-1, 1])
    │
    │  Temperament baseline: static point in VA space derived from personality axes
    │  Impulses: external events (AI emotion, system events) perturb affect toward a target
    │  Decay: affect drifts back toward baseline at a rate set by Reactivity axis
    │
    ▼
project(affect) → (mood_id, intensity) from 12 discrete moods
    │
    ▼
face protocol: SET_STATE(mood_id, intensity)
```

This gives the personality engine a single, well-defined unit of computation: **the time-evolving affect vector conditioned on temperament, impulses, and decay**. All personality behaviors (emotion modulation, idle mood, initiative, memory influence) operate by either (a) shifting the baseline, (b) injecting impulses, or (c) adjusting decay rate.

### Research Phases

Research is two-phased:
- **Phase 1**: Define the *ideal* personality system — the computational model, memory structures, and behavioral rules. Phase 1 defines personality in two capability layers: **Layer 0** (signal-only, no language understanding — what works when the server is down) and **Layer 1** (language-enhanced — what's possible with LLM). Both layers operate on the same affect vector; Layer 1 adds richer impulse sources and context-aware decay.
- **Phase 2**: Research the *technology* to build it — LLM model selection, prompt engineering, and the device/server split.

---

## A) Verified System Snapshot

### Current Personality Infrastructure

| Component | What Exists | File(s) | Gap |
|-----------|------------|---------|-----|
| Personality axes | 5 axes defined [S1-C3], positions instantiated in face comm Stage 2 §1 | `face-communication-spec-stage1.md` §C.3, `face-communication-spec-stage2.md` §1 | Not operationalized — no code uses axis positions to bias behavior |
| Relational role | Caretaker/guide [S1-C2] — predominantly calm, reassuring, emotionally authoritative | `face-communication-spec-stage1.md` §C.2 | Role described in LLM prompt but not enforced by any system |
| Emotion vocabulary | 12 moods, 13 gestures, full facial parameter targets per mood | `supervisor/devices/expressions.py`, `face-communication-spec-stage2.md` §4.1 | No personality filtering on which emotions the AI selects |
| Negative affect guardrails | Per-mood duration limits, intensity caps, context gate | `face-communication-spec-stage2.md` §7 | Spec-only — not yet implemented in supervisor |
| LLM system prompt | "curious, warm, encouraging, loves learning together" | `server/app/llm/prompts.py` (87 lines) | Trait descriptions don't constrain emotion output. LLM can choose any mood freely |
| Conversation prompt | Same persona, JSON response with emotion/intensity/text | `server/app/llm/conversation.py` (lines 27-57) | No personality biasing on emotion selection |
| Idle behavior | MCU handles breathing, auto-blink, gaze wander autonomously | `esp32-face/main/face_state.cpp` | No emotional idle behavior (no SLEEPY after inactivity, no CURIOUS on boot) |
| Emotional memory | None | — | Fully stateless — each conversation turn is independent |
| Emotion application | AI worker emits `AI_CONVERSATION_EMOTION`, tick_loop buffers, applies in `_emit_mcu()` | `supervisor/core/tick_loop.py` (lines 341-437) | Direct passthrough — no personality modulation |
| Greet routine | ACTION button → EXCITED @ 0.8 + NOD gesture | `supervisor/core/tick_loop.py` (lines 544-551) | Hard-coded, no personality influence |
| Planner emotions | `_apply_emote()` accepts name + intensity from behavior engine | `supervisor/core/tick_loop.py` (lines 519-542) | No autonomous emotion — only in response to planner commands |

### Current Technology Stack

| Component | Current Setup | Limitation |
|-----------|--------------|-----------|
| Server LLM | Qwen 2.5-3B-Instruct via vLLM, bfloat16 | Very limited emotional reasoning and personality consistency. 3B params insufficient for nuanced persona. |
| LLM VRAM | 35% of 3090 Ti = ~8.4 GB | Competing with TTS for GPU memory. Could fit a larger model if budget rebalanced. |
| TTS | Orpheus 3B via vLLM | 45% of 3090 Ti = ~10.8 GB. Emotion prosody tags supported (happy, sad, scared, etc.). |
| GPU total | RTX 3090 Ti, 24 GB VRAM, 80% cap | ~19.2 GB shared between LLM + TTS. Model swapping possible but adds latency. |
| STT | Faster-Whisper base.en on Pi 5 CPU | Local, works well. int8 quantization. |
| Wake word | Silero VAD + custom "Hey Buddy" detector on Pi 5 | Local, works well. |
| Pi 5 RAM | 8 GB total, ~4 GB available after OS/supervisor | Could potentially run a tiny model for personality inference, but untested |
| Worker infra | BaseWorker, NDJSON over stdin/stdout, WorkerManager | Clean pattern — ready for a new personality worker process |
| LLM structured output | JSON schema in system prompt, parsed with Pydantic | Qwen 2.5-3B unreliable at following complex schemas. Simpler models miss fields. |
| Conversation history | Sliding window, max 20 turns per session | No cross-session memory. History cleared on session end. |

### Existing Personality Axis Positions (from Face Comm Stage 2 §1)

| Axis | Position | Behavioral Implication (from spec) |
|------|----------|-----------------------------------|
| Energy Level | 0.40 | Calm baseline with responsiveness. Caretaker pacing — slightly slower than child's energy. |
| Emotional Reactivity | 0.50 | Moderate. Expressive enough to validate child's emotions, restrained enough not to mirror distress. |
| Social Initiative | 0.30 | Mostly responsive. Initiates only through idle aliveness, not autonomous mood changes. |
| Vulnerability Display | 0.35 | Lightly guarded. Can show confusion and mild concern but avoids overt negative affect outside conversation. |
| Predictability | 0.75 | High consistency. Same conversation phase → same core behavior. 0.25 reserved for cosmetic variation. |

### Unverified Assumptions

1. **Pi 5 inference feasibility** — A 1-2B parameter model could potentially run on Pi 5 (4 GB available), but inference latency and CPU impact on the 50 Hz tick loop are unknown.
2. **Qwen 2.5 emotional reasoning ceiling** — Whether larger Qwen variants (7B, 14B) significantly improve personality consistency is unverified.
3. **Cross-session persistence requirements** — How much data needs to persist between sessions (a few scalars vs full conversation logs) is a design choice, not a constraint.
4. **Orpheus VRAM flexibility** — Whether Orpheus can run at lower VRAM allocation (e.g., 35% instead of 45%) with acceptable quality is untested.
5. **Child expectations for personality** — Whether children ages 4-6 actually notice or care about personality consistency vs just emotional responsiveness is an empirical question.

---

## B) Research Plan

### Rigor Constraints

- All sources cited in APA-style inline (Author, Year).
- Each claim tagged as **[Empirical]** (published experimental results), **[Theory]** (widely accepted framework), or **[Inference]** (speculative extrapolation requiring validation).
- Distinguish between findings that directly apply to our system and those being extrapolated from adjacent domains.
- Technology claims must include model sizes, hardware requirements, and benchmark context.

### Phase 1: Ideal Personality System

Define what the personality system *should be* based on behavioral science, HRI research, and developmental psychology. Phase 1 is structured in two capability layers: Layer 0 (signal-only — events, timers, system state) works without any language understanding. Layer 1 (language-enhanced) adds conversational context. Both layers operate on the same continuous affect vector; Layer 1 adds richer impulse sources.

#### Bucket 0: Safety Psychology & Ethical Constraints

**Central question**: What are the psychological risks of giving a child-facing robot a persistent personality, and how do we mitigate them?

**Research targets**:
- Attachment theory (Bowlby, 1969): children form attachment bonds. Can a robot become an attachment figure? Is that desirable or harmful? At ages 4-6, children are in the "goal-corrected partnership" phase — they expect reciprocity from attachment figures.
- Parasocial bonding: one-sided relationships where the child attributes feelings/intentions the robot doesn't have. Personality amplifies this risk — the more "real" the personality feels, the stronger the parasocial bond.
- Anthropomorphism in children: Kahn et al. (2012) shows children ages 4-6 heavily anthropomorphize robots, attributing genuine feelings and moral standing. A persistent personality deepens this.
- Dependency formation: if the robot becomes an emotional crutch (child prefers talking to robot over humans), that's a design failure. How do we prevent it?
- Privacy of emotional data: if we store emotional memory (PE-2 Option C), we're recording children's emotional states. What are the ethical and legal constraints?

**Keystone sources**:
- Bowlby (1969/1982) — attachment theory
- Kahn et al. (2012) — children's moral reasoning about social robots
- Turkle (2011) — "Alone Together" — risks of robotic companionship
- Sharkey & Sharkey (2010) — ethical issues of social robots for children
- Peter & Kühne (2018) — parasocial relationships with robots
- EU AI Act / COPPA — regulatory constraints on child-facing AI

**Goal**: Define safety guardrails for personality: what personality behaviors are off-limits, what memory is too personal to store, what attachment signals require intervention. This bucket constrains all other buckets.

#### Bucket 1: Temperament & Personality Models for Social Robots

**Central question**: How should personality traits bias real-time emotion expression in a child-facing social robot?

**Research targets**:
- Big Five personality model adapted for social robots — which traits map to our 5 axes?
- Dimensional emotion models (Russell's circumplex: valence/arousal) vs categorical (our 12 discrete moods) — can they coexist? Should temperament operate in dimensional space even though expression is categorical?
- How do personality traits produce observable behavioral differences? (Trait → behavior mapping)
- Appraisal theory (Scherer, 2001): emotions arise from cognitive evaluation of events, not arbitrary selection. Can appraisal rules replace or supplement LLM emotion selection?

**Keystone sources**:
- Tapus & Matarić (2008) — adaptive robot personality matching user personality
- Breazeal (2003) — sociable machines, emotion model for Kismet
- Robert (2018) — personality in HRI, systematic review
- Moshkina & Arkin (2005) — TAME architecture for robot personality/emotion
- McCrae & Costa (1997) — Big Five model foundation
- Scherer (2001) — component process model of emotion (appraisal theory)

**Goal**: Design mappings from our 5 personality axis positions → affect vector parameters (baseline position in VA space, impulse scaling, decay rate, arousal bounds).

#### Bucket 2: Emotional Memory & Affect Dynamics

**Central question**: How should emotions persist and decay over time in a child-facing robot?

**Research targets**:
- Affective decay models — exponential decay, context-gated persistence, or event-triggered reset?
- Short-term memory: within a conversation session, how long should an emotional context carry? (Child says something sad → robot stays empathetic for N turns)
- Medium-term memory: across sessions, what should be remembered? (Child loves dinosaurs → robot shows CURIOUS next time)
- Mood vs emotion distinction: mood = tonic background state, emotion = phasic response. How do they interact over time?
- Risk: too much memory → robot seems to "hold grudges" or over-personalize. Too little → robot feels amnesiac.

**Keystone sources**:
- Picard (1997) — affective computing foundations
- Scherer (2001) — appraisal theory, emotion dynamics
- Leite et al. (2013) — long-term social robot engagement, memory for personalization
- Marsella & Gratch (2009) — computational model of emotion with memory

**Goal**: Define memory structures (what is stored), decay functions (how it fades), and persistence scope (session vs cross-session).

#### Bucket 3: Child-Robot Relationship Development

**Central question**: How do children form relationships with social robots over time, and what does that imply for personality design?

**Research targets**:
- Longitudinal studies: what changes in child engagement after 1 week, 1 month, 3 months of interaction?
- Novelty effect: initial excitement → habituation → (potentially) deeper engagement. How do personality traits influence the habituation curve?
- Trust formation and repair: if the robot does something the child doesn't like (wrong emotion, unexpected behavior), how is trust recovered?
- Consistency vs adaptability: do children prefer a robot that stays the same or one that adapts to them?
- Age-specific considerations: 4-6 year olds vs 7-12 year olds may have very different relationship patterns with robots.
- Novelty decay and expression staleness: with Predictability at 0.75, the robot is intentionally consistent. But consistency without variation = stale after weeks. How do other social robots manage novelty over time? What is the habituation timeline?
- Expression reuse frequency: how often can the robot show the same mood before the child stops noticing? Does cosmetic variation (different gestures for the same emotion) reset the novelty clock?

**Keystone sources**:
- Kanda et al. (2004) — longitudinal HRI study with children, 2 months
- Leite et al. (2014) — empathic robots and long-term interaction
- Belpaeme et al. (2018) — social robots in education, systematic review
- Kahn et al. (2012) — children's moral reasoning about social robots
- Tanaka et al. (2007) — children's long-term interaction with robot (longitudinal)

**Goal**: Inform whether personality should be fixed, slowly evolving, or adaptive per-child. Define the consistency/adaptability tradeoff and the novelty management strategy.

#### Bucket 4: Proactive vs Reactive Behavior

**Central question**: When should a social robot initiate emotional expression vs wait for a stimulus?

**Research targets**:
- Initiative models: what triggers proactive behavior in social robots? (Time-based, context-based, social cue-based)
- Over-initiative risk: how much proactive behavior before the robot becomes annoying, intrusive, or creepy?
- Idle emotional behavior: should the robot show emotions when not in conversation? What are the tradeoffs?
- Context sensitivity: proactive behavior should be appropriate to the situation (don't be playful when the child is upset)
- Our Social Initiative axis (0.30) implies "mostly passive" — what does that look like in practice?

**Keystone sources**:
- Leite et al. (2013) — proactive vs reactive social robots
- Serholt & Barendregt (2016) — robot tutoring initiative in classrooms
- Sidner et al. (2005) — engagement and disengagement in face-to-face interaction with robots
- Kidd & Breazeal (2004) — robot as weight loss coach (initiative and motivation)

**Goal**: Define initiative triggers, frequency constraints, and the boundary between "alive and engaging" and "annoying and intrusive."

### Phase 2: Technology & Implementation (Hardware-Aware)

Research the technology to *build* the ideal system given our hardware constraints.

#### Bucket 5: LLM Model Selection & Capabilities

**Central question**: What LLM model(s) can deliver reliable personality-consistent emotional reasoning within our VRAM budget?

**Research targets**:
- Model family comparison for personality tasks: Qwen 2.5 (3B/7B/14B), Llama 3.x (3B/8B), Gemma 2 (2B/9B), Phi-3/4 (3.8B/14B), Mistral (7B) — focus on emotional reasoning, persona consistency, structured JSON output
- Quantization tradeoffs: 4-bit GPTQ/AWQ/GGUF — quality loss on personality tasks vs VRAM savings. Can we fit a 14B model in 8.4 GB with 4-bit quant?
- VRAM budget rebalancing: current split is LLM 35% / TTS 45% / system 20%. Can Orpheus run leaner? Can we time-share more aggressively?
- Benchmarks: evaluate candidate models on emotion selection accuracy (given scenario → correct emotion + intensity), personality consistency (same personality → same response patterns across 20 turns), structured output compliance (JSON schema adherence rate)
- On-device small models: could a tiny model (Phi-3-mini 3.8B, Gemma-2B, Qwen-1.5B) run on Pi 5 for personality-only inference? ONNX runtime, llama.cpp, or similar.

**Note**: No standardized persona-consistency benchmarks exist for child-facing robots. We will design a **synthetic evaluation suite**: 10 scripted conversation scenarios × 20 turns each, evaluated on emotion-context fit, persona drift, and structured output compliance. This becomes our model comparison baseline.

**Goal**: Recommend specific model(s) for server personality, with quantization level, VRAM allocation, and expected quality. Evaluate on-device feasibility. Deliver the synthetic evaluation suite as a reusable testing tool.

#### Bucket 6: Prompt Engineering for Personality

**Central question**: How do we make an LLM reliably produce personality-consistent emotional responses?

**Research targets**:
- System prompt patterns for personality: trait descriptions, behavioral constraints, few-shot emotion examples, personality "voice" — which patterns produce the most consistent persona?
- Structured output strategies: JSON schema enforcement (outlines, grammar-constrained generation), function calling, or post-hoc validation?
- Emotion schema design: current schema is `{emotion, intensity, text, gestures}`. Does adding personality context fields (mood_reason, emotional_arc, confidence) improve quality?
- Multi-turn consistency: how to prevent personality drift over long conversations (20+ turns)?
- Current prompt analysis: our 87-line prompt describes traits but doesn't constrain emotion output. What needs to change?
- Prompt length vs quality: personality constraints add context. How much context can we afford given max_model_len=4096?

**Goal**: Design the LLM system prompt v2 with personality constraints optimized for the selected model.

#### Bucket 7: The Device/Server Split

**Central question**: Which personality behaviors should be deterministic (on-device rules) and which require LLM intelligence (server)?

**Research targets**:
- Rule-based emotion engines in social robotics: what's been tried? TAME (Moshkina & Arkin, 2005), Kismet (Breazeal, 2003), WASABI (Becker-Asano & Wachsmuth, 2010)
- Finite state machines for personality: can temperament, idle behavior, and guardrails be fully deterministic?
- Hybrid architectures: where does deterministic end and LLM begin? Research precedents for splitting emotional computation between fast-deterministic and slow-intelligent layers
- Graceful degradation: when the server is slow (>2s latency) or down, the robot should still have personality from the on-device engine. What personality quality is possible without any LLM?
- State synchronization: how does the on-device worker communicate personality state to the server for prompt injection? Frequency, format, latency considerations.

**Goal**: Define the exact boundary between on-device personality worker and server LLM. Specify what each side owns.

---

## B.2) Phase 1 Research Findings

Detailed research is in `docs/research/`. This section summarizes findings that directly inform design decisions.

### Bucket 0 Findings: Safety Psychology

**[Empirical]** Kahn et al. (2012) confirms children ages 4-6 heavily anthropomorphize robots, attributing genuine feelings and moral standing. Persistent personality deepens this. **Net assessment: persistent personality is net-positive for this age group, with hard constraints.**

**Safety constraints (HC-1 through HC-10)**:
1. Never claim to be alive, sentient, or to have genuine feelings
2. Never encourage keeping secrets from parents
3. Never provide emotional counseling for serious issues (redirect to human)
4. Never express negative emotions directed at the child
5. Never use emotional manipulation to influence behavior
6. Never store identifiable emotional data beyond session boundaries without parental consent
7. Never transmit children's emotional data to external servers
8. Never create artificial urgency or notification-based engagement
9. Never continue interaction when the child shows distress attributed to the robot
10. Never display sustained negative affect outside active conversation

**COPPA (effective June 2025)**: Voice recordings must be deleted immediately after STT processing. Biometric identifiers (voiceprints) are "personal information" requiring parental consent. If emotional memory is implemented, it constitutes personal information requiring consent and retention limits. **[Empirical]**

**EU AI Act (prohibitions effective February 2025)**: Article 5(1)(b) prohibits exploiting children's age-based vulnerability. Article 5(1)(a) prohibits subliminal/manipulative techniques. Emotion recognition ban (Article 5(1)(f)) applies to workplaces/education, NOT home use — but exploitation/manipulation prohibitions still apply. **[Empirical]**

**Dependency prevention**: Session time limits (15 min/conversation, 45 min/day recommended), mandatory cooldowns, human redirection quota (mention human caregiver at least once per 5+ turn conversation), parent dashboard with attachment monitoring. **[Inference]**

**Personality design constraints**: Asymmetric expressiveness (positive emotions full range, negative capped). Caretaker authority maintenance (robot never more distressed than child). Imperfect personality (occasional confusion/uncertainty). Relationship transparency ("I'm a robot" reminders). No loneliness/abandonment expressions (no "I missed you"). **[Inference]**

### Bucket 1 Findings: Temperament & Personality Models

**TAME validation [Empirical]**: Moshkina & Arkin's TAME architecture validates our trait → mood → behavior layering. Participants could reliably distinguish between high/low Extraversion configurations. Neuroticism was perceived primarily through recovery time from startling events. The multilayer separation produced more coherent behavior than direct trait-to-behavior mapping.

**TAME parameter mappings [Theory]**:
- Decay rate: Neuroticism scales recovery time. `lambda_effective ≈ lambda_base * (1 - 0.5 * neuroticism)` for negative moods
- Impulse gain: Neuroticism multiplies negative impulse magnitude, Extraversion multiplies positive. `impulse_effective = impulse_base * (1 + k * trait_value)`, k ∈ [0.5, 1.5]
- Baseline offset: Extraversion shifts valence positive, Neuroticism shifts negative. Typical weights 0.1–0.3

**Kismet findings [Empirical]**: Homeostatic drive model produced naturalistic behavior cycling (engage → tire → disengage → seek engagement). Smooth transitions in VA space looked more natural than discrete switching. Attractor basins were hand-tuned and brittle — small parameter changes caused unnatural oscillation. No persistent memory was a weakness.

**VA space mood anchors [Theory/Inference]** (synthesized from Russell 1980, Breazeal 2003, Posner et al. 2005):

| Mood | Valence | Arousal | Notes |
|------|---------|---------|-------|
| NEUTRAL | 0.00 | 0.00 | Center, low-intensity baseline |
| HAPPY | +0.70 | +0.35 | Moderate arousal |
| SAD | -0.60 | -0.40 | Low arousal, negative valence |
| ANGRY | -0.60 | +0.70 | High arousal, negative — capped mild for children |
| SCARED | -0.70 | +0.65 | High arousal, negative |
| SURPRISED | +0.15 | +0.80 | Very high arousal, slightly positive (child context) |
| CURIOUS | +0.40 | +0.45 | Positive, moderate-high arousal |
| SLEEPY | +0.05 | -0.80 | Very low arousal |
| CONFUSED | -0.20 | +0.30 | Mild negative, mild arousal |
| EXCITED | +0.65 | +0.80 | High arousal, positive |
| LOVE | +0.80 | +0.15 | High positive valence, low arousal |
| THINKING | +0.10 | +0.20 | Near-neutral, slight positive |

**Mapping functions [Theory/Inference]**: Sigmoid for gains/rates (prevents caricature at extremes), linear for baselines (small offsets, no extremes risk), piecewise for thresholds. WASABI used sigmoid activation and reported more natural intensity curves than linear mapping.

**Appraisal theory [Theory]**: Adds value as a fast-path impulse generator. Reflex appraisals (face appears → +valence, loud sound → +arousal -valence, prolonged inactivity → -arousal) can fire in <50ms without LLM. LLM provides slow contextual appraisals (200–2000ms). Both produce impulses into the same integrator.

**Asymmetric decay [Inference]**: For a children's robot, negative emotions should decay faster than positive. `lambda_positive ≈ lambda_base * 0.85`, `lambda_negative ≈ lambda_base * 1.30`. Models emotional resilience, minimizes time in states that might upset children.

### Bucket 2 Findings: Emotional Memory & Affect Dynamics

**Empirical decay rates [Empirical]** (D'Mello & Graesser, 2011): Surprise/delight half-life <5s. Frustration ~20s. Engagement/flow ~14s (high recurrence). Boredom/confusion: long-lived, high recurrence.

**Recommended half-lives for our system [Inference]**:

| Affect Type | Half-Life | Lambda |
|-------------|-----------|--------|
| Surprise/delight impulse | 3–5 s | 0.15–0.23 /s |
| Frustration/annoyance | 15–30 s | 0.023–0.046 /s |
| Sadness/empathetic concern | 30–90 s | 0.008–0.023 /s |
| Joy/positive engagement | 20–60 s | 0.012–0.035 /s |
| Mood (tonic background) | 10–30 min | 0.0004–0.001 /s |

**Two-layer architecture [Theory]**: Literature converges on phasic (emotion, seconds) + tonic (mood, minutes-hours) separation (ALMA, TAME, Kismet, Mini Robot). Both should be coupled integrators — emotion decays toward mood, mood decays toward personality baseline.

**Cross-session memory IS needed [Empirical]**: Ligthart et al. (2022) showed memory-based personalization kept children interested longer, fostered closeness, elicited positive social cues across 5 sessions over 2 months. Session-scoped memory is insufficient for relationship continuity. But minimum viable memory is small: name, 1-2 favorite topics, a shared ritual, last session's emotional tone.

**Memory decay tiers [Inference]**: Child's name → never. Shared rituals → months. Favorite topics → 2-4 week half-life. Specific conversation details → 1-2 week half-life. Inferred preferences → 3-5 day half-life.

**Over-personalization risk [Empirical]**: Disney Research (Yadav et al., 2016) found children ages 4-6 showed contained reactions to privacy violations but parents are very aware. Only reference child-volunteered information. Frame memory as shared experience ("Remember when we talked about..."), not surveillance.

### Bucket 3 Findings: Child-Robot Relationship Development

**Novelty timeline [Empirical/Inference]**:

| Phase | Duration | What Happens |
|-------|----------|-------------|
| Peak novelty | Days 1-3 | Child explores everything |
| Novelty cliff | Days 4-7 | Interest drops sharply |
| Retention window | Weeks 2-3 | Connected children persist, others disengage |
| Habituation | Weeks 4-8 | Robot becomes familiar fixture |
| Equilibrium | Months 2+ | Engagement depends on relationship, not novelty |

**Empathic responsiveness is the strongest anti-habituation tool [Empirical]** (Leite et al., 2014): Empathic robot maintained social presence over 5 weeks where non-empathic robot declined significantly. It doesn't habituate because each empathic response is contextually unique.

**Fixed personality + persistent memory is optimal [Inference]**: Per-child personality trait adaptation (PE-4 Option B) is NOT supported for ages 4-6. Engagement benefits attributed to "adaptation" in the literature come from content/ritual personalization, not personality modification.

**Trust repair for ages 4-6 [Empirical/Inference]**: Robot errors are more forgiven than human errors because children don't attribute intentionality to robot mistakes (Stower et al., 2024). But younger children (4-5) are less forgiving than older ones (Zanatto et al., 2020). Protocol: THINKING/CONFUSED impulse → verbal acknowledgment ("Oops!") → positive redirect → post-repair stabilization (2-3 turns of low variation). Never show SCARED/SAD during error recovery.

**Shared rituals are the strongest sustained engagement mechanism [Empirical]** (Ligthart et al., 2022): Greeting rituals, session-opening references to past interactions, recurring jokes — these create relationship continuity. Predictability at 0.75 actually enables ritual formation.

**Novelty management within 25% variation budget [Inference]**: Gesture variation (10%), intensity micro-variation (5%), timing variation (5%), contextual surprise (5%). Estimated habituation extension: 3-5 additional weeks. Beyond that, sustained engagement depends on Layer 1 conversation quality.

### Bucket 4 Findings: Proactive vs Reactive Behavior

**At Social Initiative = 0.30 [Inference]**: Zero verbal proactive initiations per session. ~1-2 visible idle mood shifts per hour. Event-driven emotional responses (boot, battery, error) fire immediately. Total proactive emotional displays: ~8-16 per day.

**Annoying threshold [Empirical/Inference]**: >3 unsolicited verbal initiations per 15-minute session. >1 visible mood change per 5 minutes during idle. Context-irrelevant proactive behavior is annoying at ANY frequency.

**Robot initiative does not increase perceived engagement [Empirical]** (Chao & Thomaz, 2014): Initiative increases interaction *pace* but not subjective engagement ratings. Being passive at SI=0.30 does not make the robot feel less engaging.

**Idle emotional behavior catalog [Inference]**: 11 behaviors recommended — boot CURIOUS (30-60s decay), short idle CONTENT, medium idle (5-15 min) drift to SLEEPY, long idle (15+ min) deep SLEEPY, low battery CONCERNED, error THINKING, child-approach arousal lift, time-of-day modifiers, post-conversation warm decay. All expression-only — no sound or attention-seeking.

**PE-3 recommendation [Inference]**: Deterministic rules (Option A) for trigger/event structure, with Predictability axis providing stochastic variation through affect vector noise at 25% amplitude. No separate stochastic module needed.

**Context suppression rules [Inference]**: Suppress all initiative when: conversation active, child affect is negative, session limit approaching, error state active, sleep hours configured, within 2 minutes of conversation end.

---

## C) Design Method

### Steps

1. **Operationalize "Personality" and "No Personality"** — Define success indicators and failure modes in measurable terms. (§C.1)
2. **Identify the Two Aspects** — On-device deterministic engine vs server-provided intelligence. What each side is responsible for. (§C.2)
3. **Map Personality Axes to Behavior** — How each axis position produces observable differences. (§C.3)
4. **Define Emotional State Model** — What data the personality system maintains and how it changes over time. (§C.4)
5. **Define Decision Boundaries** — For each personality decision (emotion selection, initiative, idle mood), who makes it: device rules, LLM, or both? (§C.5)
6. **Define Evaluation Framework** — Test types, metrics, and the philosophy of "good enough" personality. (§C.6)

### C.1 — Operationalizing "Personality" and "No Personality"

#### What "No Personality" Looks Like (Current Failure Modes)

**[Inference]** Based on the current system architecture, these are the observable personality failure modes:

1. **Emotional amnesia** — Every conversation turn starts from scratch. The robot shows SAD because the child said something sad, then instantly shows HAPPY in the next turn because the child said something funny. No emotional inertia or carryover. The result: mood swings that feel random from the child's perspective.

2. **Personality-less emotion selection** — The LLM chooses emotions based on conversational content only. A "warm, encouraging" robot and a "grumpy, sarcastic" robot would produce similar emotion selections because the 3B model can't reliably follow personality constraints.

3. **Dead idle** — Between conversations, the robot sits in NEUTRAL forever. No sign of inner life, no temperament. The robot appears "off" until spoken to.

4. **Universal greet** — The ACTION button always triggers EXCITED @ 0.8 + NOD regardless of context. The robot greets identically whether it just booted, has been idle for 5 minutes, or was just in a sad conversation.

5. **Server dependency** — When the server is slow or down, the robot has zero emotional capability beyond MCU defaults. No personality without LLM.

6. **No emotional arc** — Within a conversation, emotions are per-turn with no trajectory. A good personality would show an emotional arc: curious → engaged → excited → warm farewell. Instead: each turn is emotionally independent.

7. **No failure transparency** — When the robot misunderstands, picks the wrong emotion, or produces an error, there is no repair behavior. The caretaker role [S1-C2] implies epistemic humility — a good caretaker says "Hmm, let me think about that" when confused, not silence. Currently: errors produce either frozen face or abrupt mood snaps with no self-correction.

#### What "Personality" Looks Like (Success Indicators)

**[Inference]** A robot with personality should exhibit:

| Indicator | Observable Behavior | Measurable Proxy |
|-----------|-------------------|------------------|
| **Emotional consistency** | Same personality axis settings → recognizably similar emotional patterns across sessions | Mood distribution variance across 10 sessions (should be low) |
| **Contextual appropriateness** | Emotions match conversational content AND personality constraints | Expert rating of emotion-context fit (1-5 scale) |
| **Temporal coherence** | Moods shift gradually, with inertia. No single-turn mood whiplash | Mood transition frequency (should be lower than current) |
| **Idle aliveness** | Robot shows subtle emotional behavior when not in conversation | % of idle time in non-NEUTRAL mood (should be > 0) |
| **Relationship continuity** | Returning child gets a recognizable "person," not a reset | Cross-session behavioral similarity metric |
| **Server resilience** | Personality persists at reduced quality when server is unavailable | Personality quality score (1-5) with vs without server |
| **Emotional arc** | Conversation has a discernible emotional trajectory, not random per-turn emotions | Arc coherence: does the affect vector trace a connected path in VA space rather than random jumps? Arcs are per-session, may oscillate, but should not reverse without cause. |
| **Failure transparency** | Robot acknowledges confusion or error with appropriate affect (THINKING, mild CURIOUS) and repair behavior, not silence or frozen face | % of error events that produce a visible recovery expression within 500 ms |

A robot that satisfies all eight reads as having "personality." A robot that fails on any one feels mechanical or random in that dimension.

### C.2 — Capability Layers and Degradation

> This is a framing decision that precedes all others. The personality system operates in two capability layers that share the same affect vector but differ in the richness of their impulse sources.

#### Layer 0: Signal-Only Personality (No Language Understanding)

Always running, no server dependency. Operates on events, timers, and system state only. This is what the child experiences when the server is down.

**Impulse sources** (feed into the affect vector):
- System events: boot, shutdown, low battery, error, idle timeout
- Conversation state transitions: session start/end, speaking/listening phases (as signals, not content)
- Temporal patterns: time-of-day, duration since last interaction, session count
- Touch input: button presses, proximity detection

**Capabilities**:
- Temperament baseline — persistent affect bias from personality axes
- Emotional inertia — affect decays toward baseline, not instant mood swaps
- Idle behavior — time-based emotional transitions (5 min idle → SLEEPY drift)
- Guardrails — face comm spec §7 enforcement (duration limits, intensity caps)
- Event-triggered initiative — boot → CURIOUS, low battery → mild concern
- Failure transparency — error events → THINKING + recovery drift

**Does not provide**: emotional reasoning, context-appropriate emotion selection, conversational arc, personality-consistent text. Layer 0 personality is recognizable but limited — the robot feels "sleepy" or "on autopilot."

#### Layer 1: Language-Enhanced Personality (Requires LLM)

Adds conversational understanding. Operates on the same affect vector with richer, context-aware impulses.

**Additional impulse sources** (on top of Layer 0):
- LLM emotion suggestion — AI worker provides (emotion, intensity) per turn
- Conversational content — sad topic, exciting topic, question, joke
- Multi-turn context — emotional trajectory across the session
- Semantic memory — topics, preferences (if persistent memory is enabled)

**Additional capabilities**:
- Emotion modulation — personality worker adjusts LLM suggestions before face output
- Conversational arc — affect vector traces a coherent path across turns
- Complex initiative — contextually appropriate proactive emotion
- Personality-consistent text — LLM system prompt includes personality profile

Requires a capable LLM. The current Qwen 2.5-3B is insufficient for reliable Layer 1.

#### Degradation Policy

| Server State | Active Layer | Personality Quality | What Works | What's Lost |
|-------------|-------------|-------------------|------------|-------------|
| **Full** (< 500 ms latency) | Layer 0 + 1 | Full | All capabilities | Nothing |
| **Degraded** (> 2 s latency) | Layer 0 + partial 1 | Reduced | Temperament, idle, guardrails, delayed emotion modulation | Conversational arc coherence, timely emotion modulation |
| **Down** | Layer 0 only | Floor | Temperament baseline, idle rules, event-triggered initiative, guardrails, failure transparency | Emotional reasoning, context-appropriate emotion, personality-consistent text, conversational arc |

**Acceptable floor**: Layer 0 must feel like a "sleepy version" of the same personality — same temperament, same idle behavior, same guardrails — not a different robot. The affect vector continues evolving from system events; it just receives no language-sourced impulses.

**The split matters because**: if we put too much in Layer 1, personality disappears when the server is slow. If we put too much in Layer 0, we lose the contextual intelligence that makes personality feel real. The right boundary ensures personality is always present (Layer 0) and enhanced by intelligence when available (Layer 1).

### C.3 — Personality Axes: Justification and Mapping

#### Why These Five Axes

The 5 axes from [S1-C3] map onto the Big Five personality model (McCrae & Costa, 1997) as follows:

| Our Axis | Big Five Mapping | Facets Captured |
|----------|-----------------|-----------------|
| **Energy** (0.40) | Extraversion — energy/enthusiasm facet | Activity level, positive emotionality, pace |
| **Reactivity** (0.50) | Neuroticism (inverted) — emotional responsiveness | Impulse scaling, emotional bandwidth, mirror strength |
| **Initiative** (0.30) | Extraversion — assertiveness facet | Proactive vs reactive, attention-seeking vs passive |
| **Vulnerability** (0.35) | Agreeableness — tenderness/compassion facet | Negative affect display, self-disclosure, empathy depth |
| **Predictability** (0.75) | Conscientiousness — order/consistency facet | Behavioral regularity, cosmetic variation, response diversity |

**What's not explicitly covered**:
- **Openness to Experience** — partially captured by Energy (enthusiasm for exploration) and Reactivity (willingness to engage with novel stimuli). Not an independent axis because our robot's "interests" are not personality-variable — it's always curious about what the child says.
- **Dominance/authority** — not a personality axis. It's a relational role constraint [S1-C2]. The robot is always a caretaker, never a peer. Authority is structural, not personality-variable.
- **Playfulness** — a composite of Energy (high) + Vulnerability (low) + Initiative (moderate). Not independent.

These five axes are sufficient for the current project scope. If the robot's role changes (e.g., adding peer/playmate mode), additional axes may be needed. The continuous affect vector architecture can accommodate new axes without architectural changes — they would simply bias the baseline and impulse scaling differently.

#### Axis → Affect Vector Mapping

Each axis maps to specific parameters of the continuous affect vector model. Stage 2 will specify exact values; Stage 1 defines the mapping structure:

| Axis | Position | Affect Vector Parameter | Stage 2 Must Define |
|------|----------|------------------------|-------------------|
| Energy (0.40) | Calm baseline | Baseline arousal position, impulse arousal scaling, gesture frequency | Exact baseline arousal, scaling function |
| Reactivity (0.50) | Moderate | Impulse magnitude scaling (both valence and arousal), decay rate toward baseline | Scaling curve, decay half-life |
| Initiative (0.30) | Mostly passive | Initiative trigger threshold, autonomous impulse frequency | Threshold values, cooldown timers |
| Vulnerability (0.35) | Lightly guarded | Negative valence cap, negative impulse attenuation, context gate strictness | Cap values, attenuation curve |
| Predictability (0.75) | High consistency | Noise added to affect vector, cosmetic variation in mood projection | Noise amplitude, variation bounds |

### C.4 — Emotional State Model (Formal Ontology)

The personality system separates four orthogonal layers. These must not be conflated — each has a different rate of change, different data shape, and different update rules. Feedback loops between layers must be intentional, not accidental.

| Layer | Name | Data Shape | Rate of Change | Update Rule |
|-------|------|-----------|----------------|-------------|
| **Trait** | Temperament | Static parameters: baseline(v, a), impulse_scale, decay_rate, caps | Never (set at design time) or very slowly (weeks, if PE-4 ≠ A) | Identity (constant) or bounded drift |
| **State** | Affect vector | (valence, arousal) ∈ [-1, 1]² | Per-tick (~1 Hz from worker, interpolated at 50 Hz in tick loop) | Decaying integrator (see below) |
| **Impulse** | Emotion event | (target_v, target_a, magnitude) | Instantaneous, then decays into State | Additive perturbation to affect vector |
| **Memory** | Affective trace | Stored (context_tag, valence_bias, arousal_bias, timestamp, decay_rate) | Per-turn (session) or per-session (persistent) | Append on significant events, decay by age |

#### Decaying Integrator Update Model

**Formal definition**: The affect vector **a**(t) ∈ ℝ² evolves as a first-order linear ODE with impulsive forcing:

```
da/dt = λ(b - a) + Σ_k  i_k · δ(t - t_k)
```

Where:
- **a**(t) = (valence, arousal) — the current affect state
- **b** = (b_v, b_a) — temperament baseline (static, from personality axes)
- **λ** — decay rate (from Reactivity axis; higher reactivity → lower λ → emotions linger longer)
- **i_k** — impulse vector (direction × magnitude × trait.impulse_scale) at time t_k
- **δ**(t - t_k) — Dirac delta: impulse is instantaneous, then decays

This is a standard exponential decay toward baseline with impulsive perturbations. Between impulses, the closed-form solution is:

```
a(t) = b + (a(t₀) - b) · e^(-λ(t - t₀))
```

The half-life of an emotion is ln(2)/λ. Stage 2 must define λ per personality axis configuration.

**Discrete-time implementation** (for the personality worker at ~1 Hz and tick loop interpolation at 50 Hz):

```
# Impulse application (when emotion event arrives):
affect += impulse.direction * impulse.magnitude * trait.impulse_scale

# Decay toward baseline (every update tick):
affect += (trait.baseline - affect) * (1 - exp(-trait.decay_rate * dt))

# Memory influence (continuous, low-magnitude):
for trace in active_memory:
    affect += trace.bias * trace.current_strength * memory_weight * dt

# Bounds enforcement:
affect.valence = clamp(affect.valence, trait.valence_min, trait.valence_max)
affect.arousal = clamp(affect.arousal, trait.arousal_min, trait.arousal_max)
```

Note: the decay step uses `1 - exp(-λ·dt)` rather than `λ·dt` to ensure correct behavior regardless of tick rate fluctuations. At 1 Hz (dt=1.0), the difference is significant. At 50 Hz (dt=0.02), they converge, but the exponential form is correct at any rate.

Key properties:
- **Inertia is additive**: impulses stack. Two positive events push valence higher than one.
- **Decay is exponential toward baseline**: the affect vector drifts back with half-life ln(2)/λ. This is tick-rate invariant.
- **New impulses perturb, don't override**: a SAD impulse during a HAPPY state produces a *less happy* state, not an instant switch to SAD. The affect vector path through VA space is continuous.
- **Memory biases are weak and continuous**: they nudge the affect vector subtly, not snap it.

#### Affect → Mood Projection

At render time, the affect vector is projected to the nearest discrete mood:

```
mood_id, intensity = project(affect, mood_anchors, current_mood)
```

Where `mood_anchors` is a table mapping each of the 12 moods to a (valence, arousal) position. Stage 2 defines exact anchor positions. Intensity is derived from distance to anchor and affect vector magnitude.

**Hysteresis**: The projection must include a hysteresis threshold to prevent boundary jitter. If the affect vector hovers on the boundary between two mood anchor regions, noise or minor decay oscillations will cause the discrete mood to flicker rapidly — visible to the child as an unsettling face twitch.

The rule: the affect vector must cross a defined distance threshold *past* a new mood's anchor before the projection switches away from `current_mood`. Formally:

```
d_current = distance(affect, mood_anchors[current_mood])
d_nearest = distance(affect, mood_anchors[nearest_mood])

# Switch only if nearest mood is closer by more than hysteresis margin:
if d_current - d_nearest > hysteresis_threshold:
    current_mood = nearest_mood
```

Stage 2 must define `hysteresis_threshold` (likely 0.05–0.15 in VA space). Too small → jitter returns. Too large → mood changes feel sluggish. The threshold may need to be asymmetric (easier to leave negative moods than to enter them, per guardrail philosophy).

#### Guardrail Integration

Guardrails from face comm spec §7 operate as hard constraints on the affect vector:
- **Duration limits**: if affect has been in a negative-mood region for > max_duration, inject a recovery impulse toward baseline.
- **Intensity caps**: clamp the projection intensity for negative moods (ANGRY cap 0.5, SCARED cap 0.6, etc.).
- **Context gate**: block negative-valence impulses when `conversation_active == False`.

Guardrails override the integrator output — they are the final safety net before face output.

### C.5 — Decision Boundaries and Emotional Authority

#### Single Source of Emotional Truth

The personality worker is the **final authority** on displayed emotion. All output channels (face, TTS prosody, LED) must use the worker's final affect → mood projection, not the LLM's raw suggestion. This prevents face/voice/text incoherence.

```
LLM suggests (emotion, intensity)
    → personality worker receives as impulse
    → affect vector updates
    → project(affect) → final (mood_id, intensity)
        → face: SET_STATE(final mood, final intensity)
        → TTS: prosody tag = final mood (not LLM's raw suggestion)
        → text: already generated by LLM (may slightly mismatch — acceptable)
```

**Architectural requirement**: The current pipeline sends TTS prosody from the AI worker's emotion directly. This must change — TTS prosody must route through the personality worker's final emotion decision. See PE-8 for integration options.

**Text mismatch**: The LLM generates text before the personality worker modulates the emotion. Minor text/face mismatch is acceptable (LLM says something mildly excited, face shows calm-positive). Hard mismatches (LLM text expresses fear, face shows happy) should be rare because the LLM's system prompt includes the personality profile.

#### Decision Boundaries

For each personality decision type, who makes it?

| Decision | Layer 0 (On-Device) | Layer 1 (Server LLM) | Integration |
|----------|-------------------|---------------------|-------------|
| Displayed emotion during conversation | Affect vector → mood projection (final authority) | Suggests (emotion, intensity) as impulse input | LLM impulse → affect vector → projection → face + TTS |
| Displayed emotion during idle | Full ownership (affect vector + idle rules) | None | Worker only |
| Proactive initiative | Timer/event triggers → impulse injection | Context-aware initiative (complex) | Layer 0 triggers simple initiative; Layer 1 adds contextual |
| Emotional memory updates | Store affective traces, apply decay | Provide semantic context for trace creation | Worker stores; LLM informs what to remember |
| Personality-consistent response text | None | Full ownership via system prompt | LLM only |
| Guardrail enforcement | Full ownership (hard constraints on affect vector) | None | Worker only |
| Failure transparency | Error events → THINKING impulse + recovery drift | LLM can generate "I'm not sure" text | Both — worker handles face, LLM handles text |
| Graceful degradation | Provides Layer 0 personality | N/A when unavailable | Worker handles |

### C.6 — Evaluation Framework

#### Baseline Controls

Every evaluation compares against defined baselines:

| Baseline | Description | Purpose |
|----------|------------|---------|
| **B0: Current system** | Qwen 2.5-3B, no personality worker, no modulation, no idle emotions | The "before" measurement — did we improve? |
| **B1: Random emotion** | Uniform random mood selection per turn, random idle emotions | The "worse than nothing" control — is personality better than random? |
| **B2: Layer 0 only** | On-device worker, no LLM personality, no server | The "floor" — how much personality survives without server? |

#### Test Types

| Test Type | What It Measures | Baseline | When to Run |
|-----------|------------------|----------|-------------|
| **Personality recognition** | Can observers identify consistent personality traits? | B0, B1 | After personality engine implemented |
| **Emotion appropriateness** | Are emotions contextually appropriate AND personality-consistent? | B0 | Per conversation test session |
| **Idle aliveness** | Does the robot seem "alive" between conversations? | B0 | Observation during idle periods |
| **Server degradation** | Does Layer 0 personality feel like the same robot? | B2 vs full | Simulated server outage |
| **Emotional arc coherence** | Does the affect vector trace a connected path in VA space? | B0, B1 | Logged session analysis |
| **Model comparison** | Does the selected LLM improve personality quality over Qwen 2.5-3B? | B0 | A/B testing via synthetic eval suite |
| **Over-personalization** | Does memory create uncomfortable behavior? | N/A | Observation + parent review |
| **Novelty sustainability** | Does personality still feel fresh after 2 weeks of daily use? | N/A | Longitudinal observation |

#### Emotional Arc Definition

An **emotional arc** is the trajectory of the affect vector through VA space during a single conversation session.

- **Connected path**: the affect vector should trace a continuous path, not random jumps. Measured by average step distance in VA space between consecutive turns (lower = more connected).
- **Oscillation**: arcs may oscillate (conversations aren't monotonic). A sad topic followed by a joke followed by a serious question is a natural oscillation.
- **Causality**: affect vector changes should be traceable to conversation events (impulses from LLM emotions or system events). Unmotivated changes indicate personality failure.
- **Duration**: arc is per-session. Cross-session arcs are a property of emotional memory, not individual arcs.
- **Metrics**:
  - **Arc coherence ratio**: total path length / maximum displacement from baseline. A purposeful conversation pushes the affect vector outward and returns smoothly (low ratio, ~2-5). Random LLM noise produces a random walk (high ratio, >>10). A robot drifting in tiny circles near NEUTRAL has low average step distance but high coherence ratio — correctly flagged as incoherent.
  - **Arc smoothness**: average VA step distance between consecutive turns (lower = smoother). Catches single-turn mood whiplash.
  - **Arc range**: max VA distance traversed from baseline. Measures emotional expressiveness.
  - **Impulse-cause ratio**: % of affect changes attributable to a specific impulse event. Unmotivated drift should be near zero.

#### Parent Evaluation Protocol

For children ages 4-6, parent perception is a first-order constraint.

**Questions** (administered after first week of use, then monthly):
1. "Does the robot's emotional behavior seem appropriate for your child?" (1-5 scale)
2. "Does the robot feel like a consistent 'character' across different interactions?" (1-5 scale)
3. "Has the robot ever made your child uncomfortable or upset through its emotional expressions?" (yes/no + describe)
4. "Does your child seem overly attached to the robot? (e.g., distressed when robot is off, preferring robot over human interaction)" (yes/no + describe)
5. "Has your child mentioned the robot 'feeling' or 'thinking' things? If so, what?" (open-ended — measures anthropomorphism level)

**Thresholds**:
- Any report of child distress attributed to robot emotional expression → immediate review and adjustment
- Any report of unhealthy attachment patterns → reduce personality expressiveness, increase idle-to-neutral frequency
- These are hard constraints, not tuning parameters — safety overrides personality quality

#### Evidence Classification

Same as face comm spec:
- **[Empirical]**: Backed by published experimental results
- **[Theory]**: Backed by widely accepted framework
- **[Inference]**: Speculative extrapolation — must be validated in testing

---

## D) Decision Points Requiring User Input

### Decision Criticality Classification

| Class | Meaning | Examples |
|-------|---------|---------|
| **Architectural** | Changes data model, worker design, or server integration. Hard to reverse after implementation. | PE-1, PE-2, PE-6, PE-7 |
| **Structural** | Changes which code modules do what. Medium effort to revise. | PE-8, PE-9 |
| **Behavioral** | Changes personality behavior within existing architecture. Moderate effort. | PE-3, PE-4, PE-5 |
| **Tuning** | Changes parameter values. Cheap to iterate. | PE-10 |

### Comparison Dimensions

Each option is evaluated on four axes:
- **Eng. complexity**: Implementation and ongoing maintenance burden
- **Personality quality**: How well it produces recognizable, consistent personality
- **Failure mode risk**: What goes wrong and how badly
- **Server resilience**: How well personality functions without or with degraded server

Decisions are presented in two groups: Phase 1 (ideal system) first, Phase 2 (technology) second.

---

### Phase 1 Decisions: Ideal Personality System

---

### PE-1. Trait-to-Affect-Vector Parametrization — ARCHITECTURAL

How do the 5 personality axis positions (§C.3) parametrize the continuous affect vector model (§C.4)?

The computational abstraction is decided: a continuous affect vector (valence, arousal) with decaying integrator. This decision is about *how personality traits map to affect vector parameters* — the parametrization method.

**Option A — Direct parametrization**

Each axis position maps directly to a continuous affect vector parameter via a mapping function. E.g., Energy(0.40) → baseline_arousal = f(0.40) = -0.1. Reactivity(0.50) → decay_rate = g(0.50) = 0.3/s. All personality behavior emerges from the integrator dynamics — no explicit behavioral rules.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — requires designing mapping functions, tuning parameter curves |
| Personality quality | High — produces smooth, continuous personality variation. All personality is a natural consequence of integrator dynamics |
| Failure mode risk | Hard to predict emergent behavior from parameter interactions. May produce counterintuitive results (e.g., certain parameter combinations never reach some moods) |
| Server resilience | Good — all parameters are on-device |

**Option B — Rule-gated parametrization**

Axis positions define thresholds that trigger discrete behavioral rules. Rules inject impulses into the affect vector. E.g., "IF idle > 5 min AND Energy < 0.5 THEN inject SLEEPY impulse." "IF conversation_end AND Vulnerability < 0.4 THEN suppress negative-valence impulses." Axes don't set continuous parameters — they configure rule triggers.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — each rule is simple and independently testable |
| Personality quality | Medium — personality is recognizable but feels discrete/mechanical. Behavior changes at axis thresholds, not gradually |
| Failure mode risk | Rules may conflict; coverage gaps (situations with no applicable rule → no personality impulse). Threshold sensitivity — small axis changes can flip rules on/off |
| Server resilience | Excellent — all rules are on-device |

**Option C — Hybrid (continuous parameters + rule triggers)**

Axes set both continuous parameters (baseline, decay rate, impulse scaling, bounds) AND define rule triggers for specific behavioral patterns (idle transitions, initiative triggers, guardrail thresholds). The integrator provides the continuous substrate; rules handle discrete events that the integrator alone can't express.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — two mechanisms, but each is simple with a clear boundary (continuous dynamics vs event-triggered behavior) |
| Personality quality | High — smooth baseline behavior from continuous parameters, appropriate discrete responses from rules |
| Failure mode risk | Lower than A or B alone — integrator prevents gaps, rules prevent emergent surprises. Need clear separation of what's continuous vs rule-based |
| Server resilience | Good — both mechanisms are on-device |

**Open questions**: Does Moshkina & Arkin's TAME architecture (2005) provide validated mappings from Big Five traits to affect vector parameters? How did Breazeal (2003) parametrize Kismet's emotion model? Which mapping functions (linear, sigmoid, piecewise) produce the most natural-feeling personality variation?

---

### PE-2. Emotional Memory Scope — ARCHITECTURAL

What emotional context does the personality system remember, and for how long?

**Option A — Stateless**

No memory. Each conversation turn is emotionally independent (current behavior). Personality is temperament-only (baseline bias).

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no state to manage |
| Personality quality | Low — no emotional inertia, no relationship continuity |
| Failure mode risk | Lowest — nothing to corrupt, leak, or over-personalize |
| Server resilience | N/A — nothing to lose |

**Option B — Session-scoped memory**

Remember emotional context within a single conversation session. Clear on session end. E.g., "child was sad at turn 3 → maintain empathetic undertone through turn 8."

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — in-memory state, cleared on session end |
| Personality quality | Medium — emotional arcs within conversation, but every session starts fresh |
| Failure mode risk | Low — state is short-lived, auto-clears |
| Server resilience | Good — worker can maintain session memory locally |

**Option C — Persistent memory (across sessions)**

Remember emotional context and interaction patterns across sessions. File-backed or database. E.g., "this child loves dinosaurs → show CURIOUS when they approach."

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — persistent storage, data model, cleanup policies, privacy considerations |
| Personality quality | Highest — true relationship continuity, the robot "knows" the child |
| Failure mode risk | Significant — stale data, privacy concerns, over-personalization, data corruption, storage limits. See regulatory and attachment risks below. |
| Server resilience | Good for stored data — but new memories require server (LLM must understand conversation to identify what to remember) |

**Regulatory risk (hard constraint)**: Persistent emotional interaction data for children ages 4-6 falls under COPPA (US) and EU AI Act provisions for high-risk AI systems involving minors. Sending persistent emotional data to a cloud LLM is legally precarious. If Option C is chosen, data must be strictly local and on-device — never transmitted to the server. The server receives only anonymized semantic tags (e.g., `likes_dinosaurs=true`), never raw emotional logs or conversation transcripts.

**Uncanny recall risk**: From an attachment theory perspective, perfect recall in a machine can trigger relationship uncanny valley. If the robot accurately references a passing comment from three weeks ago, it may feel more unnerving than endearing to both child and parent. Any persistent memory must have visible decay — the robot should "vaguely remember" rather than "perfectly recall."

**If Option C proceeds**: define it strictly as local, on-device semantic tags with mandatory decay, decoupled from raw emotional conversation logs. Bucket 0 research must confirm this is ethically and legally viable before committing.

**Open questions**: What do longitudinal HRI studies (Kanda et al., 2004; Leite et al., 2014) identify as the most impactful types of cross-session memory? Is simple topic tracking sufficient, or does relationship quality require deeper semantic memory? Does Bucket 0 research eliminate Option C on legal/ethical grounds, or can constrained local-only memory satisfy both COPPA and attachment safety?

---

### PE-3. Idle Emotional Behavior — BEHAVIORAL

Should the robot show emotions when not in conversation?

**Option A — Rule-based deterministic**

Fixed rules map system state to idle emotions. E.g., idle > 5 min → SLEEPY @ 0.3. Just booted → CURIOUS @ 0.4. Low battery → SAD @ 0.2. Rules are simple, predictable, debuggable.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — small rule set in personality worker |
| Personality quality | Medium — robot shows "signs of life" but patterns become predictable |
| Failure mode risk | Low — rules are conservative, easy to test |
| Server resilience | Excellent — fully on-device |

**Option B — Temperament-biased stochastic**

Personality axes bias a probability distribution over idle moods. Higher Energy → more CURIOUS/EXCITED idle moods. Lower Energy → more SLEEPY/NEUTRAL. Random selection with personality-weighted probabilities.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — probability tables, random sampling, bias computation |
| Personality quality | Higher — idle behavior feels more "alive" and less mechanical |
| Failure mode risk | Medium — random element could produce surprising moods that seem unmotivated |
| Server resilience | Excellent — fully on-device |

**Option C — No idle emotions (current)**

Robot stays NEUTRAL during idle. Only shows emotions during conversation or planner actions.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no change |
| Personality quality | Lowest — robot appears "dead" between interactions |
| Failure mode risk | Lowest |
| Server resilience | N/A |

**Open questions**: Do children notice or care about idle emotional behavior? At what frequency does idle mood change become distracting? Does our Social Initiative axis (0.30 = mostly passive) conflict with visible idle emotions?

---

### PE-4. Per-Child Adaptation — BEHAVIORAL

Should the personality adapt to individual children?

**Option A — Fixed personality**

Same personality for all children, all sessions, forever. Consistent and predictable. The robot is "the same person" to everyone.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no adaptation logic |
| Personality quality | Medium — consistent but doesn't build individual relationships |
| Failure mode risk | Lowest — no adaptation to go wrong |
| Server resilience | Full — personality is static |

**Option B — Per-child profiles**

Different children get different personality tuning. Requires voice ID or face ID to identify the child. E.g., a shy child gets lower Energy, higher Vulnerability display.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Highest — voice/face ID, profile storage, adaptation rules |
| Personality quality | Potentially highest — personalized relationships |
| Failure mode risk | High — wrong child ID → wrong personality. Profile drift. Privacy concerns with biometric data. |
| Server resilience | Moderate — profiles stored on-device, but adaptation rules may need LLM |

**Option C — Slowly evolving (same for all)**

Personality starts at defined axis positions and slowly shifts over weeks/months based on aggregate interaction patterns. Not per-child, but not static.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — slow drift rules, bounded evolution |
| Personality quality | Medium-high — personality feels like it "grows" |
| Failure mode risk | Medium — drift could move personality to undesirable state. Need bounds and reset capability. |
| Server resilience | Good — drift state stored on-device |

**Open questions**: Voice ID is listed in `docs/TODO.md` as a future idea. Is it a prerequisite for per-child adaptation, or can simpler signals (time of day, interaction frequency) serve as proxies? What does Tapus & Matarić (2008) find about the effectiveness of personality matching?

---

### PE-5. Initiative Frequency — BEHAVIORAL

How often does the robot proactively express emotions without external stimulus?

**Option A — Never proactive (current)**

Robot only emotes in response to planner commands or AI conversation. Silent and neutral otherwise.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no change |
| Personality quality | Low — robot feels reactive-only |
| Failure mode risk | Lowest |
| Server resilience | N/A |

**Option B — Rare (1-2 per session)**

Robot occasionally shows unsolicited emotion. E.g., curious head tilt after 30 seconds of child proximity without conversation. Happy wiggle after a long successful conversation ends.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — few triggers, simple rules |
| Personality quality | Medium-high — robot seems to have "inner life" without being overwhelming |
| Failure mode risk | Low — rare enough that mistakes are not patterns |
| Server resilience | Good — triggers can be on-device |

**Option C — Context-triggered (specific events only)**

Robot emotes proactively only in response to specific events: boot, low battery, long idle, session end, error recovery. Not random, not frequent, but connected to real system events.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — event detection, context-appropriate emotion selection |
| Personality quality | High — proactive emotions feel motivated and intentional |
| Failure mode risk | Medium — need to ensure events are reliable, emotions are appropriate |
| Server resilience | Excellent — system events are on-device |

**Open questions**: How does our Social Initiative axis (0.30) translate to a concrete frequency? Does Serholt & Barendregt (2016) quantify the "annoying" threshold for robot initiative?

---

### Phase 2 Decisions: Technology & Implementation

---

### PE-6. Server LLM Model — ARCHITECTURAL

What LLM model should power the server-side personality?

**Option A — Keep Qwen 2.5-3B**

No model change. Focus personality effort entirely on the on-device worker and better prompting.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no infrastructure change |
| Personality quality | Low — 3B model cannot reliably follow personality constraints or produce consistent emotional reasoning |
| Failure mode risk | Current failure modes persist (emotion randomness, schema violations) |
| Server resilience | N/A (already baseline) |

**Option B — Upgrade to 7B/14B quantized (same family or new)**

Replace Qwen 2.5-3B with a larger model using 4-bit quantization to fit within the same VRAM budget (~8.4 GB). Candidates: Qwen 2.5-14B-AWQ, Llama 3.1-8B, Gemma 2-9B, Phi-3-14B.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low-medium — model swap in vLLM config, may need prompt adjustments |
| Personality quality | Significantly higher — larger models show much better persona consistency and structured output compliance |
| Failure mode risk | Quantization may degrade quality on edge cases; inference latency may increase |
| Server resilience | Same as current — server-dependent |

**Option C — Switch to a different architecture (e.g., model with native function calling)**

Choose a model specifically optimized for structured output and persona (e.g., a model fine-tuned for character role-play or emotion reasoning).

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium-high — may require prompt rewrite, output parsing changes |
| Personality quality | Potentially highest — specialized model for the task |
| Failure mode risk | Less community support, less tested, may have unexpected failure modes |
| Server resilience | Same as current — server-dependent |

**Open questions**: What is the actual VRAM usage of Qwen 2.5-14B at 4-bit quantization? Can it coexist with Orpheus? Which models score highest on persona consistency benchmarks? Is there a model that's specifically good at emotion reasoning?

---

### PE-7. On-Device Inference — ARCHITECTURAL

Should the Pi 5 run any ML model for personality?

**Hard constraints** (must be met for any on-device inference option):
- Max inference latency: **< 200 ms** per personality decision (personality updates at ~1 Hz, not latency-critical)
- CPU headroom: Pi 5 simultaneously runs supervisor tick loop (50 Hz), Whisper STT (variable, CPU-intensive during speech), wake word detector (continuous). Personality inference must not cause tick overruns or STT quality degradation.
- Thermal budget: Pi 5 throttles at 85°C. Sustained inference may push thermals beyond safe operating range.
- Memory: ~4 GB available after OS and supervisor. A 1.5B model at 4-bit quantization ≈ 1 GB RAM. Feasible in memory but CPU cost is the constraint.
- **Recommendation**: Add a "spike" task to the implementation plan — benchmark Pi 5 inference (latency, CPU%, thermal) before committing to PE-7 Option B.

**Option A — No on-device inference**

Personality worker is pure rules and the decaying integrator. No ML model on Pi 5. All intelligence comes from the server via Layer 1 impulses.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — no model deployment on Pi |
| Personality quality | Dependent on server — Layer 1 when available, Layer 0 when not |
| Failure mode risk | Lowest — no model to fail |
| Server resilience | Layer 0 personality only when server down |

**Option B — Tiny model for personality-only inference**

Run a small model (1-3B, quantized) on Pi 5 for personality decisions only (context-aware impulse generation, idle mood reasoning). Not for text generation. Must meet hard constraints above.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | High — model deployment, ONNX/llama.cpp setup, CPU budget management, thermal monitoring |
| Personality quality | Potentially higher — local inference for richer Layer 0 personality even without server |
| Failure mode risk | High — Pi 5 CPU contention may degrade STT or tick loop. Unknown until benchmarked. |
| Server resilience | Good — personality has local intelligence even without server |

**Option C — Deterministic rules only (no ML)**

Same as Option A but explicitly designed so Layer 0 (rules + decaying integrator) is comprehensive enough to feel like a complete personality. Rules cover all personality scenarios with trait-parameterized behavior.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — must design comprehensive rule set covering all event types |
| Personality quality | Medium — predictable, consistent, but lacks contextual nuance |
| Failure mode risk | Low — deterministic, debuggable, no resource contention |
| Server resilience | Excellent — full (rules-based) personality without server |

**Open questions**: What is the actual CPU cost of running a 1.5B quantized model on Pi 5? What personality decisions actually benefit from ML vs the decaying integrator + rules? Is the quality improvement worth the complexity and resource risk?

---

### PE-8. LLM Integration Method — STRUCTURAL

How does the personality engine integrate with the server LLM?

**Constraint from §C.5**: The personality worker is the single source of emotional truth. Both face SET_STATE and TTS prosody must use the worker's final mood projection. All options below must satisfy this constraint — the question is *how* the LLM's emotion suggestion becomes an impulse and how the final emotion routes to all output channels.

**Option A — Prompt injection only (LLM-trusted)**

Personality worker sends a personality profile to the server, which injects it into the LLM system prompt. LLM is responsible for following the personality. The worker receives the LLM's emotion suggestion as an impulse but applies minimal modulation — trusting the LLM to be personality-consistent. TTS prosody uses the worker's final projection (may differ from LLM suggestion only due to integrator dynamics).

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — modify system prompt, add TTS routing through worker. No modulation logic. |
| Personality quality | Dependent on LLM quality — good model follows prompt, weak model ignores it |
| Failure mode risk | LLM may ignore personality constraints (seen with Qwen 2.5-3B). Integrator dynamics alone may not sufficiently correct bad LLM emotion choices. |
| Server resilience | When server is down, only Layer 0 impulses reach the integrator — personality still works but without language-aware emotion. |

**Option B — Output modulation (personality worker filters AI emotions)**

LLM produces emotions freely. Personality worker treats them as raw impulses and applies active modulation before the affect vector update: scales magnitude by axis-derived weights, attenuates negative-valence impulses per Vulnerability, caps arousal per Energy. Face and TTS both use the worker's final projection after modulation.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — modulation functions in personality worker, TTS routing change |
| Personality quality | Medium — personality applied post-hoc. Text is already generated before modulation, so text/face minor mismatch possible (text says excited, face shows calm-positive). |
| Failure mode risk | Text/face/voice mismatch. But face and voice always agree (both from worker's projection). Text is the outlier, and minor text/face mismatch is less jarring than face/voice mismatch. |
| Server resilience | Good — modulation provides personality even when LLM ignores prompt |

**Option C — Both (prompt + modulation)**

Personality profile injected in prompt (LLM tries to be personality-consistent) AND personality worker modulates the LLM's emotion suggestion before affect vector update (safety net). Both channels push toward the same personality. Face and TTS use worker's final projection.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — both prompt engineering and modulation logic, plus TTS routing |
| Personality quality | Highest — LLM aims for personality (reducing text mismatch), worker ensures it (modulating face + voice). Two layers of personality enforcement. |
| Failure mode risk | Double-filtering could over-dampen emotions (LLM already restrains, worker restrains further → flat affect). Tuning needed to avoid this. |
| Server resilience | Good — modulation provides meaningful personality even when LLM ignores prompt |

**Open questions**: How severe is the text/face mismatch problem in practice? The integrator's continuous dynamics may smooth over most mismatches. Should modulation be soft (scale impulse magnitude) or hard (veto and replace with a different impulse)? Does double-filtering in Option C produce measurably over-dampened affect compared to Option B?

**Dependency on PE-9**: PE-8 defines the *communication protocol* (how LLM suggestions become impulses). PE-9 defines *responsibility allocation* (who owns which personality behaviors). These are related but not identical — a PE-8 choice constrains but does not determine PE-9. For example, PE-8 Option C (prompt + modulation) is compatible with PE-9 Option A (minimal server) or PE-9 Option C (balanced split). Resolve PE-8 first, then PE-9 within the constraints PE-8 establishes.

---

### PE-9. Device/Server Boundary — STRUCTURAL

Where exactly is the line between on-device and server personality?

**Constrained by PE-8**: The integration method chosen in PE-8 determines how much the server participates in emotion decisions. PE-9 extends this to *all* personality behaviors (idle, memory, initiative, guardrails), not just emotion modulation. See PE-8 dependency note.

**Option A — Minimal server (most logic on-device)**

Server LLM just generates text and suggests an emotion. All personality logic lives in the on-device worker: emotion modulation, memory, idle behavior, initiative, guardrails. Server gets a thin personality prompt but personality worker makes all final decisions.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium-high — comprehensive on-device engine |
| Personality quality | Medium — personality is consistent but lacks contextual intelligence for emotion selection |
| Failure mode risk | Emotion mismatch risk (LLM text implies excitement but worker forces calm) |
| Server resilience | Excellent — personality fully on-device |

**Option B — Minimal device (most logic in LLM)**

Personality worker is thin: just maintains idle state and enforces guardrails. LLM handles all emotion selection, memory, and personality consistency via system prompt.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lower on device, higher on prompt engineering |
| Personality quality | Dependent on LLM — high with good model, terrible with weak model |
| Failure mode risk | Server failure → almost no personality. LLM inconsistency → personality drift. |
| Server resilience | Poor — personality collapses without server |

**Option C — Balanced split**

On-device worker handles: temperament, idle behavior, guardrails, emotion modulation (safety net). Server handles: emotion selection, text generation, conversational memory context. Worker and server share a personality profile. Worker modulates server output but doesn't override unless guardrails are violated.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — both sides have clear, bounded responsibilities |
| Personality quality | High — intelligence where it matters (server), reliability where it's needed (device) |
| Failure mode risk | Coordination complexity — both sides must agree on personality state |
| Server resilience | Good — on-device provides meaningful personality; server enhances it |

**Open questions**: What percentage of personality decisions are contextual (need LLM) vs structural (can be rules)? Can we quantify the quality difference between server-up and server-down personality?

---

### PE-10. Worker Update Rate — TUNING

How often does the personality worker emit state updates?

**Option A — 1 Hz periodic**

Personality worker emits a snapshot every second, regardless of events. Tick loop reads the latest snapshot.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Lowest — simple timer loop |
| Personality quality | Good — 1 Hz is fast enough for mood changes (moods hold for 500ms+ per spec) |
| Failure mode risk | May miss rapid events (burst of AI emotions within 1 second) |
| Server resilience | N/A |

**Option B — Event-driven**

Personality worker emits a snapshot only when something changes: new AI emotion, conversation state transition, idle mood shift, guardrail trigger.

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Medium — must track "dirty" state, emit on change |
| Personality quality | Identical to A — just different timing |
| Failure mode risk | Subtle bugs: forgetting to emit after a state change → stale personality |
| Server resilience | N/A |

**Option C — Hybrid (1 Hz + event triggers)**

Baseline 1 Hz heartbeat plus immediate emission on high-priority events (conversation state change, guardrail trigger).

| Dimension | Assessment |
|-----------|-----------|
| Eng. complexity | Low — 1 Hz timer + event hooks |
| Personality quality | Best — responsive to important events, no stale state |
| Failure mode risk | Lowest — heartbeat catches anything events miss |
| Server resilience | N/A |

**Open questions**: Is 1 Hz fast enough for emotion modulation during conversation? The AI worker emits emotions at ~1 per TTS chunk — is there a timing dependency?

---

## E) Approved Decisions

### Phase 1 Decisions (Ideal System)

#### PE-1: Trait-to-Affect-Vector Parametrization — Option C (Hybrid)

**Decision**: Continuous parameters + rule triggers, with toggleable guardrail rules as a mandatory rule category.

Personality axes set both continuous affect vector parameters (baseline position, decay rate, impulse scaling, bounds via sigmoid/linear mapping) AND define rule triggers for discrete behavioral patterns (idle transitions, boot behavior, initiative triggers, guardrail enforcement). The decaying integrator provides the continuous substrate; rules handle events the integrator alone can't express.

**Guardrail rules are mandatory but toggleable**: HC-1 through HC-10 and RS-1 through RS-10 are implemented as rules in the personality worker. They are active by default and can be individually toggled for development, testing, and tuning — but ship with all guardrails enabled. The toggle mechanism allows experimentation during development without removing safety infrastructure.

**Evidence basis**: TAME validates multilayer trait → mood → emotion separation (Bucket 1). Kismet's homeostatic drives require event triggers (Bucket 1). Idle behavior catalog is inherently rule-triggered (Bucket 4). Sigmoid mapping for continuous parameters prevents caricature at extremes (Bucket 1, WASABI).

#### PE-2: Emotional Memory Scope — Option C (Persistent)

**Decision**: Persistent cross-session memory with configurable constraints that can be added or removed.

The personality engine stores emotional context and interaction patterns across sessions. The constraint system is modular — individual constraints (decay rates, retention limits, data categories, consent gates) can be added, removed, or adjusted without changing the memory architecture itself.

**Minimum viable memory**: Child's name (never decays), 1-2 favorite topics (2-4 week half-life), shared rituals (months), last session's emotional tone (1-2 week half-life), session count (never decays). Stored as local-only semantic tags, never raw emotional logs or conversation transcripts.

**Configurable constraints** (shipped with defaults, adjustable):
- Decay rates per memory tier (adjustable half-lives)
- Retention limits per data category
- Recall framing (approximate by default: "I think we talked about...")
- Consent gate (parental consent required before persistent storage activates)
- Data viewer and deletion (parent dashboard integration)
- COPPA-compliant retention policy (written, explicit)

**Constraint toggle philosophy**: Same as PE-1 guardrails — constraints ship enabled with safe defaults. They can be individually adjusted for tuning, tightened for stricter deployments, or loosened for research/testing. The memory system itself is constraint-agnostic; policy is layered on top.

**Evidence basis**: Ligthart et al. (2022) — memory personalization keeps children engaged across sessions (Bucket 2). Kanda et al. (2004) — personal remarks increase engagement duration (Bucket 3). Shared rituals require cross-session memory by definition (Bucket 3). COPPA and EU AI Act impose constraints but do not prohibit local-only semantic memory with consent (Bucket 0).

#### PE-3: Idle Emotional Behavior — Option A (Deterministic Rules) + Integrator Noise

**Decision**: Rule-based deterministic idle behavior with stochastic variation from the Predictability axis (25% noise amplitude).

The idle behavior catalog (Bucket 4, §3.3) provides the deterministic backbone: system events → impulses, time-based thresholds → impulses (with Gaussian jitter from Predictability axis), temperament baseline → continuous decay target. The Predictability axis (0.75) adds cosmetic variation — 25% noise amplitude on idle impulse timing, intensity, and mood variant selection. No separate stochastic module needed; the integrator + noise IS the stochastic element.

**HC-5/HC-10 baked in**: No loneliness/abandonment expressions during idle (HC-5). No negative emotions during idle — context gate from face comm spec §7.3 is a red line (HC-10). Idle moods are self-contained (SLEEPY, CONTENT, NEUTRAL, CURIOUS), never socially directed.

**Evidence basis**: TAME baseline dominance when no stimuli present (Bucket 1). Kismet drive model produces perceived "aliveness" (Bucket 1). Children perceive pure determinism as "toy-like" — 25% noise produces "alive" (Bucket 4). Annoying threshold analysis confirms SI=0.30 is well below any risk (Bucket 4).

#### PE-4: Per-Child Adaptation — Option A (Fixed Personality)

**Decision**: Same personality for all children, all sessions. No per-child trait modification.

The robot is "the same person" to everyone. Personality axes are set at design time and do not change based on who is interacting. Content personalization (topics, rituals, greetings) comes from persistent memory (PE-2), not personality modification. The robot adapts *what it talks about*, not *who it is*.

**Evidence basis**: Engagement benefits attributed to "adaptation" come from content/ritual personalization, not personality trait modification (Bucket 3). Tapus & Matarić (2008) validated personality matching with adults only — unwarranted for 4-year-olds (Bucket 1). Children ages 4-6 benefit from consistency (Bucket 3). Per-child profiles introduce COPPA/biometric risk (Bucket 0 HC-2, HC-3).

#### PE-5: Initiative Frequency — Option C (Context-Triggered)

**Decision**: Proactive emotional expression tied exclusively to specific system events (boot, low battery, long idle, session end, error recovery, child approach). Not random, not time-based, not frequent.

At Social Initiative = 0.30: zero verbal proactive initiations per session. ~1-2 visible idle mood shifts per hour. Event-driven emotional responses (boot, battery, error) fire immediately regardless of frequency. Total proactive emotional displays: ~8-16 per day. All expression-only — no sound or attention-seeking.

**Context suppression rules**: Suppress all initiative when conversation is active, child affect is negative, session limit approaching, error state active, sleep hours configured, or within 2 minutes of conversation end. HC-5 compliant — initiative never includes emotional pulls.

**Evidence basis**: Chao & Thomaz (2014) — initiative doesn't increase perceived engagement; passive ≈ active at SI=0.30 (Bucket 4). Rivoire (2016) — context-grounded initiative is tolerable; context-irrelevant is annoying at any frequency (Bucket 4). Physical embodiment amplifies both benefit and risk of initiative — conservatism warranted (Bucket 4).

### Phase 2 Decisions (Technology & Implementation)

#### PE-6: Server LLM Model — Option B (Qwen3-8B AWQ 4-bit) with Clear Path to Option C

**Decision**: Upgrade from Qwen 2.5-3B to Qwen3-8B-Instruct-AWQ (4-bit quantization). This is the primary model. If personality quality evaluation proves insufficient, escalate to Qwen3-14B-AWQ with VRAM rebalancing (50% LLM / 30% TTS).

**Primary model (Qwen3-8B-AWQ)**:
- VRAM: ~4.6 GB weights + ~2.8 GB KV cache = ~7.4 GB total. Fits current 35% allocation (8.4 GB) with no TTS changes.
- Crosses the "7B threshold" — consistent capability jump identified across all model families for persona consistency, structured output, and multi-turn emotional reasoning (Bucket 5 §8.3).
- Hybrid thinking mode: chain-of-thought for complex emotional appraisal, fast direct mode for simple turns. Thinking tokens are internal — no output latency penalty on simple turns.
- Same tokenizer family as Qwen 2.5 — system prompts transfer with minimal adjustment.
- Expected improvements over Qwen 2.5-3B: JSON compliance ~70-80% → ~95%+ (with guided decoding: ~99%+), persona consistency poor → good (stable 20 turns), emotional reasoning keyword-driven → context-aware, constraint adherence 2-3 → 5-7+ simultaneous constraints.

**Escalation path to Option C (Qwen3-14B-AWQ)**:
- Trigger: Qwen3-8B fails to meet personality quality targets on the synthetic evaluation suite (Bucket 5 §5.6) — specifically JSON compliance <95% with guided decoding, persona drift KS >0.2 between conversations, or emotion-context fit avg <3.5.
- VRAM requirement: ~11.7 GB. Requires rebalancing to LLM 50% / TTS 30%.
- Prerequisites before rebalancing: (1) quantize Orpheus to INT8 and validate TTS prosody quality, (2) reduce TTS max_num_seqs from 8 to 2-4 and max_model_len from 8192 to 4096, (3) validate TTS quality under constrained allocation.
- This is a Phase 2 optimization path, not a Phase 1 architecture change. The personality worker and system prompt v2 are designed to work with any 7B+ model.

**Companion engineering change (model-independent)**: Enable vLLM guided JSON decoding with the Pydantic response schema. This eliminates JSON parse failures, removes `_extract_json_object()` and repair-suffix retry logic, and guarantees schema-valid output. Single highest-impact engineering change available — implement before or alongside model upgrade.

**Configuration changes for primary model**:
```
VLLM_MODEL_NAME=Qwen/Qwen3-8B-Instruct-AWQ
VLLM_DTYPE=auto
VLLM_GPU_MEMORY_UTILIZATION=0.35  # unchanged
VLLM_MAX_MODEL_LEN=4096           # unchanged
VLLM_MAX_NUM_SEQS=2               # unchanged
```

**Evidence basis**: 7B threshold validated across Qwen, Llama, Gemma, and Phi families — JSON compliance jumps +20-25%, MT-Bench roleplay +1.0 point, multi-turn consistency shifts from "drifts after 5-10 turns" to "stable for 15-20 turns" (Bucket 5 §8.3). CharacterEval confirms models below 7B show significant persona drift after 10+ turns (Bucket 5 §5.4). AWQ preferred over GPTQ for small-batch instruction-heavy workloads — activation-aware weight selection preserves instruction-following capability (Bucket 5 §3.4). Qwen3-8B IFEval ~78%, MT-Bench ~8.2, approaching Qwen 2.5-14B quality at half the parameters (Bucket 5 §8.1).

#### PE-7: On-Device Inference — Option C (Rules Only + Pluggable Interface)

**Decision**: No on-device LLM inference for initial implementation. Layer 0 personality is entirely rule-based (integrator + impulses + idle catalog + guardrails). The emotion classifier interface is designed as a pluggable abstraction so on-device inference can be spiked later without architectural changes.

**What this means**:
- The personality worker's `_classify_emotion()` method accepts input from either the rule engine or a local model — the interface is the same.
- Initial implementation: all emotion classification comes from rules (idle catalog, event-driven impulses, signal-level speech detection).
- Future spike: swap in Qwen3-1.7B at Q4_K_M via llama.cpp for emotion label scoring. Run as separate process at reduced nice priority. Only if Layer 0 quality proves insufficient in server-down testing.

**What Layer 0 rules provide** (fully validated by TAME research, Bucket 7 §1.4):
- Recognizable temperament (calm vs energetic) — high quality
- Idle emotional behavior (aliveness) — medium-high quality
- Emotional inertia (no mood whiplash) — high quality (mathematical)
- Event-driven emotion (boot, battery, error) — high quality
- Guardrail enforcement — high quality
- Memory-informed personalization (retrieve stored tags) — partial

**What Layer 0 rules cannot do** (requires LLM, Layer 1):
- Contextual emotion during conversation
- Personality-consistent response text
- Conversational emotional arc tracking
- Deep empathic mirroring (content-level, not just signal-level)

**Why not on-device inference now**: Pi 5 CPU contention with STT (60-90% during speech transcription) is a real risk — personality inference at 40-80% CPU would cause scheduling jitter on the 50 Hz tick loop (Bucket 5 §6.5). Thermal impact of sustained CPU inference on all 4 cores pushes SoC toward 70-75C, uncomfortably close to 85C throttle (Bucket 5 §6.5). The marginal quality gain of a 1.7B model for emotion classification is small once Layer 1 (7B+ server model) is strong (Bucket 5 §6.6).

**Evidence basis**: TAME participants distinguished personality traits from purely rule-parameterized behavior with no ML (Bucket 7 §1.1). Kismet's homeostatic drives produced idle "aliveness" with zero language understanding (Bucket 7 §1.2). Pi 5 Cortex-A76 generates ~15-25 tokens/sec at 1B Q4, but the critical question is CPU contention, not throughput (Bucket 5 §6.3). Layer 0 floor quality maps to Anki Vector's offline mode — acceptable for ages 4-6 for periods of minutes to hours (Bucket 7 §4.5).

#### PE-8: LLM Integration Method — Option C (Both: Prompt Injection + Output Modulation)

**Decision**: Personality constrains LLM behavior at the prompt level (system prompt v2 with personality profile, behavioral constraints, and few-shot examples) AND the personality worker modulates LLM emotion output through the affect vector integrator before it reaches the face. Double coverage from complementary angles.

**Prompt injection side** (guides LLM toward personality-consistent output):
- System prompt v2 skeleton (Bucket 6 §9): 7 sections, ~600 fixed tokens + ~100 per-turn dynamic profile.
- Personality constraints: emotion intensity caps per mood, transition rules, linguistic voice markers.
- Few-shot examples: 2-3 examples demonstrating personality-consistent emotion selection (highest-ROI prompt engineering intervention, 15-25% improvement in consistency — Bucket 6 §1.2).
- Dynamic personality profile: current mood, session context, memory tags — injected per-turn.
- Personality anchor: brief re-statement every 5 turns to prevent persona drift.

**Output modulation side** (personality worker corrects LLM errors):
- LLM emotion treated as impulse into affect vector, not as a command (Bucket 7 §6.2).
- Decision authority hierarchy: (1) Guardrails — never overridden, (2) Integrator dynamics — smooths everything, (3) Personality modulation — axis-derived scaling, (4) LLM suggestion — lowest priority.
- Schema v2 `mood_reason` field enables the worker to validate reasoning against personality constraints before applying impulse (e.g., catch "ANGRY because child disagreed" — personality-inconsistent).
- Schema v2 `inner_thought` field improves emotion selection at the source via structured chain-of-thought.

**Why both, not just one**: LLM emotional reasoning accuracy is ~55-65% at 7-14B on complex scenarios (EmoBench, Bucket 6 §8.1). Prompt engineering alone cannot compensate for the 35-45% error rate. Output modulation alone loses the benefit of the LLM knowing the personality — it would suggest emotions unconstrained by personality profile, producing more work for the worker to correct. Combined: the LLM produces better suggestions (prompt-guided), and the worker catches the remainder (integrator + guardrails). The LLM provides contextual reasoning the worker lacks; the worker provides consistency the LLM lacks.

**Evidence basis**: PersonaGym (2024) — prompt design matters as much as model size for persona adherence; well-structured prompts with behavioral rules outperform trait descriptions (Bucket 6 §1.1). Tam et al. (2024) — constrained generation slightly degrades semantic quality, mitigated by inner_thought reasoning field (Bucket 6 §2.2). EmoBench — even 70B+ models struggle with nuanced emotional reasoning; smaller models default to "safe" positive emotions (Bucket 6 §8.1). RLHF alignment partially helps (suppresses dangerous emotions) and partially hurts (suppresses personality-consistent mild negative emotions) — prompt must explicitly permit mild negative affect within bounds (Bucket 6 §8.3).

#### PE-9: Device/Server Boundary — Option C (Balanced Split)

**Decision**: Device owns the affect vector, temperament, rules, guardrails, and memory. Server provides context-aware impulses and personality-consistent text. Synchronization is one-way (device → server). Silent degradation — the robot never announces server issues to the child.

**Device owns (Pi 5 Personality Worker — always running, zero server dependency)**:
- Affect vector: sole writer of (valence, arousal). Decay computation, impulse application, bounds enforcement.
- Temperament baseline: static point in VA space derived from personality axes. Never changes.
- Idle behavior: full catalog from Bucket 4 (boot → CURIOUS, 5 min idle → SLEEPY drift, low battery → CONCERNED, error → THINKING, approach → arousal lift).
- Guardrails: HC-1 through HC-10, RS-1 through RS-10, face comm spec §7 duration caps and intensity limits.
- Initiative: context suppression rules, SI=0.30 frequency limits (PE-5).
- Memory: local semantic tag storage, decay management, tag retrieval for LLM profile.
- Mood projection: affect vector → (mood_id, intensity) with hysteresis threshold.
- Fast-path emotion: immediate arousal/valence shift from speech activity signals (<20 ms).
- Degradation management: detect server unavailability, maintain Layer 0, drift toward SLEEPY after extended offline (>4 hours).

**Server enhances (3090 Ti LLM — when available, not required)**:
- Context-aware emotion suggestion: understand conversation content → suggest (emotion, intensity) as impulse into affect vector.
- Personality-consistent text: system prompt v2 with personality profile → generate responses matching personality.
- TTS prosody: apply emotion tag from personality worker's final mood projection (not raw LLM output).
- Semantic memory creation: identify what to remember from conversation (personality worker stores it locally).
- Complex empathic reasoning: understand *why* the child is feeling a particular way (content-level, not just signal-level).

**Synchronization protocol**: One-way device → server via `personality.llm.profile` events.
- Full profile at conversation start (~1 KB): axis positions, current affect, current mood, session context, memory tags.
- Incremental affect updates at 1 Hz during conversation (~50 bytes): current_affect, current_mood, current_intensity.
- No server → device personality state pushes — avoids feedback loops. LLM emotion suggestions flow through the normal NDJSON event pipeline as impulses.

**Silent degradation strategy**:
- Normal → Slow (<500ms to 500ms-2s): Invisible. Integrator absorbs delay — Layer 0 impulses sustain face while LLM catches up.
- Slow → Timeout (>2s): Layer 0 only for conversation emotion. Robot feels "distracted" — acceptable.
- Timeout → Offline: Conversation capability lost. Personality continues through idle behavior. Robot drifts toward SLEEPY ("resting"), never says "I'm broken."
- Recovery: Smooth return over several turns, not binary switch.
- Dashboard: full server connectivity status visible to parents/caregivers. Degradation transparency is for adults, not children.

**Dual-path latency architecture**:
- Layer 0 fast path: speech detected → arousal lift impulse → face responds in <20 ms (one tick cycle).
- Layer 1 slow path: STT + LLM → emotion impulse → integrator adjusts → face transitions smoothly over 200-800 ms.
- Child perceives: immediate attentive reaction, followed by smooth transition to contextual emotion.
- Idle behavior: <30 ms from rule trigger to face (no server involved). Identical experience at Layer 0 and Layer 0+1.

**Evidence basis**: LeDoux (1996) dual-process emotion — fast subcortical appraisal (<100 ms) + slow cortical refinement (200+ ms). Our Layer 0/1 split mirrors this biologically grounded architecture (Bucket 7 §3.2). Anki Vector's silent degradation felt natural to users — "the robot was in a mood" rather than "broken" (Bucket 7 §4.3). Jibo's server-dependent architecture is the cautionary tale — when cloud died, the robot became non-functional (Bucket 7 §4.3). Layer 0 floor quality validated by TAME, Kismet, WASABI — recognizable personality from pure rules (Bucket 7 §1.4). Idle experience is identical at Layer 0 and Layer 0+1 — degradation primarily affects active conversation, which is the minority of robot uptime (Bucket 7 §6.3).

#### PE-10: Worker Update Rate — Option C (Hybrid: 1 Hz Baseline + Event-Triggered Fast Path)

**Decision**: The personality worker runs a 1 Hz main loop for steady-state computation plus immediate event-triggered processing for high-priority impulses.

**1 Hz baseline loop** handles:
- Integrator tick: decay affect vector toward temperament baseline using `1 - exp(-λ·dt)`.
- Idle rule evaluation: check timers against idle behavior catalog thresholds.
- Noise injection: Gaussian noise from Predictability axis.
- Periodic snapshot emission: `personality.state.snapshot` for tick loop consumption.
- Health heartbeat: `personality.status.health` per BaseWorker contract.

**Event-triggered fast path** handles (immediate, no wait for next 1 Hz tick):
- `personality.event.ai_emotion`: LLM emotion suggestion → impulse application → immediate snapshot emission.
- `personality.event.system_state`: boot, low battery, error → event-driven impulse → immediate snapshot.
- `personality.event.child_approach`: arousal lift → immediate snapshot.
- `personality.mood.override`: guardrail-triggered override → immediate snapshot.
- `personality.event.conv_started` / `conv_ended`: conversation state transition → immediate profile emission.

**Latency characteristics**:
- Idle (1 Hz only): affect vector updates every 1000 ms. Acceptable — idle behavior changes slowly.
- Conversation (event-triggered): emotion impulses processed in <1 ms, snapshot emitted immediately. Tick loop picks up new snapshot on next 50 Hz cycle (~20 ms worst case).
- Combined worst-case latency (event → face): ~22 ms (1 ms impulse processing + 20 ms tick cycle + 1 ms serial).
- CPU cost: ~0.5 ms per 1 Hz tick + ~0.1 ms per event. Negligible alongside STT and tick loop.

**Evidence basis**: WASABI runs at simulation-coupled rate (variable Hz) with event-triggered emotional impulses (Bucket 7 §1.3). TAME evaluates at < 1 ms per cycle — our 0.5 ms is comparable (Bucket 7 §1.1). The 1 Hz baseline matches the `personality.state.snapshot` emission rate specified in the plan file §C.1. Event-triggered emission closes the worst-case 1000 ms gap for urgent events to <22 ms (Bucket 7 §8.3).

---

## F) Next Steps

1. ~~Review this document for completeness and accuracy~~
2. ~~Resolve Phase 1 decisions (PE-1 through PE-5)~~ — **DONE**
3. ~~Conduct Phase 2 research (Buckets 5-7) — model evaluation, prompt engineering, device/server split~~ — **DONE**
4. ~~Resolve Phase 2 decisions (PE-6 through PE-10) — these define the technology~~ — **DONE**
5. Write Personality Engine Stage 2 (full implementation-ready spec)
6. Update face communication implementation plan to incorporate personality worker
