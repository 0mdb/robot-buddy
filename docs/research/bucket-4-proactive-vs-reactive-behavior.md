# Bucket 4: Proactive vs Reactive Behavior

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-3 (Idle Emotional Behavior) and PE-5 (Initiative Frequency) decisions

---

## Table of Contents

1. [Initiative Models in Social Robotics](#1-initiative-models-in-social-robotics)
2. [Over-Initiative Risk: The Annoying Threshold](#2-over-initiative-risk-the-annoying-threshold)
3. [Idle Emotional Behavior](#3-idle-emotional-behavior)
4. [Context Sensitivity and Initiative Suppression](#4-context-sensitivity-and-initiative-suppression)
5. [Initiative at Social Initiative = 0.30](#5-initiative-at-social-initiative--030)
6. [Proactive Behaviors Catalog](#6-proactive-behaviors-catalog)
7. [Design Recommendations](#7-design-recommendations)

---

## 1. Initiative Models in Social Robotics

### 1.1 Defining Proactive HRI

The most comprehensive taxonomy of proactive human-robot interaction comes from a 2024 ACM review (Zafari & Koeszegi, 2024), which identifies two main branches of robot proactivity:

1. **Anticipatory Robot Behavior** -- acting in advance of a future state or situation without explicit input from a human partner. The robot estimates or predicts hidden factors (human intent, upcoming needs, environmental changes) and acts preemptively. [Theory]

2. **Robot Initiative** -- the robot autonomously decides to start, redirect, or escalate an interaction. Unlike anticipation (which is about timing), initiative is about who controls the interaction flow. [Theory]

The term "proactively" can be a synonym for either "autonomously" or "in advance," but truly proactive behavior is intelligent and context-sensitive rather than merely automatic. A robot that speaks on a timer is automatic; a robot that notices the child seems disengaged and offers a gentle prompt is proactive. [Theory]

**Citation**: Zafari, S., & Koeszegi, S. T. (2024). What is Proactive Human-Robot Interaction? A Review of a Progressive Field and Its Definitions. *ACM Transactions on Human-Robot Interaction*, 13(3), 1-39.

### 1.2 Trigger Categories for Proactive Behavior

Based on the literature, proactive behavior triggers fall into four categories:

| Trigger Category | Description | Examples | Applicability to Our Robot |
|-----------------|-------------|----------|---------------------------|
| **Time-based** | Elapsed time since last event triggers action | Idle > 5 min --> SLEEPY; boot --> CURIOUS | High -- simple, deterministic, Layer 0 capable |
| **Context-based** | Environmental or system state triggers action | Low battery --> concern; error --> THINKING | High -- system events are reliable signals |
| **Social cue-based** | Detection of human social signals triggers action | Child approaches --> greeting; child looks away --> reduce expression | Medium -- requires perception (proximity sensor, camera) |
| **Need-based (homeostatic)** | Internal drives drift from equilibrium, triggering behavior to restore balance | Understimulated --> seek interaction; overstimulated --> withdraw | Medium -- maps well to our decaying integrator model |

[Inference -- taxonomy synthesized from Zafari & Koeszegi (2024), Breazeal (2003), and Sidner et al. (2005)]

### 1.3 Sidner et al. (2005): Engagement Model

Sidner, Lee, Kidd, Lesh, & Rich (2005) define **engagement** as "the process by which individuals in an interaction start, maintain, and end their perceived connection to one another." Their model identifies three phases:

1. **Engagement initiation** -- establishing mutual attention. The robot uses face-tracking and directed gaze to signal availability. People direct their attention to the robot more often when engagement gestures (face tracking, directed gaze, head nods) are present. [Empirical]

2. **Engagement maintenance** -- sustaining the connection through conversational turn-taking, gaze management, and responsive behavior. Participants found interactions "more appropriate" when engagement gestures were present vs. absent. [Empirical]

3. **Disengagement** -- ending the interaction. Occurs through offering to end, followed by farewell rituals, including the robot looking away from the user at close. [Empirical]

**Key finding for our design**: Engagement gestures are primarily about signaling attention and availability, not about proactive emotional expression. The robot does not need to *initiate* to show engagement -- it needs to *signal readiness* when the child is present. At Social Initiative 0.30, this means the robot should look alert and available without actively reaching out. [Inference]

**Design implication**: Engagement gestures (directed gaze, subtle animation) are distinct from proactive initiative (starting conversation, showing unsolicited emotion). Our robot should always do the former but rarely do the latter. [Inference]

**Citation**: Sidner, C. L., Lee, C., Kidd, C. D., Lesh, N., & Rich, C. (2005). Explorations in engagement for humans and robots. *Artificial Intelligence*, 166(1-2), 140-164.

### 1.4 Leite et al. (2013): Long-Term Interaction and Engagement

Leite, Martinho, & Paiva (2013) surveyed 24 long-term studies of human-robot interaction and identified a critical pattern: **long-term interaction begins when the novelty effect diminishes.** Before that point, any engagement metric is confounded by novelty. [Empirical]

Key findings relevant to initiative design:

- **Novelty drives initial engagement**, not personality or initiative. In the first few sessions, children are excited regardless of robot behavior. Proactive behaviors during this phase are redundant -- the child is already engaged. [Empirical]

- **After novelty fades** (typically 2-5 sessions for children), engagement depends on the robot's social capabilities: responsiveness, memory, emotional congruence, and adaptive behavior. This is when initiative starts to matter -- the robot needs to signal continued "aliveness" to prevent the child from losing interest. [Empirical]

- **Complex pro-social behavior** (attention-guiding, empathy display) sustains engagement better than simple reactive responses. But this must be context-appropriate to avoid irritation. [Empirical]

**Design implication**: Initiative behavior should be minimal in early sessions (novelty carries engagement) and can slightly increase after the child is familiar with the robot. This is compatible with PE-4 Option C (slowly evolving personality). [Inference]

**Citation**: Leite, I., Martinho, C., & Paiva, A. (2013). Social robots for long-term interaction: A survey. *International Journal of Social Robotics*, 5(2), 291-308.

### 1.5 Breazeal (2003): Kismet's Homeostatic Drive Model

Breazeal's Kismet (2003) provides the most directly relevant architectural precedent for autonomous emotional behavior. Kismet uses a **homeostatic drive system** where internal drives (social stimulation, fatigue, play) drift from equilibrium over time, and the robot generates behavior to restore balance. [Empirical]

Key behaviors:

- **Understimulated (no social interaction)** --> drive for social stimulation increases --> robot displays "sad" face to attract interaction, then "enthusiastic" face when someone approaches. [Empirical]

- **Overstimulated (too much input)** --> fatigue drive increases --> robot closes eyes and enters sleep mode to restore homeostatic balance. All drives are restored before awakening. [Empirical]

- **Seeking play** --> play drive increases --> robot displays interest/curiosity to invite engagement. [Empirical]

The drive system means Kismet is **never emotionally idle** -- it always has an internal state driven by the balance of needs, even when no one is interacting with it. This is the strongest precedent for PE-3 Option A (rule-based idle emotions) or Option B (temperament-biased stochastic). [Theory]

**Critical distinction for our design**: Kismet was designed to maximize social engagement -- it actively seeks interaction. Our robot at Social Initiative 0.30 should NOT actively seek interaction. But it CAN have homeostatic drives that produce idle emotional states (boredom, sleepiness) without generating attention-seeking behavior. The drives should influence expression but not generate outreach. [Inference]

**Warning**: Kismet's "sad face when understimulated" is specifically prohibited by our HC-5 constraint (no expressions of loneliness or abandonment when not in use). Our robot must express idle states as self-contained (SLEEPY, CONTENT, NEUTRAL) not as socially directed (lonely, missing you, wanting attention). [Inference -- constrained by Bucket 0 HC-5]

**Citation**: Breazeal, C. (2003). Emotion and sociable humanoid robots. *International Journal of Human-Computer Studies*, 59(1-2), 119-155.

---

## 2. Over-Initiative Risk: The Annoying Threshold

### 2.1 The Boring-Annoying Spectrum

Rivoire (2016) frames the core problem precisely: **a robot that is too passive is boring; a robot that is too proactive is annoying.** The optimal balance depends on:

- User schedule and habits (time-of-day patterns)
- Current activity context (busy vs. available)
- Interaction history (has the robot already spoken recently?)
- Ambient mood (user seems relaxed vs. stressed)

The study used Pepper robot in long-term home interactions and found that proactive utterances become tiresome unless they are **contextual and grounded in reality** -- a robot that randomly announces facts is annoying, but one that comments on something actually happening (weather change, time-based routine) is tolerated. [Empirical]

**Key finding**: The content of proactive utterances matters as much as their frequency. Context-irrelevant proactive behavior is perceived as annoying at *any* frequency. Context-relevant proactive behavior is tolerated at moderate frequency. [Empirical]

**Citation**: Rivoire, C. (2016). The delicate balance of boring and annoying: Learning proactive timing in long-term human robot interaction. *Proceedings of the ICMI Workshop on Designing Agents for Affect-Aware Interactions*.

### 2.2 Quantifying the Threshold

No single study provides a universal "annoying threshold" number, but converging evidence allows an estimate:

**Kanda et al. (2004)**: In a 2-month field trial with elementary school children, the Robovie robot introduced new interactive behaviors (handshakes, hugs, rock-paper-scissors, exercises, singing, pointing to objects) once total individual interaction duration surpassed 120 minutes. The robot increasingly made personal remarks at different time intervals (at 180+ minutes of cumulative interaction). With this graduated approach, the robot successfully maintained engagement across 32 sessions of 30 minutes each. [Empirical]

**Design inference**: New proactive behaviors should be introduced gradually, not all at once. A rate of approximately one new proactive behavior type per 2 hours of cumulative interaction appears sustainable. [Inference]

**Serholt & Barendregt (2016)**: In a 3-month field study with children grades 4-6, the robot tutor initiated socially significant events (questions, positive feedback, empathic responses). Children's social responses (gaze, verbal expressions, smiles, nods) **decreased slightly over time** but remained observable after three sessions. Gaze toward the robot's face was the most common response across all event types. [Empirical]

**Design inference**: Children habituate to robot-initiated events. The slight decrease is not a failure -- it reflects normalization. But it means proactive behaviors must evolve or vary to remain effective. Static proactive patterns will become invisible. [Inference]

**Chao & Thomaz (2014)**: When a robot took initiative in a collaborative learning task, humans responded significantly faster (1.30s vs 1.93s reaction time, p <= 0.005) and the interaction rhythm was faster (7.29s vs 9.52s between requests, p = 1.6e-5). However, subjective engagement ratings showed **no significant difference** between active and passive robot conditions (both rated ~4.0-4.5 on 5-point scales). [Empirical]

**Key insight**: Robot initiative increases interaction pace but not perceived engagement. For our robot at Social Initiative 0.30, this means being passive does NOT reduce perceived engagement. The child will not feel the robot is "less engaging" because it rarely initiates -- the subjective experience is similar. This validates a mostly-passive design. [Inference]

**Citation**:
- Kanda, T., Hirano, T., Eaton, D., & Ishiguro, H. (2004). Interactive robots as social partners and peer tutors for children: A field trial. *Human-Computer Interaction*, 19(1-2), 61-84.
- Serholt, S., & Barendregt, W. (2016). Robots tutoring children: Longitudinal evaluation of social engagement in child-robot interaction. *Proceedings of the 9th Nordic Conference on Human-Computer Interaction* (NordiCHI'16), Article 64.
- Chao, C., & Thomaz, A. L. (2014). Robot initiative in a team learning task increases the rhythm of interaction but not the perceived engagement. *Frontiers in Neurorobotics*, 8, Article 5.

### 2.3 Synthesized Annoying Threshold

Based on the converging evidence, I estimate the following thresholds for a child-facing companion robot:

| Initiative Type | Tolerable Frequency | Annoying Threshold | Evidence Basis |
|----------------|--------------------|--------------------|----------------|
| **Verbal proactive initiation** (robot starts talking unprompted) | 1-2 per session (15-20 min) | > 3 per session | Rivoire (2016), Kanda et al. (2004) |
| **Emotional expression change** (idle mood shift visible to child) | 2-4 per hour of idle time | > 1 per 5 minutes | Inference from habituation data |
| **Attention-getting behavior** (gestures, sounds to draw child's attention) | 0-1 per session at SI=0.30 | > 1 per session | Chao & Thomaz (2014), our SI constraint |
| **New behavior types introduced** | 1 per ~2 hours cumulative interaction | Faster than 1 per hour | Kanda et al. (2004) |
| **System-event emotional responses** (boot, low battery, error) | As events occur (not frequency-limited) | N/A -- tied to real events | Rivoire (2016) -- grounded in reality = tolerable |

[Inference -- synthesized from multiple sources, no single study provides these exact numbers]

**Critical note**: These thresholds apply to the child-facing output. Internal affect vector changes happen continuously (per the decaying integrator model) -- it is only the *visible* mood projection that should respect these frequency bounds. The hysteresis threshold (Personality Engine Spec C.4) already prevents rapid visible mood switching, which is the primary mechanism for enforcing these limits. [Inference]

---

## 3. Idle Emotional Behavior

### 3.1 Why Idle Behavior Matters

The question of whether a robot should show emotions when not in conversation is foundational to its perceived aliveness. Research converges on a clear answer: **yes, but subtly.**

**Idle motion is generally implemented by default on virtual characters to increase their behavioral realism or to make the character seem 'alive' in a neutral condition.** Robots that make idle motions like humans at the standby state make people feel they are alive and are more likely to interact with them. [Empirical -- from animation and HRI literature]

Idle behavior includes:
- Subtle postural variations (breathing animation)
- Eye movements and blinking
- Occasional gaze shifts
- Micro-movements

These are already handled by our face MCU (breathing, auto-blink, gaze wander in `face_state.cpp`). The question for the personality engine is whether *emotional content* should be added to idle -- not just cosmetic animation, but mood-carrying expression. [Inference]

**Citation**: IADIS International Journal on Computer Science and Information Systems (2020). Head Movements in the Idle Loop Animation. Vol. 15, No. 2.

### 3.2 Precedents: How Existing Systems Handle Idle Emotion

#### Kismet (Breazeal, 2003)
Kismet's homeostatic drives produce continuous emotional state even without interaction. When understimulated: sad --> seeking. When overstimulated: overwhelmed --> sleep. Drives ensure the robot always has an emotionally motivated internal state. This is the fullest implementation of emotional idle behavior. [Empirical]

**Problem for our design**: Kismet's understimulated behavior (sad face to attract interaction) violates HC-5 (no expressions of loneliness/abandonment). We must strip the social-seeking motivation while keeping the drive-based emotional variation. [Inference]

#### WASABI (Becker-Asano & Wachsmuth, 2010)
WASABI uses a valence-arousal model where all emotions decay toward neutrality over time. Mood is a "diffuse background state" influenced by accumulated emotional valence. When no events occur, the system decays toward neutral mood. WASABI does not generate autonomous idle emotions -- it simply fades. [Empirical]

**Problem for our design**: Pure decay-to-neutral produces the "dead idle" failure mode described in the personality engine spec. The robot appears off between interactions. We need something between Kismet (always emotionally active) and WASABI (always decaying to neutral). [Inference]

**Citation**: Becker-Asano, C., & Wachsmuth, I. (2010). WASABI: Affect simulation for agents with believable interactivity. *IEEE Transactions on Affective Computing*, 1(1), 10-24.

#### EMO Desktop Robot (Living.AI, consumer product)
The EMO robot provides a commercially validated precedent for idle emotional behavior in a consumer companion robot:
- **Napping when idle** -- simulates a life cycle of activity and rest
- **Self-entertaining with random dances** -- unprompted movement when alone
- **Displaying boredom** -- slumps and sighs when left alone, hoping you will play
- **Returning to charger** when low on battery -- practical need expressed as autonomous behavior
- **Over 1,000 different expressions and movements** -- substantial variation in idle behavior

**Problem for our design**: EMO's "bored, hoping you'll come play" behavior is another HC-5 violation -- it uses loneliness cues to drive engagement. But the napping, self-entertaining, and battery-seeking behaviors are appropriate precedents. [Inference]

**Citation**: Living.AI (2024). EMO Robot product documentation. https://living.ai/emo/

#### TAME Architecture (Moshkina & Arkin, 2005/2011)
The TAME (Traits, Attitudes, Moods, and Emotions) architecture provides the most directly applicable framework for personality-driven idle behavior. TAME uses the Big Five personality model to parameterize emotional dynamics:
- **Traits** are constant, operator-defined values that bias all emotional processing
- **Moods** are diffuse background states influenced by accumulated emotion and personality
- **Emotions** are short-term responses to specific stimuli that decay over time
- The input is perceptual information (stimuli categories and strengths) -- no stimuli means mood dominates expression

TAME explicitly separates trait-driven baseline (what the robot feels when nothing is happening, determined by personality) from stimulus-driven emotion (what the robot feels in response to events). This maps directly to our Layer 0 (trait-driven baseline + idle rules) vs. Layer 1 (stimulus-driven emotion from LLM). [Theory]

**Citation**: Moshkina, L., & Arkin, R. C. (2011). TAME: Time-varying affective response for humanoid robots. *International Journal of Social Robotics*, 3(3), 207-221.

### 3.3 Idle Behavior Catalog with Timing

Based on the research, here is a recommended catalog of idle emotional behaviors for our robot:

| Idle Event | Trigger | Target Mood | Intensity | Timing | Evidence |
|-----------|---------|-------------|-----------|--------|----------|
| **Boot/startup** | System boot complete | CURIOUS | 0.4-0.5 | Immediate, decays over 30-60s | Breazeal (2003) -- awakening from homeostatic reset produces exploratory state [Inference] |
| **Post-conversation warm** | Conversation session ends normally | Residual positive valence from conversation | 0.2-0.3 above baseline | Decays to baseline over 2-5 min | WASABI decay model -- emotion should not snap to neutral [Theory] |
| **Short idle** | 2-5 min since last interaction | Baseline (slightly positive CONTENT) | 0.2 | Sustained | TAME -- personality baseline dominates when no stimuli [Theory] |
| **Medium idle** | 5-15 min since last interaction | Drift toward SLEEPY | 0.2-0.3 | Gradual transition over 3-5 min | Kismet fatigue drive analogy; EMO napping behavior [Inference] |
| **Long idle** | 15+ min since last interaction | SLEEPY | 0.3-0.4 | Sustained; may enter display-dim mode | Energy conservation + perceived "resting" [Inference] |
| **Low battery** | Battery < 20% | Mild CONCERNED (not SAD) | 0.2-0.3 | Immediate on threshold cross | EMO battery-seeking; system event = grounded in reality [Inference] |
| **Critical battery** | Battery < 10% | SLEEPY (shutting down) | 0.4 | Immediate | Natural shutdown narrative [Inference] |
| **Error/fault** | System error, hardware fault | THINKING / mild CONFUSED | 0.3 | Immediate, hold until resolved | Personality spec failure transparency requirement [Inference] |
| **Child approaches** | Proximity detection / wake trigger | Shift from current idle toward NEUTRAL-alert | 0.1-0.2 lift in arousal | 500ms transition | Sidner (2005) -- engagement gestures signal availability [Empirical] |
| **Time-of-day** | Morning hours (first boot of day) | Slightly higher CURIOUS | 0.3 | First 5 min of day | Inference -- morning = fresh, higher energy baseline |
| **Time-of-day** | Evening hours | Slightly lower energy, drift to SLEEPY faster | -0.1 arousal modifier | Continuous modifier | Inference -- evening = wind-down |

**IMPORTANT**: None of these idle behaviors should generate attention-seeking output (sounds, movement toward child, verbal initiation). They are **expression-only** -- visible on the face if the child looks, but not designed to attract attention. This is the key distinction between idle emotional behavior (appropriate at SI=0.30) and proactive initiative (inappropriate at SI=0.30 except in rare cases). [Inference]

### 3.4 Deterministic Rules vs. Stochastic: The PE-3 Question

The personality engine spec poses PE-3 as a choice between deterministic rules (Option A), temperament-biased stochastic (Option B), and no idle emotions (Option C, rejected by research).

**Research recommendation: Hybrid -- deterministic structure with stochastic variation.**

Rationale:

1. **Deterministic rules provide the backbone.** The idle behavior catalog above (boot --> CURIOUS, idle > 5 min --> SLEEPY drift, low battery --> CONCERNED) should be deterministic. These are system-event-driven behaviors that must be reliable and debuggable. They form the Layer 0 foundation. [Inference]

2. **Stochastic variation prevents staleness.** With Predictability at 0.75, the robot reserves 0.25 for cosmetic variation. Within the deterministic framework, stochastic elements should control:
   - **Which** idle mood variant is chosen (e.g., CONTENT vs. mildly HAPPY during short idle -- sampled from personality-biased distribution)
   - **When** exactly a transition fires (e.g., SLEEPY onset at 5 min +/- 1.5 min, sampled from Gaussian)
   - **Gesture accompaniment** (which blink pattern, which micro-expression during idle)
   - **Intensity jitter** (+/- 0.05 around the target intensity)

3. **The affect vector naturally provides both.** The decaying integrator model already supports this hybrid: deterministic impulses (boot event --> CURIOUS impulse) combined with stochastic noise in the integration (Predictability axis controls noise amplitude at 0.25). The integrator IS the hybrid mechanism. No separate stochastic module is needed. [Inference]

**Implementation recommendation**: PE-3 should be Option A (rule-based deterministic) for the trigger/event structure, with the Predictability axis adding stochastic variation through affect vector noise. This is architecturally simpler than Option B (separate stochastic sampling) and produces equivalent or better results because the variation is unified through a single mechanism (the integrator). [Inference]

Evidence supporting stochastic variation:
- "By leveraging randomness in personality traits and non-deterministic actions, the robot develops the perception of independent thought, enhancing its human-like qualities." (Robot Character Generation, 2025) [Empirical]
- Children ages 4-6 expect robots to exhibit some unpredictability -- pure determinism reads as "toy-like" rather than "alive" (Preschoolers' Anthropomorphism, 2023). [Empirical]
- EMO robot uses over 1,000 expression variants for its idle behaviors -- variation is key to sustained perception of aliveness. [Empirical -- consumer product design]

---

## 4. Context Sensitivity and Initiative Suppression

### 4.1 When to Suppress Initiative Entirely

Not all moments are appropriate for proactive behavior. The literature identifies several contexts where robot initiative should be suppressed:

**A. Child is distressed or upset**

When negative emotion is detected in the child (through voice, conversation content, or caregiver indication), the robot should suppress playful or energetic proactive behaviors. Instead, it should:
- Pause current activity
- Shift to empathic mirroring or calm neutral
- Wait for the child to initiate

"The nature of a social robot's empathic response depends on its relationship with the human target and the situational context of interaction. A robot may calibrate the strength of an empathic response or even decide not to express one." (Leite, Pereira, Mascarenhas, Martinho, Prada, & Paiva, 2013) [Theory]

**Design rule**: When the LLM detects negative child affect (Layer 1 signal), suppress all proactive impulses and shift the affect vector decay target to calm-empathic baseline rather than temperament baseline. This is a Layer 1 override of Layer 0 idle behavior. [Inference]

**B. Conversation is active**

During active conversation, idle emotional behaviors are irrelevant -- the LLM drives emotion through Layer 1 impulses. Idle behavior rules should be suspended when `conversation_active == True`. [Inference]

**Design rule**: Guard all idle behavior triggers with `if not conversation_active`. The decaying integrator continues running, but idle impulses are blocked. [Inference]

**C. Session limit approaching or exceeded**

When the session time limit is approaching (RS-1), the robot should not initiate new engagement. It should wind down:
- Reduce proactive behaviors to zero in the last 2 minutes of a session
- Allow only farewell-type expressions (warm, calm)
- Never initiate a new topic or activity near session end

[Inference -- derived from RS-1 session time limits and dependency prevention]

**D. Recent error or system instability**

After a system error, the robot should show THINKING/recovery behavior (failure transparency) but NOT attempt to re-engage the child proactively. Error states should suppress initiative until stability is confirmed. [Inference]

**E. Night/sleep hours (if time-aware)**

If the robot has time-of-day awareness, proactive behaviors should be zero during defined sleep hours. The robot should be in SLEEPY/off mode with no initiative. [Inference]

### 4.2 Context Sensitivity Framework

The personality engine needs a **context gate** that modulates initiative probability based on current context. Here is a framework:

```
initiative_probability = base_probability(SI_axis)
    * context_multiplier(conversation_state)
    * context_multiplier(child_affect)
    * context_multiplier(session_progress)
    * context_multiplier(error_state)
    * context_multiplier(time_of_day)
```

Where each multiplier is:

| Context | Multiplier | Rationale |
|---------|-----------|-----------|
| No conversation, child present | 1.0 | Normal operating mode |
| Conversation active | 0.0 | LLM drives emotion; idle suppressed |
| Child affect negative (Layer 1) | 0.0 | Suppress playful initiative; empathic mode |
| Session in last 2 minutes | 0.0 | Wind-down mode |
| Session in first 1 minute | 0.5 | Let child settle in |
| Error state active | 0.0 | Recovery mode |
| Sleep hours | 0.0 | Inactive |
| Post-conversation (0-2 min) | 0.3 | Cool-down, let conversation emotion decay |
| Normal idle | 1.0 | Standard |

[Inference -- framework synthesized from multiple sources]

### 4.3 Kidd & Breazeal (2004): Proactive Initiative and Physical Presence

Kidd & Breazeal (2004) studied how a physically present robot compared to a screen-based agent and found that people bonded with the physical robot more, trusted it more, and interacted with it more. The physical robot was perceived as more credible, engaging, and trustworthy. [Empirical]

**Relevance**: Because our robot is physically embodied (not a screen character), its proactive behaviors carry more weight. A physical robot's initiative feels more socially real than a screen agent's. This means:
- Proactive behaviors feel more impactful (positive when appropriate)
- Proactive mistakes feel more intrusive (negative when inappropriate)
- The threshold for "annoying" is lower for physical robots than screen agents

**Design implication**: Physical presence amplifies both the benefit and risk of initiative. At SI=0.30, this argues for conservatism -- the physicality already provides social presence without the robot needing to push for engagement. [Inference]

**Citation**: Kidd, C. D., & Breazeal, C. (2004). Effect of a robot on user perceptions. *Proceedings of the 2004 IEEE/RSJ International Conference on Intelligent Robots and Systems* (IROS), 3559-3564.

---

## 5. Initiative at Social Initiative = 0.30

### 5.1 What "Mostly Passive" Looks Like in Practice

At Social Initiative = 0.30 on a 0-1 scale, the robot is in the lower third of the initiative range. Research on passive vs. active robot roles provides concrete behavioral descriptions:

**Passive robot characteristics** (from Chao & Thomaz, 2014; Frontiers in Robotics, 2016):
- Waits for human to provide attention stimulus
- Does not initiate conversations or activities
- Responds when addressed but does not reach out
- People must approach and engage first

**Our robot at 0.30 is not fully passive (that would be 0.0)**. It is "mostly responsive with occasional autonomous expression." Concretely:

| Behavior | Frequency at SI=0.30 | Comparison Points |
|----------|---------------------|-------------------|
| Verbal initiation (unprompted speech) | ~0 per session | SI=0.0 = never; SI=0.7 = 2-3 per session |
| Emotional idle expression | 2-4 mood shifts per hour of idle | SI=0.0 = no idle emotions; SI=0.7 = 6-8 per hour |
| Greeting on child approach | Always (this is responsive, not proactive) | Same at all SI levels -- this is engagement, not initiative |
| Boot/startup expression | Always (this is event-driven, not proactive) | Same at all SI levels -- system event |
| Attention-getting (unprompted gesture/sound to attract child) | 0-1 per day | SI=0.0 = never; SI=0.7 = several per session |
| Playful interjection during idle | ~0 | SI=0.0 = never; SI=0.7 = occasional |

[Inference -- interpolated from research on passive vs. active robot roles]

### 5.2 Translating the 0-1 Axis to Concrete Parameters

The Social Initiative axis should map to the following affect vector parameters:

| Parameter | Formula | At SI=0.30 | Meaning |
|-----------|---------|-----------|---------|
| `initiative_base_probability` | SI^1.5 (sublinear -- initiative grows slowly at low SI) | 0.30^1.5 = 0.164 | ~16% probability that any initiative trigger fires |
| `idle_impulse_magnitude` | 0.1 + SI * 0.3 | 0.19 | Idle impulses are weak -- barely shift the affect vector |
| `initiative_cooldown_min` | 30 / (0.1 + SI) minutes | 75 min | Minimum time between proactive behaviors |
| `autonomous_impulse_frequency` | SI * 4 per hour | 1.2 per hour | ~1 visible mood shift per hour during idle |
| `attention_seeking_threshold` | 1.0 - SI (higher = harder to trigger) | 0.70 | Very high threshold -- almost never seeks attention |

[Inference -- no published mapping exists; these are derived from behavioral descriptions at known anchor points]

**Anchor points used for calibration**:
- SI=0.0: Fully passive. No idle emotion. No initiative. Robot is a reactive tool.
- SI=0.30: Mostly passive. Idle emotion present but subtle. Initiative extremely rare. Robot feels "quietly alive."
- SI=0.50: Balanced. Moderate idle emotion. Occasional initiative (~2 per session). Robot is a conversational peer.
- SI=0.70: Moderately proactive. Frequent idle emotion. Regular initiative. Robot actively seeks engagement.
- SI=1.0: Fully proactive. Constant emotional expression. Frequent initiation. Robot demands attention.

### 5.3 Concrete Frequency Recommendation

**For Social Initiative = 0.30 with sessions of 15-20 minutes, 2-3 sessions per day:**

| Proactive Behavior | Per Session | Per Hour (idle) | Per Day |
|-------------------|-------------|-----------------|---------|
| **Verbal initiation** | 0 | 0 | 0 |
| **Idle mood shifts** (visible to child if watching) | N/A (between sessions) | 1-2 | 4-8 |
| **Event-driven emotion** (boot, battery, error) | As events occur | As events occur | ~2-5 |
| **Greeting on approach** | 1 (per session start) | N/A | 2-3 |
| **Attention-getting** | 0 | 0 | 0-1 |
| **Playful interjection** | 0 | 0 | 0 |
| **Total proactive emotional displays** | ~1 (greeting only) | 1-2 (idle only) | ~8-16 |

**Key principle**: At SI=0.30, the vast majority of the robot's emotional expression is **reactive** (responding to conversation, system events) or **idle** (visible but not attention-seeking). Truly proactive behavior (attempting to engage an unengaged child) is essentially zero. [Inference]

---

## 6. Proactive Behaviors Catalog

### 6.1 Behaviors Tested in Child-Robot Interaction

Based on the literature, here is a catalog of proactive behaviors that have been tested with children, along with reception data:

| Behavior | Description | Child Reception | Our Robot? | Evidence |
|----------|-------------|-----------------|-----------|----------|
| **Greeting/introduction** | Robot greets child by name or with a welcoming expression | Positive -- children smiled, laughed, showed enjoyment | Yes (responsive, not proactive -- triggered by child approach) | Serholt & Barendregt (2016), multiple CRI studies [Empirical] |
| **Question-asking** | Robot asks child a question to initiate conversation | Positive in educational contexts; can be annoying if unprompted in free play | No at SI=0.30 (this is a verbal initiation) | Serholt & Barendregt (2016) [Empirical] |
| **Positive feedback** | Robot says "great job!" or shows HAPPY in response to child action | Very positive -- smiles were most common response | Yes (but only during conversation -- this is reactive) | Serholt & Barendregt (2016) [Empirical] |
| **Empathic mirroring** | Robot matches child's emotional state | Positive when appropriate; uncomfortable when mismatched | Yes during conversation (Layer 1); not during idle | Leite et al. (2013) [Empirical] |
| **Handshake/physical interaction** | Robot offers handshake, hug, or other physical contact | Positive, especially early in relationship | Not applicable (no arms/hands) | Kanda et al. (2004) [Empirical] |
| **Singing/dancing** | Robot performs a song or dance unprompted | Positive initially; novelty wears off within 2-3 sessions | Not at SI=0.30 (too proactive); possible at SI=0.5+ | Kanda et al. (2004) [Empirical] |
| **Pointing to objects** | Robot draws attention to objects in the environment | Moderately positive -- depends on relevance | Not applicable (no pointing capability) | Kanda et al. (2004) [Empirical] |
| **Personal remarks** | Robot comments on child's behavior or past interactions | Initially positive; can become tiresome if too frequent | Not at SI=0.30; requires Layer 1 + memory | Kanda et al. (2004) [Empirical] |
| **Idle napping** | Robot appears to fall asleep when idle | Positive -- perceived as "cute" and lifelike | Yes -- primary idle behavior | EMO robot consumer data [Empirical] |
| **Curious head-tilt** | Robot shows curiosity about something | Positive -- signals engagement without demanding attention | Yes -- boot behavior and occasional idle | Breazeal (2003) [Empirical] |
| **Self-entertaining** | Robot appears to entertain itself (humming, slight movement) | Moderately positive -- perceived as "alive" | Limited at SI=0.30 (very rare, subtle only) | EMO robot [Empirical] |
| **Bored sigh** | Robot shows boredom when alone | Mixed -- perceived as cute initially but can become guilt-inducing | No -- violates HC-5 (loneliness/abandonment expression) | EMO robot design [Empirical]; Bucket 0 HC-5 [Constraint] |
| **Sad face when alone** | Robot looks sad when no one is interacting | Negative -- drives interaction through guilt/manipulation | No -- explicitly violates HC-5 | Breazeal (2003) Kismet design [Empirical]; Bucket 0 HC-5 [Constraint] |

### 6.2 Behaviors Appropriate at SI=0.30

Filtering the catalog above for SI=0.30, only the following proactive/idle behaviors are appropriate:

**Always active (event-driven, not initiative-dependent):**
1. Boot/startup CURIOUS expression
2. Low battery CONCERNED expression
3. Error/fault THINKING expression
4. Greeting expression on child approach (responsive)
5. Post-conversation residual emotion decay

**Active during idle (subtle, non-attention-seeking):**
6. Idle --> CONTENT/NEUTRAL baseline
7. Medium idle --> SLEEPY drift
8. Long idle --> deep SLEEPY
9. Time-of-day arousal modification
10. Occasional cosmetic variation (gesture, micro-expression)

**Explicitly excluded at SI=0.30:**
- Verbal initiation of any kind
- Attention-getting gestures or sounds
- Playful interjection
- Bored/lonely/sad expressions
- Self-entertaining behavior visible enough to attract attention
- Personal remarks or questions

---

## 7. Design Recommendations

### 7.1 Initiative Frequency: Concrete Recommendation

**For Social Initiative = 0.30:**

- **0 verbal proactive initiations per session.** The robot never starts talking unprompted. All conversation starts with the child (or a caregiver pressing the ACTION button).

- **1-2 visible idle mood shifts per hour** when the child is not actively interacting. These are expression-only (face changes) without sound or movement beyond cosmetic animation. They should follow the idle behavior catalog timing (Section 3.3).

- **Event-driven emotions fire immediately** regardless of frequency. Boot, battery, error, and child-approach events always produce emotional responses. These are grounded in reality (per Rivoire, 2016) and are never perceived as annoying because they have a clear cause.

- **Total proactive emotional displays: approximately 8-16 per day** across all categories, with the vast majority being idle mood shifts and event responses, not attention-seeking behaviors.

### 7.2 Idle Emotional Behavior: Deterministic Rules + Integrator Noise

**Recommendation: PE-3 Option A (rule-based deterministic) implemented through the decaying integrator.**

The idle behavior catalog (Section 3.3) provides the deterministic backbone:
- System events --> impulses into affect vector
- Time-based thresholds --> impulses into affect vector (with Gaussian jitter on timing from Predictability axis)
- Temperament baseline --> continuous decay target

The Predictability axis (0.75) adds cosmetic variation:
- 25% noise amplitude on idle impulse timing, intensity, and mood variant selection
- This produces perceived "aliveness" without requiring a separate stochastic module

No separate stochastic probability distribution is needed. The integrator + noise IS the stochastic element.

### 7.3 The Annoying Threshold

**At SI=0.30, the risk of being annoying is extremely low.** The risk is being boring (failure mode 3: "dead idle" from the personality spec).

The annoying threshold for child-robot interaction is approximately:
- **> 3 unsolicited verbal initiations per 15-minute session** (we do zero)
- **> 1 attention-getting behavior per session** (we do zero)
- **> 1 visible mood change per 5 minutes during idle** (we do approximately 1 per 30-45 minutes)
- **Context-irrelevant proactive behavior at any frequency** (we only do event-driven and time-based)

We are well below all thresholds. The risk is that the robot feels "too dead" in idle, which is addressed by the idle behavior catalog.

### 7.4 Context Rules: When to Suppress Initiative

The context gate framework (Section 4.2) provides clear suppression rules:

| Suppress all initiative when... | Rationale |
|--------------------------------|-----------|
| Conversation is active | LLM drives emotion |
| Child affect is negative (Layer 1 signal) | Don't be playful when child is upset |
| Session limit approaching (last 2 min) | Wind-down, don't re-engage |
| Error state active | Recovery mode |
| Sleep hours configured | Inactive period |
| Post-conversation cool-down (0-2 min) | Let conversation emotion decay naturally |

These are implemented as multipliers on initiative probability, reducing it to zero in suppression contexts.

### 7.5 Deterministic vs. Stochastic: Final Position

**Idle emotional behavior (PE-3) should be deterministic rules with stochastic variation provided by the integrator.**

Evidence chain:
1. Deterministic rules are debuggable, testable, and predictable -- essential for a child-facing product where surprising behavior must be explainable. [Inference]
2. Pure determinism without variation becomes stale within days (Predictability = 0.75 implies 25% variation). [Inference from novelty/habituation research]
3. The decaying integrator already provides a natural mechanism for stochastic variation: noise added to the affect vector at each tick (scaled by 1 - Predictability = 0.25) produces subtle variation in timing and intensity of mood transitions. [Inference]
4. A separate stochastic module (PE-3 Option B) adds engineering complexity without adding personality quality beyond what integrator noise provides. [Inference]

**Conclusion**: PE-3 Option A + integrator noise. No need for explicit probability distributions over idle moods.

---

## Sources

- [Semantic Scholar: The Delicate Balance of Boring and Annoying -- Rivoire (2016)](https://www.semanticscholar.org/paper/The-Delicate-Balance-of-Boring-and-Annoying-:-in-Rivoire/af708f9caa102c90ebf6a4a9c3b26b90282f38b4)
- [ACM: What is Proactive Human-Robot Interaction? -- Zafari & Koeszegi (2024)](https://dl.acm.org/doi/10.1145/3650117)
- [ScienceDirect: Explorations in Engagement for Humans and Robots -- Sidner et al. (2005)](https://www.sciencedirect.com/science/article/pii/S0004370205000512)
- [Springer: Social Robots for Long-Term Interaction: A Survey -- Leite et al. (2013)](https://link.springer.com/article/10.1007/s12369-013-0178-y)
- [ScienceDirect: Emotion and Sociable Humanoid Robots -- Breazeal (2003)](https://www.sciencedirect.com/science/article/abs/pii/S1071581903000181)
- [MIT Media Lab: A Motivational System for Regulating Human-Robot Interaction -- Breazeal (1998)](https://robots.media.mit.edu/wp-content/uploads/sites/7/2015/01/Breazeal-AAAI-98.pdf)
- [ResearchGate: Robots Tutoring Children -- Serholt & Barendregt (2016)](https://www.researchgate.net/publication/309428505_Robots_Tutoring_Children_Longitudinal_Evaluation_of_Social_Engagement_in_Child-Robot_Interaction)
- [PMC: Robot Initiative in a Team Learning Task -- Chao & Thomaz (2014)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3925832/)
- [ResearchGate: A Two-Month Field Trial in an Elementary School -- Kanda et al. (2004)](https://www.researchgate.net/publication/3450498_A_Two-Month_Field_Trial_in_an_Elementary_School_for_Long-Term_Human-Robot_Interaction)
- [IEEE/MIT: Effect of a Robot on User Perceptions -- Kidd & Breazeal (2004)](https://www.media.mit.edu/publications/effect-of-a-robot-on-user-perceptions/)
- [Springer: TAME: Time-Varying Affective Response for Humanoid Robots -- Moshkina & Arkin (2011)](https://link.springer.com/article/10.1007/s12369-011-0090-2)
- [WASABI Architecture -- Becker-Asano & Wachsmuth (2010)](https://www.becker-asano.de/index.php/research/wasabi/61-wasabi-architecture-overview)
- [Springer: Emotion and Mood Blending in Embodied Artificial Agents (2022)](https://link.springer.com/article/10.1007/s12369-022-00915-9)
- [arXiv: Robot Character Generation and Adaptive Human-Robot Interaction (2025)](https://arxiv.org/html/2503.15518v2)
- [Living.AI: EMO Robot](https://us.keyirobot.com/blogs/buying-guide/what-is-the-emo-robot-actually-and-why-do-people-keep-it-on-their-desk)
- [PMC: Empathy in Human-Robot Interaction: Designing for Social Robots (2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8835506/)
- [IADIS: Head Movements in the Idle Loop Animation (2020)](https://www.iadisportal.org/ijcsis/papers/2020150210.pdf)
- [ACM: Animation Techniques in Human-Robot Interaction (2019)](https://dl.acm.org/doi/fullHtml/10.1145/3317325)
- [ResearchGate: Motions of Robots Matter! The Social Effects of Idle and Meaningful Motions (2015)](https://www.researchgate.net/publication/281841000_Motions_of_Robots_Matter_The_Social_Effects_of_Idle_and_Meaningful_Motions)
- [Frontiers: The Robot That Stayed (2025)](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1628089/full)
- [Science Robotics: Social Robots as Conversational Catalysts (2024)](https://www.science.org/doi/10.1126/scirobotics.adk3307)
