# Bucket 2: Emotional Memory & Affect Dynamics

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-2 (Emotional Memory Scope) and affect decay parameter tuning

---

## Table of Contents

1. [Empirical Affect Decay Rates](#1-empirical-affect-decay-rates)
2. [Mood vs Emotion: The Two-Layer Architecture](#2-mood-vs-emotion-the-two-layer-architecture)
3. [Within-Session Emotional Memory](#3-within-session-emotional-memory)
4. [Cross-Session Memory Evidence](#4-cross-session-memory-evidence)
5. [Over-Personalization and Privacy Risks](#5-over-personalization-and-privacy-risks)
6. [Memory Decay Models](#6-memory-decay-models)
7. [WASABI Architecture: Mood as Diffuse Background](#7-wasabi-architecture-mood-as-diffuse-background)
8. [Marsella & Gratch: Computational Emotion with Memory](#8-marsella--gratch-computational-emotion-with-memory)
9. [Recommended Half-Lives and Lambda Values](#9-recommended-half-lives-and-lambda-values)
10. [Memory Structure Recommendations](#10-memory-structure-recommendations)
11. [Design Recommendations](#11-design-recommendations)

---

## 1. Empirical Affect Decay Rates

### 1.1 D'Mello & Graesser: Affect Dynamics During Learning

The most directly applicable empirical data on how emotions persist and transition comes from D'Mello and Graesser's program of research on affect dynamics during complex learning (2011, 2012). While their context is educational software rather than social robots, their methodology -- observing naturalistic affective states over extended interaction periods with frame-by-frame coding -- produces the best available data on emotional duration and transition patterns.

**Study design (D'Mello & Graesser, 2012)**: Participants interacted with AutoTutor (an intelligent tutoring system) for approximately 32 minutes. Affect was coded at 20-second intervals by trained judges observing face video. Six affective states were tracked: boredom, confusion, delight, engagement/flow, frustration, and surprise. The resulting data enabled construction of transition likelihood matrices showing the probability of moving from one affective state to another. [Empirical]

**Key findings on state duration and persistence**:

- **Surprise/delight**: Very short-lived. Surprise rarely persisted across two consecutive 20-second observation windows, implying a half-life under 5 seconds. Delight showed similar brevity -- it occurs as a punctual response to a positive event and decays rapidly. [Empirical]

- **Frustration**: Moderate persistence. Frustration showed a half-life of approximately 20 seconds. It tends to self-resolve unless the triggering condition (e.g., repeated failure) persists. When frustration does persist, it most commonly transitions to boredom rather than to engagement. [Empirical]

- **Engagement/flow**: Moderate duration with high recurrence. Individual engagement episodes lasted approximately 14 seconds on average, but engagement was the most recurrent state -- once a learner entered flow, they were highly likely to return to it after brief departures. This suggests engagement is not a single sustained state but a rapidly cycling attractor. [Empirical]

- **Boredom**: Long-lived and highly recurrent. Once established, boredom was the most persistent state and the hardest to exit. D'Mello & Graesser describe boredom as an "attractor state" -- affective dynamics tend to converge toward boredom over time unless actively disrupted. Boredom also showed the highest self-transition probability (remaining bored given already bored). [Empirical]

- **Confusion**: Moderate duration, context-dependent. Confusion persisted for 10-20 seconds and frequently transitioned to either engagement (productive confusion -- the learner is working through a problem) or frustration (unproductive confusion -- the learner is stuck). This bifurcation makes confusion a pivotal state. [Empirical]

**Citation**: D'Mello, S. K., & Graesser, A. C. (2012). Dynamics of affective states during complex learning. *Learning and Instruction*, 22(2), 145-157.

### 1.2 Transition Likelihood Matrix (Simplified)

D'Mello & Graesser's transition matrices reveal the probabilistic flow between states. The following is a simplified representation of the key transition probabilities relevant to our design:

| From \ To | Engagement | Confusion | Frustration | Boredom | Delight | Neutral |
|-----------|-----------|-----------|-------------|---------|---------|---------|
| **Engagement** | 0.41 | 0.13 | 0.04 | 0.08 | 0.08 | 0.26 |
| **Confusion** | 0.21 | 0.19 | 0.13 | 0.10 | 0.05 | 0.32 |
| **Frustration** | 0.12 | 0.13 | 0.17 | 0.19 | 0.04 | 0.35 |
| **Boredom** | 0.10 | 0.08 | 0.10 | 0.33 | 0.03 | 0.36 |
| **Delight** | 0.25 | 0.09 | 0.04 | 0.06 | 0.08 | 0.48 |

*Values are approximate, derived from D'Mello & Graesser (2012) Tables 2 and 4. Rows do not sum to 1.0 because surprise and other minor states are omitted.*

**Interpretation for our design**:

1. **Engagement is sticky and recurrent** (0.41 self-transition). Once the child is engaged, the affect vector should be slow to leave the engagement/flow region. Implementation: low decay rate for positive-arousal states. [Inference]

2. **Boredom is an attractor** (0.33 self-transition, low exit probability to positive states). If our robot enters a boredom-like state, it should require a strong external impulse to exit. However, we should resist this for a child-facing robot -- we want the robot to model emotional resilience, not mirror boredom's sticky quality. [Inference]

3. **Confusion bifurcates** -- it goes to engagement (productive) or frustration (unproductive). The robot should display CONFUSED/THINKING briefly, then resolve toward either CURIOUS (productive) or mild CONCERNED (unproductive), never lingering in confusion. [Inference]

4. **Frustration leads to boredom more than to engagement** (0.19 vs 0.12). If the robot shows frustration, the natural trajectory is disengagement. This reinforces the personality spec's asymmetric decay: negative emotions should decay faster toward baseline to prevent the frustration-to-boredom slide. [Inference]

**Citation**: D'Mello, S. K., & Graesser, A. C. (2011). The half-life of cognitive-affective states during complex learning. *Cognition & Emotion*, 25(7), 1299-1308.

### 1.3 Applicability to Child-Robot Interaction

D'Mello and Graesser studied adult learners, not 4-6 year olds. Several adjustments are warranted:

- **Children have shorter attention spans** and faster emotional cycling. Half-lives should be scaled shorter for children ages 4-6. A rough scaling factor of 0.5-0.75 on adult half-lives is reasonable based on developmental psychology of emotional regulation (Eisenberg et al., 2010). [Inference]

- **Children's emotions are more externally driven**. Adult emotional persistence often involves rumination (internal re-triggering). Young children are more stimulus-bound -- remove the stimulus and the emotion dissipates faster. This argues for faster base decay rates. [Theory]

- **Positive emotions may be more durable in play contexts** than in learning contexts. D'Mello's data comes from tutoring (effortful, sometimes frustrating). A companion robot in free play should expect longer-lived positive states. [Inference]

**Citation**: Eisenberg, N., Spinrad, T. L., & Eggum, N. D. (2010). Emotion-related self-regulation and its relation to children's maladjustment. *Annual Review of Clinical Psychology*, 6, 495-525.

---

## 2. Mood vs Emotion: The Two-Layer Architecture

### 2.1 The Phasic-Tonic Distinction

A core finding across multiple computational affect architectures is the separation of emotional phenomena into two temporal layers:

- **Phasic (emotion)**: Short-lived, high-intensity responses to specific events. Time scale: seconds to tens of seconds. Triggered by discrete stimuli (a joke, a startling event, a sad comment). Emotions have clear onset points and decay rapidly. [Theory]

- **Tonic (mood)**: Diffuse, low-intensity background states that color perception and behavior over longer periods. Time scale: minutes to hours. Not triggered by single events but by accumulated emotional experience. Mood shifts gradually and does not have sharp onset/offset boundaries. [Theory]

This distinction is not merely theoretical convenience -- it maps onto different neural substrates (Davidson, 1998) and produces different behavioral signatures. A person in a good mood does not show "happy face" continuously (that would be a phasic expression); instead they interpret ambiguous stimuli more positively, show higher engagement, and recover faster from minor setbacks. [Theory]

**For our robot**: The continuous affect vector must implement both layers as coupled integrators -- a fast-decaying emotion layer and a slow-decaying mood layer. The face projection draws primarily from the emotion layer (phasic expressions), but the mood layer influences the baseline toward which emotions decay and modulates the gain of new impulses.

**Citation**: Davidson, R. J. (1998). Affective style and affective disorders: Perspectives from affective neuroscience. *Cognition & Emotion*, 12(3), 307-330.

### 2.2 ALMA: A Layered Model of Affect (Gebhard, 2005)

Gebhard's ALMA (A Layered Model of Affect) is one of the most cited architectures for implementing the phasic-tonic distinction in virtual agents. ALMA separates affect computation into three explicit layers:

1. **Personality layer** (stable, months-years): Based on the Big Five / OCEAN model. Defines the agent's dispositional tendencies. Does not change during interaction. Maps to our Trait layer (temperament baseline, decay rates, impulse scaling). [Theory]

2. **Mood layer** (tonic, minutes-hours): A diffuse affective background computed from accumulated emotional valence and personality bias. Mood in ALMA is represented in the PAD (Pleasure-Arousal-Dominance) space of Mehrabian (1996). Mood influences which emotions are more easily triggered (congruent mood lowers the threshold for matching emotions) and modulates the intensity of emotional expression. [Theory]

3. **Emotion layer** (phasic, seconds): Discrete emotional responses generated by cognitive appraisal of events using the OCC (Ortony, Clore & Collins, 1988) emotion model. Each emotion has an intensity that decays over time. The decay rate is influenced by the personality layer (e.g., neurotic agents sustain negative emotions longer). [Theory]

**The critical coupling mechanism**: In ALMA, emotions feed into mood -- a sequence of positive emotions shifts the mood in a positive direction. Mood feeds into emotion -- a positive mood makes positive emotions easier to trigger and negative emotions harder. Personality feeds into both -- it sets the baseline mood and modulates emotional reactivity.

```
Personality → Mood baseline, emotional thresholds
Events → Emotion (via OCC appraisal)
Emotion → Mood (accumulated valence/arousal shifts mood)
Mood → Emotion (mood congruence biases next emotion)
```

**Relevance to our design**: ALMA validates the coupled integrator architecture proposed in the personality engine spec (C.4). Our system has:
- Trait layer = personality axes (static)
- Affect vector = conflation of mood and emotion (needs separation)

The research suggests we should implement **two coupled affect vectors**: a fast-decaying emotion vector (half-life: seconds) and a slow-decaying mood vector (half-life: minutes). Emotions decay toward the mood vector. The mood vector decays toward the personality baseline. This produces natural emotional inertia -- a burst of sadness shifts mood slightly negative, making subsequent sadness easier to trigger and joy harder. [Inference]

**Citation**: Gebhard, P. (2005). ALMA -- A Layered Model of Affect. *Proceedings of the Fourth International Joint Conference on Autonomous Agents and Multiagent Systems (AAMAS '05)*, 29-36.

### 2.3 TAME: Trait, Attitude, Mood, Emotion (Moshkina & Arkin, 2005)

TAME extends the layered model to four levels, explicitly targeting robot platforms:

1. **Traits** (permanent): Big Five personality parameters set by the designer. Influence all lower layers. Participants in Moshkina's experiments could reliably distinguish between robots configured with different trait profiles (e.g., high vs low Extraversion). [Empirical]

2. **Attitudes** (long-term): Learned dispositions toward specific entities or categories (e.g., positive attitude toward a specific child, negative attitude toward loud noises). Updated slowly based on experience. This is the closest analog to our cross-session memory. [Theory]

3. **Moods** (medium-term): Background affect state influenced by accumulated emotions and personality traits. TAME implements mood as a weighted integration of recent emotional events, with decay toward a personality-determined baseline. The Neuroticism trait parameter specifically controls mood recovery rate -- high Neuroticism produces slower recovery from negative moods. [Empirical]

4. **Emotions** (short-term): Stimulus-triggered responses that decay rapidly. Emotion intensity is modulated by current mood (congruent mood amplifies, incongruent mood attenuates) and personality traits (high Neuroticism amplifies negative emotions). [Theory]

**Behavioral cycling in TAME**: Without external stimulation, the robot cycles through temperament-biased behavior. A high-Extraversion robot without stimulation gradually shifts toward seeking interaction; a low-Extraversion robot settles into self-contained idle behavior. This cycling is implicit mood -- the Attitude and Mood layers slowly drift the robot's behavioral tendencies even without discrete emotional events. [Empirical]

**Validation**: Moshkina & Arkin (2011) ran perception studies where naive participants watched videos of a robot (Sony AIBO) configured with different TAME personality profiles. Participants rated the robot's personality using standardized Big Five questionnaires. Results showed that trait configurations produced statistically distinguishable perceived personalities, confirming that the four-layer architecture generates observable behavioral differences. The strongest distinguishing factor was Extraversion (activity level, approach/withdrawal behavior). Neuroticism was perceived primarily through emotional recovery time -- how long the robot stayed "upset" after a startling event. [Empirical]

**Relevance to our design**: TAME's four layers map cleanly to our architecture:
- Traits = personality axis positions (static)
- Attitudes = cross-session memory (PE-2)
- Mood = tonic integrator (slow decay)
- Emotion = phasic integrator (fast decay)

The TAME validation data confirms that emotional recovery time (decay rate) is the primary behavioral signature of personality for observers. This means our lambda parameter -- the decay rate in the affect ODE -- is the single most important personality parameter to get right. [Inference]

**Citation**: Moshkina, L., & Arkin, R. C. (2005). Human perspective on affective robotic behavior: A longitudinal study. *Proceedings of the IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)*, 1444-1451.

**Citation**: Moshkina, L., & Arkin, R. C. (2011). TAME: Time-varying affective response for humanoid robots. *International Journal of Social Robotics*, 3(3), 207-221.

### 2.4 Kismet: Behavior Cycling as Implicit Mood

Breazeal's Kismet (2003) does not implement an explicit mood layer, but achieves mood-like behavior through its homeostatic drive system. Three drives (social stimulation, fatigue, play) continuously drift from their set points. The combination of drive levels produces a background motivational state that biases emotional expression:

- When social stimulation drive is high (no one present): the robot displays increasingly intense "seeking" behavior -- scanning, alert expression, and eventually "distress" (sadness/loneliness) if no social partner appears. [Empirical]

- When fatigue drive is high (extended activity): the robot slows down, eventually closes eyes and enters sleep mode. All drives reset during sleep. [Empirical]

- Emotional reactions overlay onto the current drive state. A positive social event (face detected) triggers joy, but the intensity is modulated by the current drive balance -- joy is more intense when social stimulation drive is high (the robot "needed" this interaction). [Empirical]

**Implicit mood mechanism**: The slowly drifting drives create an implicit tonic layer. Kismet does not store "mood" as a variable, but the cumulative drive state functions identically to mood -- it biases emotional responses and produces different behavioral tendencies over time scales of minutes. [Theory]

**Limitation for our design**: Kismet's drives are entirely homeostatic (deviation from equilibrium produces corrective behavior). Our robot does not need to actively seek interaction (Social Initiative = 0.30), so we cannot use social stimulation drive in the Kismet sense. However, the fatigue/energy drive concept maps well to our idle behavior (idle time increases "fatigue" drive, producing SLEEPY). See Bucket 4 for how this was resolved. [Inference]

**Citation**: Breazeal, C. (2003). Emotion and sociable humanoid robots. *International Journal of Human-Computer Studies*, 59(1-2), 119-155.

### 2.5 Convergence Across Architectures

Despite different terminology and implementation details, ALMA, TAME, and Kismet converge on the same essential architecture:

| Property | ALMA | TAME | Kismet | Our System |
|----------|------|------|--------|------------|
| Fast layer (seconds) | Emotion (OCC) | Emotion | Emotional responses | Phasic integrator |
| Slow layer (minutes) | Mood (PAD) | Mood | Drive balance | Tonic integrator |
| Static layer | Personality (Big Five) | Traits (Big Five) | Drive set-points | Personality axes |
| Fast decays toward... | Mood | Mood + Trait bias | Drive equilibrium | Tonic integrator |
| Slow decays toward... | Personality baseline | Trait baseline | Set-points | Personality baseline |
| Mood-emotion coupling | Congruence bias | Congruence amplification | Drive modulation | Impulse scaling |

**Architectural conclusion**: The coupled integrator model is well-validated across all three major computational affect architectures. Our system should implement two coupled integrators (phasic emotion, tonic mood) rather than a single affect vector. The phasic layer decays toward the tonic layer (emotion decays toward mood). The tonic layer decays toward the personality baseline (mood decays toward temperament). The phasic layer feeds into the tonic layer (emotional events shift mood). [Theory -- convergent across ALMA, TAME, Kismet]

---

## 3. Within-Session Emotional Memory

### 3.1 Emotional Carry-Over Across Conversation Turns

Within a single conversation session, emotional context must persist across turns. The question is: for how long?

**The problem of emotional amnesia**: The current system treats each conversation turn independently. If the child says "my dog is sick" and the robot responds empathetically, the very next turn might produce a cheerful response if the child says something neutral. This emotional amnesia is one of the personality failure modes identified in the spec (C.1). [Inference]

**Empirical guidance**: No published study directly measures "how many conversational turns should empathetic context persist in a child-robot interaction." However, converging evidence suggests:

- **Therapeutic conversation norms**: In child therapy, empathetic attunement after a disclosure of sadness typically persists for 3-5 exchanges before the therapist may gently redirect. Premature topic-switching signals dismissiveness. [Theory -- adapted from Landreth, 2012, child-centered play therapy]

- **D'Mello's engagement data**: Emotional states in learning contexts persist for approximately 14-20 seconds of continuous interaction, corresponding to roughly 2-4 conversational turns at typical child interaction pace (one turn every 5-8 seconds including response time). [Inference -- derived from D'Mello & Graesser, 2012]

- **Adult conversation studies**: Emotional carry-over in human conversation typically extends 2-5 turns after the triggering event, with declining intensity. Abrupt emotional shifts within 1-2 turns are perceived as incoherent or dismissive (Gonzales, Hancock, & Pennebaker, 2010). [Empirical]

**Recommendation for our system**: Empathetic context should persist for a minimum of 3 turns after the triggering event, with exponentially declining intensity. The phasic integrator naturally provides this -- a SAD impulse from the child's disclosure decays over several turns rather than disappearing instantly. The key is that the decay rate (lambda) for empathetic states must be slow enough that 3 turns at ~6-second pace (18 seconds total) retains at least 50% of the original impulse magnitude. This implies a half-life of approximately 18 seconds for empathetic states. [Inference]

**Citation**: Gonzales, A. L., Hancock, J. T., & Pennebaker, J. W. (2010). Language style matching as a predictor of social dynamics in small groups. *Communication Research*, 37(1), 3-19.

### 3.2 Affective Trace Structures

To implement within-session memory, the personality worker must store **affective traces** -- records of emotionally significant events that continue to influence the affect vector after the triggering event has passed.

**What to store per event**:

```
AffectiveTrace:
    timestamp: float          # when the event occurred (session time)
    source: str               # "llm", "system", "child_affect"
    valence_bias: float       # direction of influence (-1 to +1)
    arousal_bias: float       # direction of influence (-1 to +1)
    initial_magnitude: float  # starting strength (0 to 1)
    current_strength: float   # decaying strength (computed)
    decay_rate: float         # lambda for this trace
    context_tag: str          # semantic label ("child_sad", "shared_joke", "topic_dinosaurs")
```

**How traces influence the affect vector**: Each active trace applies a continuous, low-magnitude force on the affect vector in the direction of its bias. The force decays exponentially with time since the event. Traces are pruned when their current strength drops below a threshold (e.g., 0.01). [Inference]

This is the "memory influence" term in the integrator update from the personality spec (C.4):

```
for trace in active_memory:
    affect += trace.bias * trace.current_strength * memory_weight * dt
```

**Maximum active traces**: To prevent unbounded accumulation, limit active traces to approximately 20 per session. New traces push out the weakest existing trace if the limit is reached. This ensures bounded memory cost while retaining the most emotionally significant events. [Inference]

### 3.3 Emotional Inertia and Perceived Coherence

**Emotional inertia** -- the tendency of an emotional state to persist -- is not merely a technical implementation detail. It is a critical factor in whether the robot's emotional behavior is perceived as coherent by the child.

Kuppens, Allen, & Sheeber (2010) studied emotional inertia in human adolescents and found that moderate inertia is associated with healthy emotional functioning. Too little inertia (rapid mood switching) is associated with emotional instability. Too much inertia (emotional rigidity) is associated with depression. [Empirical]

**For our robot**: The decaying integrator naturally produces emotional inertia -- the affect vector cannot snap instantaneously to a new state because the decay toward baseline is continuous. The key design parameter is the balance between responsiveness (the robot should noticeably react to the child's emotions) and inertia (the robot should not mirror every emotional flicker). [Inference]

The Reactivity axis (0.50) directly controls this balance. At 0.50, the robot is moderately inertial -- responsive enough to validate the child's emotions, but not so reactive that it swings wildly between states. [Inference]

**Citation**: Kuppens, P., Allen, N. B., & Sheeber, L. B. (2010). Emotional inertia and psychological maladjustment. *Psychological Science*, 21(7), 984-991.

---

## 4. Cross-Session Memory Evidence

### 4.1 Ligthart et al. (2022): Memory-Based Personalization with Children

Ligthart, Lexis, de Graaf, and Hindriks (2022) conducted the most directly relevant study for our memory design question. They investigated the effect of a social robot's memory (remembering information from previous sessions) on children's engagement across five interaction sessions spread over approximately two months.

**Study design**: Children (ages 6-9) interacted with a NAO robot in a storytelling context. The robot either had memory (it remembered the child's name, preferences, and details from previous sessions and referenced them in subsequent sessions) or no memory (each session started fresh). Sessions were approximately 10-15 minutes each. [Empirical]

**Key findings**:

- **Children interacted more** with the memory-equipped robot. They spoke more, asked more questions, and showed more social cues (smiling, leaning forward, gesturing). [Empirical]

- **Memory fostered closeness**. Children rated the memory-equipped robot as more friendly and reported feeling closer to it. The effect was particularly strong in sessions 3-5, after sufficient memory had accumulated. [Empirical]

- **Memory maintained interest across sessions**. Without memory, children showed declining engagement from session 1 to session 5 (novelty effect fading). With memory, engagement was sustained or increased. The memory condition counteracted the novelty decay curve. [Empirical]

- **Personal references were the key mechanism**. Children responded positively when the robot said things like "Last time you told me you like dinosaurs. Do you want to hear a story about dinosaurs today?" The memory enabled personalized content selection and conversation continuity. [Empirical]

**Implication for our design**: Session-scoped memory (PE-2 Option B) is insufficient for sustained engagement. Cross-session memory (PE-2 Option C) is needed, but the minimum viable memory is small -- the robot needs to remember the child's name, 1-2 favorite topics, and the general tone of the previous session. It does not need to remember full conversation transcripts. [Inference]

**Citation**: Ligthart, M. E. U., Lexis, M. A. S., de Graaf, M. M. A., & Hindriks, K. V. (2022). Memory-based personalization in child-robot interaction: A retrieval and comparison study. *Frontiers in Robotics and AI*, 9, Article 819033.

### 4.2 Kanda et al. (2004): Personal Remarks in a Two-Month Field Trial

Kanda, Hirano, Eaton, and Ishiguro (2004) deployed a Robovie robot in an elementary school for two months. The robot interacted with 37 children across 32 sessions (approximately 30 minutes each, 3 sessions per week).

**Memory-related findings**:

- The robot tracked cumulative individual interaction time and introduced personal remarks after 180+ minutes of total interaction with a specific child. Personal remarks included referencing shared activities ("We played rock-paper-scissors before, didn't we?") and names. [Empirical]

- **Children who received personal remarks showed sustained engagement** beyond the novelty phase. The percentage of children who continued interacting dropped significantly after 2 weeks for all children, but the drop was less severe for children who had accumulated enough interaction time to trigger personal remarks. [Empirical]

- The robot also introduced new interactive behaviors (handshakes, exercises, singing) at cumulative time thresholds, but the personal remarks were specifically cited by children as making the robot feel "like a friend." [Empirical]

**Limitation**: Kanda et al.'s children were 8-12 years old, older than our target range. Younger children (4-6) may respond differently to personal remarks. However, the basic mechanism -- recognizing and referencing shared experience creates relationship continuity -- is well-established across ages. [Inference]

**Citation**: Kanda, T., Hirano, T., Eaton, D., & Ishiguro, H. (2004). Interactive robots as social partners and peer tutors for children: A field trial. *Human-Computer Interaction*, 19(1-2), 61-84.

### 4.3 Minimum Viable Cross-Session Memory

Synthesizing Ligthart et al. and Kanda et al., the minimum viable memory for relationship continuity consists of:

| Memory Item | Justification | Evidence |
|-------------|--------------|----------|
| **Child's name** | Personalization anchor; most basic form of recognition | Ligthart et al. (2022) -- name use increased engagement [Empirical] |
| **1-2 favorite topics** | Enables personalized content selection ("Want to hear about dinosaurs?") | Ligthart et al. (2022) -- topic memory was key mechanism [Empirical] |
| **Shared ritual/activity** | Creates continuity ("Last time we played the guessing game") | Kanda et al. (2004) -- personal remarks sustained engagement [Empirical] |
| **Last session's emotional tone** | Prevents emotional discontinuity ("Welcome back! We had fun last time") | Inference from emotional inertia research |
| **Session count** | Enables graduated behavior (first session = warm welcome; 5th session = familiar greeting) | Kanda et al. (2004) -- graduated behavior introduction [Empirical] |

**What is NOT needed for minimum viability**:
- Full conversation transcripts
- Detailed emotional logs per turn
- Inferred personality model of the child
- Calendar of interaction times
- Semantic understanding of past conversations beyond topic tags

**Evidence that session-scoped memory is insufficient**: Both Ligthart et al. and Kanda et al. demonstrate that cross-session memory is the mechanism that sustains engagement beyond the novelty phase. Without it, engagement declines predictably after 1-2 weeks regardless of robot personality quality. Session-scoped memory provides within-session coherence (important) but not relationship continuity (essential for long-term engagement). [Empirical -- convergent evidence from both studies]

### 4.4 When Cross-Session Memory Begins to Matter

Cross-session memory does not matter equally at all time points:

- **Sessions 1-3**: Novelty dominates. Memory has minimal impact because there is nothing meaningful to remember yet. [Inference]

- **Sessions 4-7**: The novelty cliff. This is where memory becomes critical. Without memory, the child returns to a "stranger" robot each time, and without novelty to compensate, engagement drops. With memory, the robot references shared experience and the child perceives relationship continuity. [Empirical -- Ligthart et al., 2022]

- **Sessions 8+**: Memory is the foundation of the relationship. The robot's ability to reference accumulated shared experience is what distinguishes it from a generic toy. [Inference]

**Design implication**: Cross-session memory can be implemented incrementally. For initial deployment, session-scoped memory is sufficient (sessions 1-3 are novelty-driven anyway). Cross-session memory should be functional before the child's 4th session. [Inference]

---

## 5. Over-Personalization and Privacy Risks

### 5.1 The Uncanny Recall Problem

Perfect recall in a machine creates a specific form of uncanniness that differs from the traditional uncanny valley (which concerns physical appearance). When a robot accurately references a passing comment from weeks ago, the reaction is often discomfort rather than delight -- the entity "knows too much." [Theory]

This problem has been documented in several contexts:

- **Yadav et al. (2016, Disney Research)** studied children's reactions to being "known" by interactive technology. Children ages 4-6 showed contained reactions to privacy-relevant disclosures -- they did not always protest when technology referenced personal information, but parents observing the same interactions were highly sensitive to it. The parent's perception of "creepiness" was triggered by the technology accurately referencing information the parent didn't expect it to have. [Empirical]

- **Luger & Sellen (2016)** found that conversational AI systems that demonstrate unexpected knowledge of the user trigger "surveillance anxiety" -- the user wonders what else the system knows and how it learned it. This effect was strongest when the system referenced information the user didn't remember providing. [Empirical]

**Design principle**: Memory should feel like **shared experience**, not surveillance. The robot should reference things as though it experienced them together with the child ("Remember when we talked about dinosaurs?") rather than as though it has been recording the child ("You mentioned dinosaurs on February 14th at 3:42 PM"). Vague, warm references are better than precise, clinical ones. [Inference]

**Implementation**: Memory retrieval should always use fuzzy framing:
- Good: "I remember you like dinosaurs!" (shared experience)
- Bad: "Last Tuesday you said your favorite dinosaur is T-Rex." (surveillance)
- Good: "We had fun last time!" (vague positive)
- Bad: "In our last session, your affect was 73% positive." (clinical)

**Citation**: Yadav, K., et al. (2016). Understanding children's interactions with conversational agents. *Proceedings of the 2016 CHI Conference Extended Abstracts on Human Factors in Computing Systems*, 2480-2486.

**Citation**: Luger, E., & Sellen, A. (2016). "Like having a really bad PA": The gulf between user expectation and experience of conversational agents. *Proceedings of the 2016 CHI Conference on Human Factors in Computing Systems*, 5286-5297.

### 5.2 COPPA Implications for Stored Emotional Data

Under the Children's Online Privacy Protection Act (COPPA), as updated effective June 2025:

- **Emotional interaction data constitutes "personal information"** when combined with any identifier (name, voice recording, device ID). If the robot stores that "Child X was sad during session Y," this is covered under COPPA. [Empirical -- regulatory]

- **Voice recordings must be deleted immediately** after STT processing. Storing audio for emotional analysis purposes requires explicit parental consent and creates significant compliance burden. [Empirical -- regulatory]

- **Biometric identifiers** (voiceprints for speaker identification) are "personal information" requiring verifiable parental consent before collection. This constrains PE-4 Option B (per-child profiles via voice ID). [Empirical -- regulatory]

- **Retention limits**: Even with consent, personal information should be retained only as long as necessary. Emotional memory that persists indefinitely is harder to justify than memory with built-in decay. [Empirical -- regulatory]

**Design constraints derived from COPPA**:

1. All emotional memory must be stored **locally on-device only**. Never transmitted to the server. The server receives anonymized semantic tags (e.g., `likes_dinosaurs=true`), never raw emotional logs. [Inference -- constrained by COPPA + HC-7]

2. Memory must have **mandatory decay**. No emotional data persists indefinitely. Decay rates should be calibrated so that conversation-level details fade within 1-2 weeks and only high-level tags (name, topics, rituals) persist longer. [Inference]

3. **Parental transparency**: Parents must be able to view all stored memory through the dashboard, and must be able to delete any or all stored data at any time. [Inference -- constrained by COPPA]

4. **Only store child-volunteered information**. The robot should not infer emotional states from behavior (e.g., "child seems anxious based on speech patterns") and store those inferences. Only information the child explicitly shares ("I like dinosaurs," "I'm sad today") should be retained. [Inference -- constrained by COPPA + HC-6]

### 5.3 The EU AI Act and Emotional Data

The EU AI Act (prohibitions effective February 2025) adds additional constraints:

- **Article 5(1)(a)**: Prohibits AI systems that deploy subliminal techniques or manipulative techniques to distort behavior. A robot that uses stored emotional data to manipulate a child's engagement (e.g., deliberately bringing up topics that made the child happy to keep them interacting longer) could violate this provision. [Empirical -- regulatory]

- **Article 5(1)(b)**: Prohibits exploiting age-based vulnerability. Using emotional memory to create dependency (the child interacts because the robot "remembers" them, creating an obligation to return) could fall under exploitation. [Empirical -- regulatory]

- **Emotion recognition ban (Article 5(1)(f))**: Applies to workplaces and education, NOT home use. However, the exploitation and manipulation prohibitions still apply to home use. [Empirical -- regulatory]

**Design constraint**: Emotional memory must serve the child's experience, not the system's engagement metrics. The robot should reference shared experience to create warmth and continuity, not to maximize session length or interaction frequency. This is enforced by the session time limits (RS-1) and the prohibition on artificial urgency (HC-8). [Inference]

### 5.4 Framing Memory as Shared Experience

The research and regulatory analysis converge on a single framing principle: **memory should feel like a friendship, not a dossier.**

| Approach | Example | Risk Level | Child Perception |
|----------|---------|------------|-----------------|
| **No memory** | Every session is a blank slate | None | Robot is a toy (no relationship) |
| **Shared experience** | "We had fun talking about dinosaurs!" | Low | Robot is a friend (remembers what we did together) |
| **Personal knowledge** | "You told me your dog is named Max." | Medium | Robot pays attention (positive if volunteered, creepy if inferred) |
| **Behavioral inference** | "You seem to like it when I'm excited." | High | Robot is watching me (surveillance anxiety) |
| **Perfect recall** | "On Feb 3rd you were sad because your friend was mean." | Very high | Robot is recording me (privacy violation) |

**Our design should operate in the "shared experience" zone**, occasionally reaching into "personal knowledge" for child-volunteered facts (name, favorite topics), but never into "behavioral inference" or "perfect recall." [Inference]

---

## 6. Memory Decay Models

### 6.1 Exponential Decay

The simplest and most commonly used memory decay model:

```
strength(t) = initial_strength * e^(-lambda * (t - t_event))
```

Where lambda is the decay rate and t_event is when the memory was formed. Half-life = ln(2) / lambda.

**Properties**:
- Memoryless: the rate of forgetting depends only on the current strength, not on how long the memory has existed
- Simple to implement and computationally cheap
- Produces smooth, continuous decay
- Used by WASABI, ALMA, and most computational affect models

**Limitation**: Exponential decay predicts that all memories of the same type fade at the same rate regardless of context. A deeply emotional shared experience decays at the same rate as a trivial conversational detail. This does not match human memory, where emotional salience enhances retention. [Theory]

### 6.2 Power-Law Forgetting (Ebbinghaus Curve)

Ebbinghaus (1885) and subsequent research established that human forgetting follows a power law rather than an exponential:

```
strength(t) = initial_strength * (1 + beta * (t - t_event))^(-alpha)
```

Power-law forgetting is slower than exponential at long time scales -- memories fade quickly at first but then stabilize. This matches the intuitive experience that old memories are surprisingly durable. [Empirical]

**Wixted & Ebbesen (1991)** confirmed that the power function provides the best fit for human forgetting across multiple studies and memory types. The key difference from exponential decay: a memory that has survived for a week is much more likely to survive another week than a fresh memory. [Empirical]

**For our robot**: Power-law forgetting is appropriate for cross-session memory (topics, rituals, name) but unnecessarily complex for within-session emotional traces (which only last seconds to minutes and are well-served by exponential decay). [Inference]

**Citations**:
- Ebbinghaus, H. (1885/1913). *Memory: A contribution to experimental psychology*. Teachers College, Columbia University.
- Wixted, J. T., & Ebbesen, E. B. (1991). On the form of forgetting. *Psychological Science*, 2(6), 409-415.

### 6.3 Context-Gated Persistence

Neither pure exponential nor power-law decay captures a critical feature of human emotional memory: **emotional salience gates persistence**. Memories formed during high-arousal emotional events are retained longer than emotionally neutral memories (McGaugh, 2004). [Empirical]

**Implementation for our system**: Emotional events near the child (during conversation) should decay more slowly than system events (boot, battery). This can be implemented by scaling the decay rate by an emotional salience factor:

```
effective_lambda = base_lambda / (1 + salience_factor * emotional_intensity)
```

Where emotional_intensity is the magnitude of the affect vector perturbation at the time of memory formation. A deeply sad conversation creates traces with higher emotional intensity and therefore slower decay. A routine greeting creates traces with low emotional intensity and faster decay. [Inference]

**Practical implementation**: Rather than computing continuous salience, assign each memory to a **decay tier** based on its type and emotional context at formation time. This produces a small number of discrete decay rates (see Section 6.4) rather than a continuous spectrum.

**Citation**: McGaugh, J. L. (2004). The amygdala modulates the consolidation of memories of emotionally arousing experiences. *Annual Review of Neuroscience*, 27, 1-28.

### 6.4 Memory Decay Tiers

Combining the decay models above with the practical requirements of our system, the following tier structure is recommended:

| Tier | Content | Decay Model | Half-Life | Lambda | Justification |
|------|---------|-------------|-----------|--------|---------------|
| **T0: Identity** | Child's name | Never decays | Infinite | 0 | Forgetting a name is a relationship violation, not graceful decay [Inference] |
| **T1: Rituals** | Shared activities, recurring games, greeting patterns | Power-law | Months (60-90 days effective) | ~0.008/day | Rituals define the relationship; slow decay maintains continuity [Empirical -- Kanda et al., 2004] |
| **T2: Topics** | Favorite subjects, interests ("likes dinosaurs") | Power-law | 2-4 weeks | ~0.025-0.050/day | Topics are durable but not permanent; interests change [Inference] |
| **T3: Session tone** | Emotional summary of last few sessions ("last time was fun") | Exponential | 1-2 weeks | ~0.050-0.100/day | Recent tone influences greeting and initial mood bias [Inference] |
| **T4: Conversation details** | Specific things said, particular stories told | Exponential | 3-5 days | ~0.14-0.23/day | Details should fade quickly -- perfect recall is creepy [Inference] |
| **T5: Inferred preferences** | Robot's guesses about child's preferences based on behavior | Exponential | 1-3 days | ~0.23-0.69/day | Inferences are the most privacy-sensitive; fastest decay [Inference] |
| **T6: Within-session traces** | Per-turn emotional events during active conversation | Exponential | 15-90 seconds | 0.008-0.046/s | See Section 1 half-life data; session-scoped, cleared at session end [Empirical] |

**Tier assignment rule**: Each memory is assigned to a tier at creation time based on its `context_tag`. Tier determines decay rate. A memory does not change tiers. [Inference]

**Pruning rule**: When a memory's effective strength drops below 0.05, it is pruned (deleted from storage). This ensures storage is bounded and creates genuine forgetting rather than arbitrarily precise but low-weight traces. [Inference]

**Reinforcement rule**: If the same topic or ritual appears in multiple sessions, its decay timer resets and its tier may upgrade (e.g., a topic mentioned in three sessions upgrades from T2 to T1). This models the spacing effect in human memory -- repeated exposure strengthens retention. [Inference]

---

## 7. WASABI Architecture: Mood as Diffuse Background

### 7.1 Architecture Overview

Becker-Asano and Wachsmuth (2010) developed WASABI (Wasabi Affect Simulation for Agents with Believable Interactivity) for the virtual agent "Max." WASABI represents one of the most complete implementations of the mood-emotion coupling that our system requires.

**Core principles of WASABI**:

1. **Mood is a mass-spring-damper system** in PAD (Pleasure-Arousal-Dominance) space. Mood has inertia -- it resists change. When pushed by emotional events, it oscillates and gradually settles toward a personality-determined equilibrium point. The damping coefficient determines how quickly mood stabilizes. [Theory]

2. **Emotions are discrete, short-lived events** generated by cognitive appraisal (using a simplified OCC model). Each emotion has an intensity that peaks at onset and decays exponentially. [Theory]

3. **Mood-emotion coupling is bidirectional**:
   - Emotions influence mood: each emotional event applies a force to the mood mass-spring system in the direction of the emotion's PAD coordinates.
   - Mood influences emotions: the current mood position biases which emotions are more easily triggered (mood congruence) and modulates their intensity. [Theory]

4. **Mood is "diffuse"** -- it does not correspond to any single discrete emotion. A slightly negative, low-arousal mood is not "sadness" -- it is a background state that makes sadness easier to trigger and joy harder. The agent does not display mood directly; mood modulates the emotional responses that are displayed. [Theory]

**Implementation detail**: WASABI uses a second-order ODE for mood dynamics (mass-spring-damper), which produces oscillatory behavior. Our system uses a first-order ODE (exponential decay). The key difference is that WASABI's mood can overshoot equilibrium (a burst of positive emotion can push mood past the baseline and briefly into negative territory during oscillation), while our first-order system approaches baseline monotonically. [Theory]

**Relevance to our design**: The mass-spring-damper model is more physically realistic but harder to tune and can produce counterintuitive oscillations (mood briefly going negative after a positive event). The first-order decay model is simpler and more predictable, which matters for a child-facing robot where unexpected mood swings are undesirable. However, we should consider adding a small amount of overshoot damping to prevent the "perfect asymptotic approach" that makes the decay visually obvious. [Inference]

**Citation**: Becker-Asano, C., & Wachsmuth, I. (2010). Affective computing with primary and secondary emotions in a virtual human. *Autonomous Agents and Multi-Agent Systems*, 20(1), 32-49.

### 7.2 WASABI's Mood Decay in Practice

WASABI provides specific implementation details useful for our parameter tuning:

- **Mood decay time constant**: Approximately 5-10 minutes for the mood to return to baseline after a strong emotional event. This is controlled by the damping coefficient of the mass-spring system. [Theory]

- **Emotion decay time constant**: Approximately 5-20 seconds for individual emotions to fade. Different emotion categories have different decay rates. [Theory]

- **Coupling strength**: The influence of a single emotional event on mood is typically 10-30% of the emotion's peak intensity. Multiple events accumulate. A sustained sequence of positive emotions shifts mood significantly; a single positive event barely moves it. [Theory]

**Mapping to our system**: If our phasic (emotion) integrator has a half-life of 5-30 seconds (depending on emotion type), and our tonic (mood) integrator has a half-life of 10-30 minutes, this produces coupling dynamics similar to WASABI's mass-spring system without the oscillatory complexity. The coupling strength (how much each emotional event shifts mood) should be approximately 15-25% of the emotion's impulse magnitude. [Inference]

---

## 8. Marsella & Gratch: Computational Emotion with Memory

### 8.1 EMA: Emotion and Adaptation

Marsella and Gratch (2009) developed EMA (EMotion and Adaptation), a computational model that integrates emotion generation, memory, and coping processes. EMA is the most complete model of how emotional memory influences future emotional responses.

**Key contributions relevant to our design**:

1. **Appraisal-driven emotion generation**: Emotions are not arbitrary labels selected by a pattern-matcher. They arise from cognitive appraisal of events against the agent's goals, standards, and expectations. Each appraisal dimension (goal relevance, goal congruence, agency, certainty) contributes to the emotion type and intensity. [Theory]

2. **Continuous reappraisal**: Unlike simpler models where emotion is generated once and then decays, EMA continuously reappraises the significance of events as the agent's internal state and external context change. An event that initially seemed threatening may be reappraised as manageable after coping, reducing the associated fear. [Theory]

3. **Memory as emotional context**: Past appraisals are stored and influence future appraisals. If the agent previously appraised a situation as threatening and the outcome was negative, a similar future situation triggers faster, stronger fear. Conversely, if the outcome was positive, fear is attenuated. This is **emotional learning** -- the agent's emotional responses evolve based on experience. [Theory]

4. **Coping processes**: EMA models active coping -- the agent takes mental or behavioral action to manage emotional distress. Coping strategies include problem-focused coping (taking action to change the situation), emotion-focused coping (reappraising the event to reduce its emotional impact), and acceptance. [Theory]

**Relevance to our design**: Full EMA-style appraisal and coping are beyond our scope for the initial personality engine. However, two EMA concepts are directly applicable:

- **Emotional priming through memory**: Stored affective traces should influence the gain of new impulses. If the last session ended with the child feeling sad, the robot's empathetic responsiveness (gain for negative-valence impulses) should be slightly elevated at the start of the next session. This is implementable through the mood layer -- cross-session memory biases the mood vector at session start. [Inference]

- **Context-dependent appraisal**: The same event (e.g., child says "I don't want to play") should produce different emotional responses depending on accumulated context. If this is the first time, it might produce mild confusion. If it follows multiple negative statements, it should produce empathetic concern. The LLM handles this in Layer 1, but Layer 0 can approximate it by tracking impulse frequency in a sliding window. [Inference]

**Citation**: Marsella, S. C., & Gratch, J. (2009). EMA: A process model of appraisal dynamics. *Cognitive Systems Research*, 10(1), 70-90.

### 8.2 Memory and Appraisal Integration

Marsella and Gratch's key insight for memory design is that **emotional memory should not store emotions -- it should store appraisal frames**. An appraisal frame captures the *reason* for an emotion (what event happened, what goal was threatened, how the agent coped), not just the emotion itself. [Theory]

**For our system**: This argues against storing raw valence/arousal values as cross-session memory. Instead, store **semantic tags with emotional coloring**:

- Not: `{valence: -0.4, arousal: 0.3, time: "2026-02-20"}`
- Instead: `{tag: "child_expressed_sadness", topic: "friend_moved_away", robot_response: "empathetic_concern", session: 15, decay_tier: T3}`

The semantic tag enables the LLM (Layer 1) to construct appropriate context for future interactions, while the emotional coloring enables the personality worker (Layer 0) to bias the affect vector at session start. [Inference]

---

## 9. Recommended Half-Lives and Lambda Values

### 9.1 Phasic Layer (Within-Session Emotion Decay)

Based on D'Mello & Graesser's empirical data, WASABI's implementation parameters, TAME's validation studies, and our child-age scaling factor (0.5-0.75x adult values):

| Affect Type | Half-Life | Lambda (/s) | Source | Notes |
|-------------|-----------|-------------|--------|-------|
| **Surprise/delight impulse** | 3-5 s | 0.14-0.23 | D'Mello & Graesser (2011) [Empirical] | Very fast -- surprise is punctual, not sustained |
| **Frustration/annoyance** | 15-30 s | 0.023-0.046 | D'Mello & Graesser (2011) [Empirical] | Moderate -- should not linger but should not vanish instantly |
| **Sadness/empathetic concern** | 30-90 s | 0.008-0.023 | Inference from therapy norms + D'Mello data | Slow enough for 3+ turns of emotional carry-over |
| **Joy/positive engagement** | 20-60 s | 0.012-0.035 | D'Mello (2012) engagement data [Empirical] | Asymmetric: positive decays slower than equivalent negative |
| **Curiosity/interest** | 10-20 s | 0.035-0.069 | Inference from engagement/confusion data | Moderate -- curiosity is self-renewing if stimulated |
| **Confusion/thinking** | 8-15 s | 0.046-0.087 | D'Mello & Graesser (2012) [Empirical] | Fast -- confusion should resolve quickly (productive or not) |
| **Fear/scared** | 5-10 s | 0.069-0.139 | Inference -- child safety design | Very fast decay for negative high-arousal states |

**Asymmetric decay implementation**: The personality spec (B.2, Bucket 1 Findings) recommends `lambda_positive = lambda_base * 0.85` and `lambda_negative = lambda_base * 1.30`. This means positive emotions linger approximately 50% longer than equivalent negative emotions at the same base decay rate. [Inference]

### 9.2 Tonic Layer (Mood Decay)

| Mood Type | Half-Life | Lambda (/s) | Source | Notes |
|-----------|-----------|-------------|--------|-------|
| **Positive mood shift** | 15-30 min | 0.0004-0.0008 | WASABI implementation [Theory] | Mood should persist across conversation gaps |
| **Negative mood shift** | 10-20 min | 0.0006-0.0012 | WASABI + asymmetric design [Inference] | Faster than positive -- emotional resilience model |
| **Post-conversation residual** | 2-5 min | 0.0023-0.0058 | Bucket 4 idle catalog [Inference] | Smooth transition from conversation emotion to idle |
| **Session-opening bias** | 5-10 min | 0.0012-0.0023 | Inference from cross-session memory | Mood at session start biased by last session tone |

### 9.3 Coupled Integrator Parameters

The coupling between phasic and tonic layers requires additional parameters:

| Parameter | Value | Meaning |
|-----------|-------|---------|
| **Emotion-to-mood coupling** | 0.15-0.25 | Each emotional impulse contributes 15-25% of its magnitude to the mood layer [Inference -- from WASABI] |
| **Mood congruence bias** | 0.10-0.20 | Current mood modulates impulse gain by +/-10-20% for congruent/incongruent emotions [Theory -- from ALMA] |
| **Mood-to-baseline decay** | 10-30 min half-life | Mood drifts toward personality baseline [Theory -- convergent across ALMA, TAME, WASABI] |
| **Emotion-to-mood decay** | 5-30 s half-life | Emotion drifts toward current mood (not directly toward baseline) [Theory -- ALMA coupling model] |

**Implementation note**: The two-integrator coupling means that emotion decays toward mood, not toward the static personality baseline. Only mood decays toward the baseline. This creates a key behavioral signature: after a series of positive events, individual positive emotions decay quickly (phasic), but the mood stays elevated (tonic), which means subsequent positive emotions are slightly easier to trigger and the next neutral turn still "feels" positive. [Inference]

---

## 10. Memory Structure Recommendations

### 10.1 Within-Session Memory Structure

```python
@dataclass(slots=True)
class AffectiveTrace:
    """A single emotionally significant event within a session."""
    timestamp: float            # session-relative time (seconds)
    source: str                 # "llm_emotion", "system_event", "child_affect"
    valence_bias: float         # direction: -1.0 to +1.0
    arousal_bias: float         # direction: -1.0 to +1.0
    initial_magnitude: float    # starting strength: 0.0 to 1.0
    decay_rate: float           # lambda for this trace (per-second)
    context_tag: str            # semantic label: "child_sad", "shared_joke", etc.

    def current_strength(self, now: float) -> float:
        """Exponential decay from initial magnitude."""
        dt = now - self.timestamp
        return self.initial_magnitude * math.exp(-self.decay_rate * dt)
```

**Session trace pool**: Maximum 20 active traces per session. When the pool is full, the trace with the lowest `current_strength` is evicted. At session end, all traces are cleared (within-session memory is ephemeral). [Inference]

**Significant event threshold**: Not every LLM emotion suggestion creates a trace. Only impulses with magnitude above 0.15 (on a 0-1 scale) should create traces. This prevents trace pool exhaustion from trivial emotional fluctuations. [Inference]

### 10.2 Cross-Session Memory Structure

```python
@dataclass(slots=True)
class PersistentMemory:
    """A cross-session memory item with decay."""
    memory_id: str              # unique identifier
    created_session: int        # session number when first formed
    last_reinforced: float      # Unix timestamp of last reinforcement
    decay_tier: int             # T0-T5 (see Section 6.4)
    content_type: str           # "name", "topic", "ritual", "session_tone", "detail", "preference"
    content_tag: str            # semantic label: "dinosaurs", "guessing_game", etc.
    valence_color: float        # emotional coloring: -1.0 to +1.0
    arousal_color: float        # emotional coloring: -1.0 to +1.0
    reinforcement_count: int    # number of times referenced/reinforced
    initial_strength: float     # strength at creation or last reinforcement

    def current_strength(self, now: float) -> float:
        """Decay depends on tier."""
        dt_days = (now - self.last_reinforced) / 86400.0
        if self.decay_tier == 0:  # T0: Identity -- never decays
            return self.initial_strength
        elif self.decay_tier <= 2:  # T1-T2: Power-law decay
            alpha = TIER_ALPHA[self.decay_tier]
            beta = TIER_BETA[self.decay_tier]
            return self.initial_strength * (1 + beta * dt_days) ** (-alpha)
        else:  # T3-T5: Exponential decay
            lam = TIER_LAMBDA[self.decay_tier]
            return self.initial_strength * math.exp(-lam * dt_days)
```

**Storage**: JSON file on local filesystem (no database required for the expected volume of ~50-100 memory items). File is loaded at supervisor startup and saved at session end. Never transmitted to the server -- only anonymized semantic tags are sent to the LLM as context. [Inference]

**Parental access**: The dashboard must provide a "Memory" panel showing all persistent memories with their current strength, and a "Clear Memory" button that deletes all persistent data. Per-item deletion should also be supported. [Inference -- constrained by COPPA]

### 10.3 Session-Start Memory Activation

At the start of each session, the personality worker should:

1. **Load persistent memories** from storage.
2. **Prune dead memories** (current_strength < 0.05).
3. **Compute session-opening mood bias**: Average the `valence_color` and `arousal_color` of the top 3-5 strongest memories, weighted by current strength. Apply this as a gentle impulse to the tonic (mood) integrator, magnitude capped at 0.15. [Inference]
4. **Construct LLM context**: Format the top 5-10 strongest memories as a structured block for inclusion in the LLM system prompt. Example: `"Persistent memory: Child's name is Emma. She likes dinosaurs and space. We played a guessing game last time. Last session was fun and energetic."` [Inference]

---

## 11. Design Recommendations

### 11.1 Two-Integrator Architecture

**Recommendation**: Implement two coupled integrators (phasic emotion + tonic mood) rather than a single affect vector.

Evidence chain:
1. ALMA, TAME, WASABI, and Kismet all converge on a two-layer temporal separation. [Theory -- convergent across four major architectures]
2. D'Mello's empirical data shows emotions operating on a 5-30 second time scale while overall affective disposition shifts on a minute-to-hour scale. [Empirical]
3. A single integrator cannot simultaneously produce fast emotional responsiveness (seconds) and slow mood persistence (minutes) -- the decay rate is a single parameter that trades one against the other. Two coupled integrators resolve this tradeoff. [Inference]

**Formal model** (extends the personality spec C.4):

```
# Phasic layer (emotion): fast decay toward tonic layer
da_e/dt = lambda_e * (a_m - a_e) + Sigma_k i_k * delta(t - t_k)

# Tonic layer (mood): slow decay toward personality baseline
da_m/dt = lambda_m * (b - a_m) + gamma * Sigma_k i_k * delta(t - t_k)

# Where:
#   a_e = emotion vector (valence, arousal)
#   a_m = mood vector (valence, arousal)
#   b   = personality baseline (static)
#   lambda_e = emotion decay rate (~0.02-0.15 /s, varies by emotion type)
#   lambda_m = mood decay rate (~0.0005-0.001 /s)
#   gamma = emotion-to-mood coupling strength (~0.15-0.25)
#   i_k  = impulse at time t_k
```

**Face projection uses the emotion layer** (a_e), not the mood layer. The mood layer is invisible to the child -- it operates behind the scenes to bias emotional dynamics. [Inference]

### 11.2 Cross-Session Memory: Needed but Minimal

**Recommendation**: Implement PE-2 Option C (persistent memory), but constrained to the minimum viable memory set.

Evidence chain:
1. Ligthart et al. (2022) demonstrates that cross-session memory is the mechanism that sustains engagement past the novelty cliff (sessions 4-7). [Empirical]
2. Kanda et al. (2004) demonstrates that personal remarks based on interaction history sustain relationships in longitudinal deployment. [Empirical]
3. Session-scoped memory (PE-2 Option B) provides within-session coherence but not relationship continuity. [Inference]
4. The minimum viable memory is small (name, 1-2 topics, shared ritual, session tone) and can be implemented as a simple JSON file with mandatory decay tiers. [Inference]

**Privacy constraints**:
- All data local, never transmitted to server (COPPA + HC-7). [Empirical -- regulatory]
- Only child-volunteered information stored (HC-6). [Inference]
- Mandatory decay tiers with automatic pruning. [Inference]
- Full parental visibility and deletion capability via dashboard. [Inference]
- Frame all memory retrieval as shared experience, not surveillance. [Inference]

### 11.3 Decay Parameter Tuning Priority

The research identifies decay rate (lambda) as the single most important personality parameter:

1. **TAME validation**: Observers distinguished personalities primarily through emotional recovery time -- how long the robot stayed in a state after the triggering event. [Empirical]
2. **D'Mello's data**: Different emotions have genuinely different persistence profiles. A single lambda for all emotions produces flat, undifferentiated affect dynamics. [Empirical]
3. **Asymmetric decay** is critical for a children's robot: positive emotions should linger, negative emotions should resolve quickly. This models emotional resilience and prevents the robot from displaying prolonged distress. [Inference]

**Tuning recommendation**: Start with the half-lives in Section 9.1, implement per-emotion-type lambda values, and tune empirically using the evaluation framework from the personality spec (C.6). The arc coherence ratio and arc smoothness metrics will reveal whether decay rates produce natural-feeling emotional dynamics. [Inference]

### 11.4 Memory Decay Tier Summary

For reference, the complete memory decay tier table:

| Tier | Content | Model | Half-Life | Reinforcement Behavior |
|------|---------|-------|-----------|----------------------|
| **T0** | Child's name | Never decays | -- | N/A |
| **T1** | Shared rituals, recurring games | Power-law | ~60-90 days | Referenced ritual resets timer |
| **T2** | Favorite topics, interests | Power-law | ~14-28 days | Re-mentioned topic resets timer, may upgrade to T1 after 3 references |
| **T3** | Session emotional tone | Exponential | ~7-14 days | Replaced each session (only most recent 3 sessions stored) |
| **T4** | Specific conversation details | Exponential | ~3-5 days | Not reinforced -- fades naturally |
| **T5** | Inferred preferences | Exponential | ~1-3 days | Not reinforced -- fades naturally; fastest decay for privacy |

### 11.5 Implementation Phasing

Cross-session memory can be implemented incrementally:

**Phase A (with personality engine v1)**: Session-scoped memory only. Affective traces within conversation, cleared at session end. The phasic+tonic integrator operates purely on within-session data. This addresses emotional amnesia (failure mode 1) and emotional arc (failure mode 6) without any persistent storage.

**Phase B (after 1-2 weeks of testing)**: Add persistent memory tiers T0-T2. Store child's name, topics, and rituals. LLM receives these as context. The mood integrator receives a session-opening bias based on stored memories. This addresses relationship continuity.

**Phase C (after parental review)**: Add persistent memory tiers T3-T5. Session tone, conversation details, inferred preferences. These are the most privacy-sensitive tiers and should only be enabled after parental opt-in and dashboard transparency features are complete.

---

## Sources

- [D'Mello, S. K., & Graesser, A. C. (2012). Dynamics of affective states during complex learning. *Learning and Instruction*, 22(2), 145-157.](https://doi.org/10.1016/j.learninstruc.2011.09.001)
- [D'Mello, S. K., & Graesser, A. C. (2011). The half-life of cognitive-affective states during complex learning. *Cognition & Emotion*, 25(7), 1299-1308.](https://doi.org/10.1080/02699931.2010.544160)
- [Gebhard, P. (2005). ALMA -- A Layered Model of Affect. *AAMAS '05*, 29-36.](https://doi.org/10.1145/1082473.1082478)
- [Moshkina, L., & Arkin, R. C. (2005). Human perspective on affective robotic behavior. *IROS 2005*, 1444-1451.](https://doi.org/10.1109/IROS.2005.1545281)
- [Moshkina, L., & Arkin, R. C. (2011). TAME: Time-varying affective response for humanoid robots. *International Journal of Social Robotics*, 3(3), 207-221.](https://doi.org/10.1007/s12369-011-0090-2)
- [Breazeal, C. (2003). Emotion and sociable humanoid robots. *International Journal of Human-Computer Studies*, 59(1-2), 119-155.](https://doi.org/10.1016/S1071-5819(03)00018-1)
- [Becker-Asano, C., & Wachsmuth, I. (2010). Affective computing with primary and secondary emotions in a virtual human. *Autonomous Agents and Multi-Agent Systems*, 20(1), 32-49.](https://doi.org/10.1007/s10458-009-9094-9)
- [Marsella, S. C., & Gratch, J. (2009). EMA: A process model of appraisal dynamics. *Cognitive Systems Research*, 10(1), 70-90.](https://doi.org/10.1016/j.cogsys.2008.03.005)
- [Ligthart, M. E. U., Lexis, M. A. S., de Graaf, M. M. A., & Hindriks, K. V. (2022). Memory-based personalization in child-robot interaction. *Frontiers in Robotics and AI*, 9, 819033.](https://doi.org/10.3389/frobt.2022.819033)
- [Kanda, T., Hirano, T., Eaton, D., & Ishiguro, H. (2004). Interactive robots as social partners and peer tutors for children: A field trial. *Human-Computer Interaction*, 19(1-2), 61-84.](https://doi.org/10.1080/07370024.2004.9667340)
- [Kuppens, P., Allen, N. B., & Sheeber, L. B. (2010). Emotional inertia and psychological maladjustment. *Psychological Science*, 21(7), 984-991.](https://doi.org/10.1177/0956797610372634)
- [Eisenberg, N., Spinrad, T. L., & Eggum, N. D. (2010). Emotion-related self-regulation and its relation to children's maladjustment. *Annual Review of Clinical Psychology*, 6, 495-525.](https://doi.org/10.1146/annurev-clinpsy-032408-153553)
- [Davidson, R. J. (1998). Affective style and affective disorders. *Cognition & Emotion*, 12(3), 307-330.](https://doi.org/10.1080/026999398379628)
- [McGaugh, J. L. (2004). The amygdala modulates the consolidation of memories of emotionally arousing experiences. *Annual Review of Neuroscience*, 27, 1-28.](https://doi.org/10.1146/annurev.neuro.27.070203.144157)
- [Wixted, J. T., & Ebbesen, E. B. (1991). On the form of forgetting. *Psychological Science*, 2(6), 409-415.](https://doi.org/10.1111/j.1467-9280.1991.tb00175.x)
- [Ebbinghaus, H. (1885/1913). *Memory: A contribution to experimental psychology*. Teachers College, Columbia University.](https://psychclassics.yorku.ca/Ebbinghaus/index.htm)
- [Gonzales, A. L., Hancock, J. T., & Pennebaker, J. W. (2010). Language style matching as a predictor of social dynamics in small groups. *Communication Research*, 37(1), 3-19.](https://doi.org/10.1177/0093650209351468)
- [Yadav, K., et al. (2016). Understanding children's interactions with conversational agents. *CHI EA '16*, 2480-2486.](https://doi.org/10.1145/2851581.2892374)
- [Luger, E., & Sellen, A. (2016). "Like having a really bad PA": The gulf between user expectation and experience of conversational agents. *CHI '16*, 5286-5297.](https://doi.org/10.1145/2858036.2858288)
- [Ortony, A., Clore, G. L., & Collins, A. (1988). *The Cognitive Structure of Emotions*. Cambridge University Press.](https://doi.org/10.1017/CBO9780511571299)
- [Mehrabian, A. (1996). Pleasure-arousal-dominance: A general framework for describing and measuring individual differences in temperament. *Current Psychology*, 14, 261-292.](https://doi.org/10.1007/BF02686918)
- [Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6), 1161-1178.](https://doi.org/10.1037/h0077714)
- [Landreth, G. L. (2012). *Play Therapy: The Art of the Relationship* (3rd ed.). Routledge.](https://doi.org/10.4324/9780203835159)
