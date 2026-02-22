# Bucket 1: Temperament & Personality Models for Social Robots

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-1 (Trait-to-Affect-Vector Parametrization) and personality axis mapping decisions

---

## Table of Contents

1. [Big Five Personality Model Adapted for Social Robots](#1-big-five-personality-model-adapted-for-social-robots)
2. [TAME Architecture: Traits, Attitudes, Moods, and Emotions](#2-tame-architecture-traits-attitudes-moods-and-emotions)
3. [Kismet: Homeostatic Drive Model](#3-kismet-homeostatic-drive-model)
4. [Dimensional Emotion Models: Russell's Circumplex](#4-dimensional-emotion-models-russells-circumplex)
5. [Appraisal Theory: Scherer's Component Process Model](#5-appraisal-theory-scherers-component-process-model)
6. [Mapping Functions: Traits to Affect Vector Parameters](#6-mapping-functions-traits-to-affect-vector-parameters)
7. [Tapus & Mataric: Adaptive Personality Matching](#7-tapus--mataric-adaptive-personality-matching)
8. [VA Space Mood Anchor Table](#8-va-space-mood-anchor-table)
9. [Parameter Mapping Recommendations](#9-parameter-mapping-recommendations)
10. [Design Recommendations](#10-design-recommendations)

---

## 1. Big Five Personality Model Adapted for Social Robots

### 1.1 The Big Five Foundation

The Five-Factor Model (FFM), commonly known as the Big Five, is the dominant taxonomy for human personality in psychology. McCrae & Costa (1997) established its five dimensions through decades of factor-analytic research across cultures:

1. **Openness to Experience** -- intellectual curiosity, aesthetic sensitivity, imagination
2. **Conscientiousness** -- orderliness, self-discipline, goal-directed behavior
3. **Extraversion** -- sociability, assertiveness, positive emotionality, activity level
4. **Agreeableness** -- altruism, trust, compliance, tenderness
5. **Neuroticism** -- anxiety, emotional volatility, negative affectivity

Each dimension has six facets. For robot personality, not all facets are equally observable. A robot with no body cannot display physical activity level; a robot with no social group cannot display gregariousness. The key insight is that only **behaviorally observable** facets matter for robot personality design. [Theory]

**Citation**: McCrae, R. R., & Costa, P. T. (1997). Personality trait structure as a human universal. *American Psychologist*, 52(5), 509-516.

### 1.2 Big Five to Robot Behavior: What Translates?

Robert (2018) conducted a systematic review of personality in human-robot interaction and identified which Big Five traits produce **perceivable behavioral differences** in robots:

- **Extraversion** is the most reliably perceived trait in robots. It maps to speech rate, movement amplitude, gesture frequency, and initiative-taking. Both adults and children can distinguish extraverted from introverted robot behavior after brief exposure. [Empirical]

- **Neuroticism** (or its inverse, Emotional Stability) is perceived through emotional recovery patterns -- how quickly the robot returns to baseline after a perturbation. High-neuroticism robots linger in negative states; low-neuroticism robots bounce back quickly. This is perceived primarily through duration rather than intensity. [Empirical]

- **Agreeableness** is perceived through compliance, warmth, and conflict avoidance. Agreeable robots use more positive emotional expressions and fewer negative ones. In child-robot interaction, agreeableness maps most directly to the robot's willingness to mirror and validate the child's emotional state. [Empirical]

- **Conscientiousness** manifests primarily in behavioral regularity and predictability. For a robot, this is less about "personality" and more about "reliability." [Empirical]

- **Openness** has weak behavioral correlates in robots -- partially expressed through curiosity behaviors but easily confounded with Extraversion. [Inference]

**Key finding for our design**: Extraversion and Neuroticism are the two traits that most reliably produce perceivable personality differences in robots. Our five axes should be strongly informed by these two Big Five dimensions. [Inference]

**Citation**: Robert, L. P. (2018). Personality in the human robot interaction literature: A review and brief critique. *Proceedings of the 24th Americas Conference on Information Systems (AMCIS)*.

### 1.3 Mapping Big Five to Our Five Axes

Our robot has five personality axes, each at a defined position. Here is how they map to the Big Five and which behavioral channels carry each trait:

| Our Axis | Position | Big Five Mapping | Primary Facets | Observable Through |
|----------|----------|-----------------|----------------|-------------------|
| **Energy Level** | 0.40 | Extraversion (activity/enthusiasm) | Activity level, positive emotionality | Baseline arousal, gesture frequency, transition speed |
| **Emotional Reactivity** | 0.50 | Neuroticism (inverted: 0.50 = moderate stability) | Emotional volatility, impulse responsiveness | Impulse magnitude, decay rate, emotional range |
| **Social Initiative** | 0.30 | Extraversion (assertiveness) | Assertiveness, sociability, approach behavior | Proactive behavior frequency, idle expression, initiative triggers |
| **Vulnerability Display** | 0.35 | Agreeableness (tenderness/trust) | Self-disclosure, empathy display, negative affect visibility | Negative valence cap, empathy mirroring depth |
| **Predictability** | 0.75 | Conscientiousness (order/deliberation) | Behavioral consistency, response regularity | Noise amplitude, cosmetic variation bounds |

**Not independent axes**: Openness is partially captured by Energy and Reactivity; it is not independent because curiosity is role-defined (caretaker is always curious about the child). Dominance is a relational role constraint [S1-C2], not a personality axis. [Inference]

**Citation**: McCrae, R. R., & Costa, P. T. (2008). The Five-Factor Theory of personality. In O. P. John, R. W. Robins, & L. A. Pervin (Eds.), *Handbook of personality: Theory and research* (3rd ed., pp. 159-181). Guilford Press.

---

## 2. TAME Architecture: Traits, Attitudes, Moods, and Emotions

### 2.1 Architecture Overview

Moshkina & Arkin (2005, 2011) developed the TAME (Traits, Attitudes, Moods, and Emotions) architecture as a computational framework for robot personality and affect. TAME is the most directly relevant prior work to our personality engine because it explicitly separates personality traits from emotional dynamics and defines how traits parameterize the emotion system. [Theory]

TAME defines four layers of affect, each with different temporal dynamics:

| Layer | Name | Temporal Scale | Update Source |
|-------|------|---------------|---------------|
| **Traits** | Stable personality dimensions | Permanent (operator-defined) | Never changes during operation |
| **Attitudes** | Disposition toward specific objects/situations | Hours to days | Accumulated experience with specific stimuli |
| **Moods** | Diffuse background affective state | Minutes to hours | Accumulated emotional residue + trait bias |
| **Emotions** | Short-term responses to specific events | Seconds to minutes | Direct stimulus appraisal |

The key architectural insight is that **higher layers constrain lower layers**: traits bias mood computation, moods bias emotion computation, and emotions produce observable behavior. Information flows top-down (traits --> moods --> emotions --> behavior) and bottom-up (emotions accumulate into moods, moods inform attitude formation). [Theory]

**Citation**: Moshkina, L., & Arkin, R. C. (2005). Human perspective on affective robotic behavior: A longitudinal study. In *Proceedings of the 2005 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)* (pp. 1444-1451).

### 2.2 How TAME Maps Big Five to Affect Parameters

TAME uses Big Five traits to parameterize mood and emotion computation. The two most impactful mappings:

- **Extraversion** --> increases baseline valence (more positive resting mood), amplifies positive impulse gain, increases approach/initiative probability, raises arousal baseline
- **Neuroticism** --> reduces decay rate for negative emotions (they linger), amplifies negative impulse gain, widens emotional range, increases mood susceptibility to single events

Secondary mappings: **Agreeableness** increases empathy mirroring gain and reduces negative expression. **Conscientiousness** reduces stochastic variation and increases behavioral regularity. **Openness** increases curiosity impulse magnitude and broadens stimulus responsiveness. [Theory -- derived from Moshkina & Arkin's published parameter framework]

### 2.3 TAME Parameter Mapping Patterns

The specific parameter mappings from TAME that are most relevant to our decaying integrator model:

**Decay rate scaling by Neuroticism**:
```
lambda_effective = lambda_base * (1 - k_n * neuroticism)
```
Where k_n is a scaling constant (typically 0.3-0.5). Higher Neuroticism means slower decay -- negative emotions linger. For our Reactivity axis at 0.50 (moderate), this produces near-baseline decay rates, which is the intended "moderate responsiveness." [Theory]

**Impulse gain scaling by Neuroticism and Extraversion**:
```
impulse_positive = impulse_base * (1 + k_e * extraversion)
impulse_negative = impulse_base * (1 + k_n * neuroticism)
```
Where k_e and k_n are in [0.5, 1.5]. This creates asymmetric impulse sensitivity: extraverted robots respond more strongly to positive events, neurotic robots respond more strongly to negative events. [Theory]

**Baseline offset by Extraversion**:
```
baseline_valence = baseline_neutral + w_e * extraversion - w_n * neuroticism
```
Where weights w_e and w_n are typically 0.1-0.3. This shifts the resting mood: extraverted robots rest at slightly positive valence, neurotic robots rest at slightly negative. For our system, Energy (0.40, mapping to Extraversion) and Reactivity (0.50, inverse-mapping to Neuroticism) produce a near-neutral but slightly positive baseline. [Theory]

### 2.4 TAME Perception Studies

Moshkina & Arkin (2005) conducted participant studies to test whether humans could perceive personality differences in robots configured with different TAME trait settings:

- **Participants could reliably distinguish** between high-Extraversion and low-Extraversion robot configurations. The distinction was perceived primarily through activity level, initiative frequency, and positive affect display. [Empirical]

- **Neuroticism was perceived** primarily through emotional recovery time -- how long the robot stayed in a startled or distressed state after a perturbation event. Participants did not reliably identify "neuroticism" by name but described high-neuroticism robots as "jittery," "nervous," or "anxious." [Empirical]

- **The multilayer separation** (traits biasing moods biasing emotions) produced more coherent behavior than direct trait-to-behavior mapping. When traits directly controlled behavior (bypassing the mood layer), the robot's actions appeared more erratic and harder for participants to form a personality impression. [Empirical]

- **Perception improved over time**: longer exposure (multiple sessions) produced more accurate personality attribution. Brief interactions were insufficient for reliable perception of all traits beyond Extraversion. [Empirical]

**Citation**: Moshkina, L., & Arkin, R. C. (2011). TAME: Time-varying affective response for humanoid robots. *International Journal of Social Robotics*, 3(3), 207-221.

### 2.5 TAME Limitations

1. **Hand-tuned parameters**: The mapping constants (k_n, k_e, w_e, w_n) were hand-tuned with no published sensitivity analysis. Small changes produce qualitatively different behavior. [Empirical]

2. **Attractor basin brittleness**: Certain trait configurations become "trapped" in mood states requiring unrealistically strong impulses to escape -- especially problematic for negative moods with high-Neuroticism settings. [Empirical]

3. **No developmental validation with children**: Studies used adults only. Children ages 4-6 have less differentiated personality perception ("nice" vs "mean" rather than five dimensions) -- TAME's model may be over-specified for our audience. [Inference]

4. **Static attitudes**: The attitude layer was under-developed. For our system, this gap maps to the emotional memory question (PE-2). [Theory]

---

## 3. Kismet: Homeostatic Drive Model

### 3.1 Architecture Overview

Breazeal's Kismet (2003) is one of the most extensively documented social robot emotion systems. Kismet uses a **homeostatic drive model** where internal drives (social stimulation, fatigue, play) drift from equilibrium over time, creating an intrinsic motivation for behavior. [Empirical]

The emotion system has three components:

1. **Drive system**: Three drives (social, stimulation, fatigue) each have a desired equilibrium level. Deviation from equilibrium creates behavioral pressure. Drives influence emotion but are not emotions themselves.

2. **Emotion system**: Six proto-emotions (anger, disgust, fear, joy, sorrow, surprise) are activated by appraisal of perceptual stimuli, modulated by the current drive state. Emotions are represented as points in a three-dimensional space (valence, arousal, stance).

3. **Behavior system**: Emotions and drives together produce behavioral outputs (facial expression, motor behavior, vocalization) through a behavior arbitration system that selects the highest-activation behavior.

**Citation**: Breazeal, C. (2003). Emotion and sociable humanoid robots. *International Journal of Human-Computer Studies*, 59(1-2), 119-155.

### 3.2 Smooth Transitions in VA Space

Breazeal explicitly rejected discrete emotion switching in favor of continuous movement through affect space. [Empirical]

- **Continuous movement through VA space** looked significantly more natural than discrete switching. Observers described smooth transitions as "lifelike" and abrupt switches as "mechanical." [Empirical]

- **Transition speed was state-dependent**: transitions into high-arousal states (surprise, excitement) were faster than transitions into low-arousal states (sadness, sleepiness). This asymmetry matches human emotional dynamics. [Theory]

- **Tuned attractor regions**: each proto-emotion occupied a basin in affect space. The current state was attracted toward the nearest active basin with strength proportional to activation level. [Theory]

**Design implication**: The decaying integrator model naturally produces smooth transitions -- architecturally equivalent to Kismet's continuous transitions without requiring an explicit attractor-basin mechanism. The integrator IS the smooth transition mechanism. [Inference]

### 3.3 Naturalistic Behavior Cycling

Kismet's homeostatic drives produced a characteristic cycling pattern even without external stimulation:

1. **Engage**: Social drive satisfied, stimulation drive rising --> curious, attentive behavior
2. **Tire**: Fatigue drive rising, stimulation drive saturated --> reduced responsiveness, slower reactions
3. **Disengage**: Fatigue drive dominant --> eyes close, withdrawal behavior, "sleep" mode
4. **Seek**: After rest, social drive unsatisfied --> renewed seeking behavior, approach orientation

This cycling produced the appearance of an autonomous "life cycle" that observers found compelling. The robot appeared to have genuine internal states rather than merely reacting to stimuli. [Empirical]

**Relevance to our design**: This cycle maps directly to our idle behavior catalog (Bucket 4 Section 3.3): boot CURIOUS --> short idle CONTENT --> medium idle SLEEPY --> long idle deep SLEEPY. The key difference is that our robot at Social Initiative 0.30 does NOT complete the cycle by seeking engagement. It rests until the child initiates. The cycle is truncated: engage --> tire --> disengage --> rest (no seek). [Inference]

### 3.4 Limitations

1. **Hand-tuned attractor basins**: Small parameter changes caused unnatural oscillation between emotions -- visible as unsettling facial twitching when two basins had similar activation levels. [Empirical]

2. **No persistent memory**: Each session started from the same equilibrium. No relationship history. Breazeal identified this as a primary weakness for long-term interaction. [Empirical]

3. **Over-engagement seeking**: When understimulated, Kismet sought engagement through increasingly dramatic emotional displays (progressing to visible sadness/distress). Incompatible with our HC-5 constraint and Social Initiative 0.30. [Inference -- constrained by Bucket 0 HC-5]

4. **Binary engagement model**: Kismet either had a person or did not -- no graduated engagement (child nearby but not interacting, child playing independently). Our system requires more nuanced context. [Inference]

---

## 4. Dimensional Emotion Models: Russell's Circumplex

### 4.1 The Circumplex Model of Affect

Russell (1980) proposed that all affective states can be described by two orthogonal dimensions:

- **Valence**: pleasure/displeasure (positive/negative)
- **Arousal**: activation/deactivation (high energy/low energy)

These two dimensions form a circular space (the "circumplex") in which specific emotions are arranged. The model argues that categorical emotion labels (happy, sad, angry) are linguistic conveniences mapped onto an underlying continuous dimensional experience. [Theory]

Key claims:

- Affective states are not discrete categories but regions in a continuous two-dimensional space. "Happy" is not a binary state but a region of positive valence and moderate-to-high arousal. [Theory]

- The two dimensions are bipolar and orthogonal. Any affective state can be described by its valence and arousal coordinates. [Theory]

- Categorical emotion labels (anger, fear, joy) correspond to prototypical positions in the VA space, but actual emotional experience can fall anywhere in the continuous space, including between or outside named categories. [Theory]

**Citation**: Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6), 1161-1178.

### 4.2 Neurobiological Support

Posner, Russell, & Peterson (2005) reviewed neuroimaging evidence supporting the dimensional model:

- **Valence** correlates with lateralized prefrontal cortex activation (left = positive, right = negative) and with dopaminergic and serotonergic system activity. [Empirical]

- **Arousal** correlates with reticular activation system, amygdala activation, and autonomic nervous system activity (heart rate, skin conductance). [Empirical]

- **Categorical emotions emerge from dimensional substrates**: discrete emotion categories are not hardwired in the brain but are constructed from dimensional affect + cognitive appraisal + context. This supports using a continuous VA space as the computational substrate with categorical moods as output projections. [Theory]

**Design implication**: The neurobiological evidence validates our architecture -- a continuous affect vector (valence, arousal) as the internal state, projected to categorical moods (12 discrete expressions) at render time. The continuous space is the "truth"; the categorical labels are the display vocabulary. [Inference]

**Citation**: Posner, J., Russell, J. A., & Peterson, B. S. (2005). The circumplex model of affect: An integrative approach to affective neuroscience, cognitive development, and psychopathology. *Development and Psychopathology*, 17(3), 715-734.

### 4.3 Can Categorical and Dimensional Coexist?

A recurring question in emotion modeling is whether to use categorical (discrete labeled emotions) or dimensional (continuous VA space) representations. Our system uses both: dimensional internally, categorical externally. The literature supports this hybrid:

- **Categorical perception aids recognition**: children ages 4-6 recognize categorical labels (happy, sad, angry, scared) much more reliably than dimensional descriptions. They do not think in terms of "positive valence, moderate arousal" -- they think "happy." The categorical face expression is essential for legibility. [Empirical -- Widen & Russell, 2003]

- **Dimensional computation aids dynamics**: smooth transitions, decay toward baseline, impulse stacking, and personality-biased processing all benefit from continuous computation. Discrete emotion switching produces unnatural jumps. [Theory -- Breazeal 2003, Russell 1980]

- **Projection is the bridge**: the affect vector evolves continuously in VA space; at render time, it is projected to the nearest mood anchor (12 discrete moods) with intensity derived from distance to anchor and affect magnitude. This projection is a lossy quantization -- the continuous state is richer than the discrete output -- which is appropriate because the display vocabulary (12 moods on a 320x240 TFT) is inherently limited. [Inference]

**Key design principle**: Compute in dimensional space, display in categorical space. The personality engine operates on (valence, arousal) floats; the face MCU receives a mood ID and intensity byte. The projection function is the interface between these worlds. [Inference]

### 4.4 Limitations and Refinements

- **Dominance as a third dimension**: Mehrabian & Russell (1974) proposed PAD (Pleasure-Arousal-Dominance). For our robot, dominance is role-fixed (caretaker = moderately high dominance) and not face-displayed, so two dimensions suffice. [Theory]

- **Within-quadrant differentiation**: Anger and fear occupy similar VA positions but are expressively distinct. Our 12-mood vocabulary handles this through separate anchors with contextual disambiguation via appraisal (Section 5). [Theory]

- **Cultural variation**: VA coordinates for named emotions vary across cultures, but our single target context (English-speaking, ages 4-6) reduces this concern. [Empirical]

---

## 5. Appraisal Theory: Scherer's Component Process Model

### 5.1 Overview

Scherer (2001) proposed that emotions arise from cognitive evaluation ("appraisal") of events along multiple dimensions, rather than being directly triggered by stimulus categories. The Component Process Model (CPM) defines a sequence of appraisal checks that evaluate an event and produce an emotional response:

1. **Relevance check**: Is this event relevant to me? Does it affect my goals?
2. **Implication check**: What are the consequences? Is the outcome favorable or unfavorable?
3. **Coping potential check**: Can I deal with it? Do I have the resources to respond?
4. **Normative significance check**: Does this event conform to my values and social norms?

Each check produces a partial evaluation. The pattern of evaluations across all checks determines the resulting emotion. For example: relevant + unfavorable + low coping potential = fear; relevant + unfavorable + high coping potential = anger. [Theory]

**Citation**: Scherer, K. R. (2001). Appraisal considered as a process of multilevel sequential checking. In K. R. Scherer, A. Schorr, & T. Johnstone (Eds.), *Appraisal processes in emotion: Theory, methods, research* (pp. 92-120). Oxford University Press.

### 5.2 Fast-Path vs Slow-Path Appraisal

A critical distinction in appraisal theory is between two processing speeds:

**Fast-path (reflex) appraisals** -- automatic, preattentive, completed in under 100ms:
- Sudden loud sound --> relevance: HIGH, implications: THREAT --> arousal spike, negative valence shift
- Face appears in visual field --> relevance: SOCIAL, implications: POSITIVE --> mild positive valence
- Prolonged silence/inactivity --> relevance: LOW, implications: NONE --> arousal decay
- Touch/button press --> relevance: HIGH, implications: INTERACTIVE --> arousal lift, positive valence

These are computationally trivial -- they are essentially stimulus-response rules. They do not require language understanding or contextual reasoning. [Theory]

**Slow-path (deliberate) appraisals** -- require contextual understanding, 200-2000ms:
- Child says something sad --> relevance: HIGH, implications: EMPATHY NEEDED, coping: VALIDATE --> empathetic response (moderate negative valence, low arousal)
- Child asks a difficult question --> relevance: HIGH, implications: UNCERTAINTY, coping: MODERATE --> THINKING (slight negative valence, moderate arousal)
- Child shares excitement about a topic --> relevance: HIGH, implications: POSITIVE SHARING, coping: MATCH --> positive valence boost, moderate arousal

These require language comprehension and contextual reasoning -- they are the domain of the LLM (Layer 1). [Theory]

### 5.3 Mapping to Our Layer 0/Layer 1 Architecture

The appraisal theory distinction between fast and slow appraisals maps directly onto our two-layer architecture:

| Appraisal Type | Processing Time | Our Layer | Implementation |
|---------------|----------------|-----------|---------------|
| **Fast-path reflex** | < 50 ms | Layer 0 (signal-only) | Rules in personality worker: stimulus category --> impulse vector |
| **Slow-path contextual** | 200-2000 ms | Layer 1 (language-enhanced) | LLM evaluates conversation content --> emotion suggestion --> impulse |

**Both produce impulses into the same decaying integrator.** Fast-path appraisals fire immediately and provide the robot's initial emotional reaction. Slow-path appraisals arrive later and refine or override the initial reaction. This produces a natural two-phase response: quick reflex followed by considered adjustment. [Inference]

**Example sequence**:
1. Child speaks (audio detected) --> **Layer 0 fast appraisal**: social stimulus present --> +0.1 arousal impulse (mild alerting, ~20ms)
2. Speech processing completes --> **Layer 1 slow appraisal**: child said something sad --> empathetic impulse (-0.3 valence, -0.1 arousal, ~800ms after speech onset)
3. The affect vector first lifts slightly (alerting) then shifts toward empathetic sadness as the LLM appraisal arrives

This temporal layering is more natural than waiting for the LLM response before showing any reaction. The robot appears to "listen and then understand," which matches human emotional processing. [Inference]

### 5.4 Appraisal Dimensions to VA Perturbations

Each appraisal dimension maps to VA perturbations. **Relevance** and **normative significance** checks can be implemented as fast rules (they don't need semantic understanding): relevant events increase arousal; irrelevant events decrease it; unexpected events spike arousal; routine events habituate. **Implication** and **coping** checks require Layer 1 (LLM): favorable outcomes increase valence; unfavorable outcomes decrease it; high coping potential calms arousal; low coping potential raises it. [Theory -- synthesized from Scherer (2001)]

**Design implication**: Layer 0 implements relevance and normative appraisals. Layer 1 adds implication and coping appraisals. This gives Layer 0 enough capability for meaningful reactions to system events while Layer 1 provides context-aware reasoning. [Inference]

---

## 6. Mapping Functions: Traits to Affect Vector Parameters

### 6.1 The Mapping Problem

Each personality axis position (a value between 0 and 1) must be converted to a concrete affect vector parameter (baseline position, impulse gain, decay rate, noise amplitude, cap value). The choice of mapping function determines how personality "feels" -- linear, sigmoid, and piecewise mappings each produce qualitatively different personality expressions.

### 6.2 Linear Mapping

`parameter = a + b * axis_position`. Simple, monotonic, debuggable. But produces caricature at extremes -- Energy 0.95 creates mania, Energy 0.05 creates comatose behavior. **Appropriate for**: baseline offsets where the parameter range is already constrained (e.g., valence shifts of +/- 0.15). [Theory/Inference]

### 6.3 Sigmoid Mapping

`parameter = L / (1 + exp(-k * (axis_position - x0)))`. Naturally saturates at extremes. The middle 60% of axis range (0.20-0.80) produces most parameter variation; outer 20% on each side produces diminishing returns. [Theory]

**WASABI validation**: Becker-Asano & Wachsmuth (2010) used sigmoid activation for emotion intensity and reported "more natural intensity curves than linear activation" -- emotions rose quickly from neutral but saturated at moderate intensity, matching human experience where the difference between "not happy" and "a little happy" is salient but "very happy" vs "extremely happy" is barely noticeable. [Empirical]

**Appropriate for**: Impulse gains and decay rates, where extreme values produce mood whiplash or emotional deadness. [Inference]

**Citation**: Becker-Asano, C., & Wachsmuth, I. (2010). Affective computing with primary and secondary emotions in a virtual human. *Autonomous Agents and Multi-Agent Systems*, 20(1), 32-49.

### 6.4 Piecewise Mapping

Different slopes for different axis ranges. Full control per range but risks discontinuities at segment boundaries. **Appropriate for**: threshold parameters where behavior should change qualitatively at specific positions (e.g., Social Initiative below 0.20 disables proactive behavior entirely). [Theory/Inference]

### 6.5 WASABI Architecture: Additional Findings

Beyond sigmoid activation, WASABI (Becker-Asano & Wachsmuth, 2010) contributes several relevant design patterns:

- **Mood as slow-moving background**: Explicit separation of emotion (fast, stimulus-driven) from mood (slow, accumulated). Mood decays toward a personality-defined baseline -- architecturally equivalent to our two-layer integrator. [Theory]
- **Asymmetric emotion-to-mood coupling**: Negative events have stronger mood impact than positive events (psychological negativity bias). Applies to impulse magnitude but NOT to decay rate in our system. [Theory]
- **Concentration parameter**: Modulates emotional responsiveness during focused tasks. Maps to our context gate -- idle impulses suppressed during conversation. [Theory]

**Citation**: Becker-Asano, C., & Wachsmuth, I. (2010). WASABI: Affect simulation for agents with believable interactivity. *IEEE Transactions on Affective Computing*, 1(1), 10-24.

### 6.6 Preventing Caricature at Extremes

Linear mapping at axis extremes produces caricature: Energy 1.0 creates mania, Reactivity 1.0 creates mood whiplash, Vulnerability 1.0 removes all negative affect guardrails, Predictability 0.0 produces seizure-like jitter. Sigmoid naturally saturates at extremes, preventing these pathologies.

**Recommendation**: Use sigmoid for gains and rates (Energy, Reactivity), linear for small-range offsets (baseline valence/arousal shifts), and piecewise for threshold parameters (Initiative triggers, Vulnerability caps). This combination prevents caricature at extremes while maintaining intuitive behavior in the normal operating range (0.2-0.8). [Inference]

### 6.7 Asymmetric Decay: Negative Faster Than Positive

For a child-facing robot, emotional decay should be asymmetric: **negative emotions should decay faster than positive emotions.**

Rationale:
- Children ages 4-6 attribute genuine emotional states to robots (Kahn et al., 2012). A robot that lingers in sadness, anger, or fear is distressing to children who believe the robot is actually experiencing those states. [Empirical]
- Emotional resilience is a positive model for children. A robot that recovers quickly from negative states demonstrates healthy emotional regulation. [Inference]
- Our HC-10 constraint (no sustained negative affect outside active conversation) mandates faster negative decay by design. [Inference -- constrained by Bucket 0]
- WASABI's negativity bias (negative events have stronger mood impact) should apply to impulse magnitude but NOT to decay rate. Negative events can hit hard but should fade fast. [Inference]

**Recommended asymmetric decay multipliers**:
```
lambda_positive = lambda_base * 0.85    (positive emotions decay 15% slower)
lambda_negative = lambda_base * 1.30    (negative emotions decay 30% faster)
```

At our baseline configuration:
- If lambda_base = 0.05 /s (half-life ~14s), then:
  - Positive emotion half-life: ~16.3s (lingers slightly)
  - Negative emotion half-life: ~10.7s (fades faster)

This asymmetry means a HAPPY impulse of the same magnitude as a SAD impulse will be visible for about 50% longer -- the robot naturally "dwells in joy, bounces back from sadness." [Inference]

---

## 7. Tapus & Mataric: Adaptive Personality Matching

### 7.1 Study Overview

Tapus & Mataric (2008) studied how matching a robot's personality to a user's personality affects interaction quality and task performance in a rehabilitation therapy context. The robot adjusted its behavioral parameters (speech, gestures, encouragement style) to either match or oppose the user's personality profile. [Empirical]

### 7.2 Key Findings

**Personality matching improves outcomes**: Matched personality (extraverted robot for extraverted user) produced greater task engagement, more positive affect, higher compliance, and stronger preference. This supports the "similarity-attraction" hypothesis. [Empirical]

**Behavioral parameters that conveyed personality**: Speech rate/volume, gesture frequency/amplitude, encouragement style (enthusiastic vs. quiet), proximity, and interaction pacing. **Adaptation was primarily along the Extraversion dimension** -- other Big Five dimensions were less reliably conveyed, consistent with Robert (2018). [Empirical]

**Citation**: Tapus, A., & Mataric, M. J. (2008). Socially assistive robots: The link between personality, empathy, physiological signals, and task performance. In *Proceedings of the AAAI Spring Symposium on Emotion, Personality, and Social Behavior*.

### 7.3 Implications for Our Design

**We choose NOT to do per-child personality matching** (PE-4 Option A: fixed personality). Reasons:
1. **Identification problem**: We cannot assess a 4-year-old's Big Five traits -- personality is not reliably stable at this age. [Inference]
2. **Safety concern**: Matching an anxious child with a high-Neuroticism robot mirrors anxiety rather than regulating it. The caretaker role requires stable emotional anchoring. [Inference]
3. **Consistency is valued at this age**: Children ages 4-6 benefit more from personality consistency (ritual formation, predictability) than from adaptation (Bucket 3 findings). [Inference]
4. **Adult-only validation**: Tapus & Mataric's participants had stable personality profiles; generalizing to 4-year-olds is not warranted. [Inference]

**What we DO take**: The behavioral parameters that convey personality (speech rate, gesture frequency, interaction pacing) must be consistent across interactions -- Energy 0.40 should always produce calm pacing. [Inference]

---

## 8. VA Space Mood Anchor Table

### 8.1 Methodology

The following VA coordinates for our 12 moods are synthesized from multiple sources:
- Russell (1980) -- prototypical positions of emotion labels in the circumplex
- Posner, Russell, & Peterson (2005) -- refined positions with neurobiological grounding
- Breazeal (2003) -- positions used in Kismet's emotion space
- WASABI (Becker-Asano & Wachsmuth, 2010) -- positions in the PAD model (P and A dimensions extracted)

Coordinates are adjusted for our specific context: child-facing robot where SURPRISED is biased positive (children experience surprise as positive in safe contexts) and negative emotions are positioned conservatively (further from extremes to facilitate faster decay recovery). [Inference]

### 8.2 Mood Anchor Positions

| Mood | Valence | Arousal | Quadrant | Notes |
|------|---------|---------|----------|-------|
| **NEUTRAL** | 0.00 | 0.00 | Center | Origin point. Low-intensity baseline. Decay target for personality baseline near (0.00, 0.00). |
| **HAPPY** | +0.70 | +0.35 | Q1 (pos/pos) | Moderate arousal distinguishes from EXCITED. Primary positive emotion for social interaction. |
| **SAD** | -0.60 | -0.40 | Q3 (neg/neg) | Low arousal, negative valence. Duration-limited by guardrails. Capped intensity for children. |
| **ANGRY** | -0.60 | +0.70 | Q2 (neg/pos) | High arousal, negative valence. Intensity hard-capped at 0.5 for children. Used only for mild frustration in practice. |
| **SCARED** | -0.70 | +0.65 | Q2 (neg/pos) | High arousal, strong negative. Intensity hard-capped at 0.6 for children. Brief duration only. |
| **SURPRISED** | +0.15 | +0.80 | Q1 (pos/pos) | Very high arousal, slightly positive. Biased positive for child context (surprise = exciting, not threatening). |
| **CURIOUS** | +0.40 | +0.45 | Q1 (pos/pos) | Positive, moderate-high arousal. Represents active interest and engagement. Core exploration state. |
| **SLEEPY** | +0.05 | -0.80 | Q4 (pos/neg) | Very low arousal, near-neutral valence. Primary idle/rest state. Slightly positive to avoid "sad-sleepy" read. |
| **CONFUSED** | -0.20 | +0.30 | Q2 (neg/pos) | Mild negative, mild arousal. Represents uncertainty. Close to THINKING but with slight discomfort. |
| **EXCITED** | +0.65 | +0.80 | Q1 (pos/pos) | High arousal, high positive. Distinguished from HAPPY by arousal level. Peak positive engagement state. |
| **LOVE** | +0.80 | +0.15 | Q1 (pos/pos) | Highest positive valence, low arousal. Warm, calm affection. Distinguished from HAPPY by lower arousal and higher valence. |
| **THINKING** | +0.10 | +0.20 | Q1 (pos/pos) | Near-neutral, slight positive. Represents deliberation and processing. Calm concentration. |

### 8.3 Spatial Relationships

**Close pairs requiring hysteresis**:
- HAPPY (+0.70, +0.35) and LOVE (+0.80, +0.15): distance = 0.22 -- need hysteresis to prevent flickering between warm-active and warm-calm
- CURIOUS (+0.40, +0.45) and THINKING (+0.10, +0.20): distance = 0.39 -- adequate separation
- ANGRY (-0.60, +0.70) and SCARED (-0.70, +0.65): distance = 0.11 -- very close, need strong hysteresis or contextual disambiguation
- CONFUSED (-0.20, +0.30) and THINKING (+0.10, +0.20): distance = 0.32 -- adequate separation
- SURPRISED (+0.15, +0.80) and EXCITED (+0.65, +0.80): distance = 0.50 -- adequate separation

**Isolated moods (far from all others)**:
- SLEEPY (+0.05, -0.80): most isolated mood. Nearest neighbor is NEUTRAL at distance 0.80. Strong attractor basin -- once the affect vector drifts this low in arousal, it locks into SLEEPY.
- SAD (-0.60, -0.40): nearest neighbor is NEUTRAL at distance 0.72. Adequately separated.

**Design note**: The ANGRY/SCARED proximity (distance 0.11) means the affect vector can easily oscillate between these two moods. Since both are hard-capped for intensity in children, this flickering -- while technically possible -- would occur at low intensity where the visual difference is minimal. Nevertheless, a hysteresis threshold of at least 0.15 is recommended for transitions between these two moods specifically. [Inference]

---

## 9. Parameter Mapping Recommendations

### 9.1 Consolidated Axis-to-Parameter Table

All mapping functions use `sigmoid(x, k, x0) = 1 / (1 + exp(-k * (x - x0)))` with k (steepness) and x0 (midpoint) as noted. [Inference]

| Axis | Parameter | Mapping | Formula | Value | Behavioral Effect |
|------|-----------|---------|---------|-------|-------------------|
| **Energy (0.40)** | Baseline arousal | Linear | `b_a = -0.20 + 0.40 * E` | -0.04 | Very slightly calm resting state |
| | Gesture frequency mult. | Sigmoid (k=6, x0=0.5) | `0.5 + 1.0 * sig(E)` | 0.73 | Slightly below average gesture rate |
| | Transition speed mult. | Linear | `0.7 + 0.6 * E` | 0.94 | Near-normal transition speed |
| | Positive impulse arousal scaling | Sigmoid (k=5, x0=0.5) | `0.6 + 0.8 * sig(E)` | 0.83 | Slightly attenuated arousal response |
| **Reactivity (0.50)** | Impulse magnitude scaling | Sigmoid (k=5, x0=0.5) | `0.4 + 1.2 * sig(R)` | 1.00 | Exactly baseline -- no amplification |
| | Decay rate (lambda_base) | Inv. sigmoid (k=5, x0=0.5) | `0.08 - 0.05 * sig(R)` | 0.055 /s | Half-life ~12.6s |
| | Emotional range (max displacement) | Sigmoid (k=4, x0=0.5) | `0.4 + 0.6 * sig(R)` | 0.70 | Moderate excursions from baseline |
| | Mood susceptibility | Linear | `0.1 + 0.4 * R` | 0.30 | Needs several consistent emotions to shift mood |
| **Initiative (0.30)** | Initiative base probability | Piecewise | `SI^1.5` | 0.164 | ~16% trigger probability |
| | Idle impulse magnitude | Linear | `0.1 + 0.3 * SI` | 0.19 | Weak idle impulses |
| | Initiative cooldown min | Inv. linear | `30 / (0.1 + SI) min` | 75 min | Very infrequent proactive behavior |
| | Autonomous impulse freq. | Linear | `SI * 4 /hr` | 1.2 /hr | ~1 visible mood shift per hour idle |
| **Vulnerability (0.35)** | Neg. valence display cap | Piecewise | `-0.3 - 0.5 * V` | -0.475 | Can show mild negative, not strong |
| | Neg. impulse attenuation | Sigmoid (k=5, x0=0.5) | `0.3 + 0.7 * sig(V)` | 0.53 | Negative impulses at ~53% -- lightly guarded |
| | Empathy mirroring gain | Linear | `0.2 + 0.6 * V` | 0.41 | Moderate empathy display |
| | Context gate strictness | Inv. linear | `1.0 - 0.5 * V` | 0.825 | Suppresses most neg. affect outside conversation |
| **Predictability (0.75)** | Noise amplitude (per-tick) | Inv. linear | `0.10 * (1 - P)` | 0.025 | Very small jitter |
| | Mood variant randomness | Inv. linear | `1.0 - P` | 0.25 | 25% variant selection chance |
| | Timing jitter (sigma) | Inv. linear | `60 * (1 - P) s` | 15s | Events fire within +/- 15s of deterministic timing |
| | Response diversity | Inv. linear | `1.0 - P` | 0.25 | 25% of the time, non-default expression variant |

### 9.2 Behavioral Summary per Axis

- **Energy 0.40**: "Calm but present" -- near-neutral arousal, almost normal speed, slightly attenuated arousal response. Not sluggish, not energetic. [Inference]
- **Reactivity 0.50**: "Responsive but stable" -- baseline impulse gain, ~12.6s half-life (emotions visible ~25s before fading), moderate excursions. [Inference]
- **Initiative 0.30**: "Quietly alive" -- almost never initiates (16% probability, 75-min cooldown), weak idle impulses, ~1 mood shift/hr. See Bucket 4 Section 5. [Inference]
- **Vulnerability 0.35**: "Lightly guarded caretaker" -- negative emotions attenuated, moderate empathy, negative affect mostly suppressed outside conversation. [Inference]
- **Predictability 0.75**: "Consistent with cosmetic freshness" -- same response 75% of the time, 25% budget for timing/gesture/intensity variation. [Inference]

### 9.3 Combined Baseline Position

With all axes at their defined positions:

```
baseline_valence = 0.00 + 0.15 * energy(0.40) = +0.06
baseline_arousal = -0.20 + 0.40 * energy(0.40) = -0.04
```

**Baseline position: (+0.06, -0.04)** -- very slightly positive valence, very slightly below neutral arousal. Nearest mood anchor is NEUTRAL (0.00, 0.00) at distance 0.07. At rest, the robot projects NEUTRAL at very low intensity -- the intended "calm contentment" idle state. [Inference]

---

## 10. Design Recommendations

### 10.1 Use the TAME Multilayer Architecture

The TAME architecture's separation of Traits --> Moods --> Emotions is validated by participant studies and maps directly onto our decaying integrator model. **Traits set the integrator parameters. Moods are the slow-moving tonic state. Emotions are fast-moving phasic impulses.** Both moods and emotions are positions in the VA space; they differ only in temporal dynamics and update sources.

The decaying integrator naturally implements this layering: emotions (impulses) perturb the affect vector; the vector decays toward a mood-biased baseline; the mood itself slowly drifts based on accumulated emotional residue, decaying toward the trait-defined personality baseline. No explicit "mood computation module" is needed -- the two-rate integrator IS the mood/emotion separation. [Inference]

### 10.2 Compute in Dimensional Space, Display in Categorical Space

The affect vector operates in continuous VA space. Mood anchors (Section 8) define 12 categorical output positions. The projection function maps continuous to discrete at render time. This hybrid gives us the dynamic benefits of dimensional computation (smooth transitions, impulse stacking, decay, noise) with the perceptual benefits of categorical display (children recognize named emotions). [Inference]

### 10.3 Use Sigmoid Mapping for Gains and Rates

Sigmoid mapping prevents caricature at axis extremes and was validated by WASABI for emotion intensity curves. Apply sigmoid to:
- Impulse magnitude scaling (Reactivity axis)
- Positive impulse arousal scaling (Energy axis)
- Negative impulse attenuation (Vulnerability axis)
- Decay rate (Reactivity axis, inverse sigmoid)

Apply linear mapping to:
- Baseline position offsets (small range, no extremes risk)
- Noise amplitude (Predictability axis)
- Initiative frequency (Social Initiative axis)

Apply piecewise mapping to:
- Initiative trigger thresholds (Social Initiative axis -- qualitative change below 0.20)
- Negative valence display caps (Vulnerability axis -- hard floor)

[Inference]

### 10.4 Implement Asymmetric Decay

Negative emotions should decay faster than positive emotions:
```
lambda_positive = lambda_base * 0.85    (positive lingers 15% longer)
lambda_negative = lambda_base * 1.30    (negative fades 30% faster)
```

This serves three purposes:
1. **Child safety**: minimizes time in negative emotional states that may distress children who attribute genuine feelings to the robot [Inference -- constrained by Bucket 0]
2. **Emotional resilience modeling**: demonstrates healthy emotional regulation -- recovering from setbacks quickly while savoring positive experiences [Inference]
3. **HC-10 compliance**: sustained negative affect outside active conversation is prohibited; faster decay is the primary enforcement mechanism [Inference -- constrained by Bucket 0 HC-10]

### 10.5 Use Appraisal Theory for Layer 0 Fast-Path Impulses

Layer 0 should implement fast-path appraisal rules as the primary impulse generator when no LLM is available:

| Stimulus | Appraisal | Impulse (dV, dA) | Magnitude | Latency |
|----------|-----------|-------------------|-----------|---------|
| System boot | Novel, relevant | CURIOUS (+0.40, +0.45) | 0.4 | < 50 ms |
| Button press | Social, relevant | Positive alert (+0.20, +0.30) | 0.3 | < 20 ms |
| Low battery | Relevant, unfavorable, high coping | Mild concern (-0.15, +0.10) | 0.2 | < 50 ms |
| Error/fault | Relevant, uncertain, moderate coping | THINKING (+0.10, +0.20) | 0.3 | < 50 ms |
| Idle timeout (5+ min) | Low relevance | Arousal decay (0, -0.15) | 0.2 | On timer |
| Child approach (proximity) | Social, relevant | Alert/warm (+0.10, +0.15) | 0.2 | < 100 ms |
| Loud sound | Novel, uncertain | Startle (0, +0.40) | 0.3 | < 30 ms |
| Conversation end (normal) | Relevant, positive | Warm residual (+0.15, -0.10) | 0.2 | < 100 ms |

These fast-path impulses give the robot immediate emotional reactions to system events without waiting for LLM processing. When Layer 1 is available, it provides contextually richer impulses that may override or supplement the fast-path response. [Inference]

### 10.6 Hysteresis Thresholds for Mood Projection

To prevent mood flickering at anchor boundaries:

| Transition Type | Recommended Hysteresis | Rationale |
|----------------|----------------------|-----------|
| Any positive --> negative mood | 0.15 | Higher threshold -- harder to enter negative states |
| Any negative --> positive mood | 0.08 | Lower threshold -- easier to escape negative states |
| Within positive moods (e.g., HAPPY --> CURIOUS) | 0.10 | Standard threshold |
| Within negative moods (e.g., ANGRY --> SCARED) | 0.15 | Higher threshold -- prevent flickering between close negative anchors |
| Any mood --> NEUTRAL | 0.12 | Standard -- should be natural to return to neutral |
| NEUTRAL --> any mood | 0.08 | Lower threshold -- easy to leave neutral (robot appears responsive) |

The asymmetric hysteresis (easier to escape negative, harder to enter negative) reinforces the asymmetric decay design and further reduces time in negative states. [Inference]

### 10.7 TAME/Kismet Limitation Mitigations

1. **Sensitivity analysis**: Sweep each mapping constant before finalizing; verify no attractor basin trapping (especially negative moods). Document stable operating ranges.
2. **Anti-trapping mechanism**: If affect vector is in a negative mood region longer than the guardrail duration limit, inject recovery impulse toward baseline regardless of ongoing stimuli.
3. **Bounded noise**: Gaussian noise from Predictability axis must be hard-clipped at 2 sigma to prevent random perturbations into unexpected mood regions.
4. **Empirical validation with children**: TAME was validated with adults only. Test with parents and children ages 4-6 before deployment per the evaluation framework (personality engine spec Section C.6).

[Inference -- mitigation strategies derived from documented TAME/Kismet failure modes]

---

## Sources

- [Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6), 1161-1178.](https://doi.org/10.1037/h0077714)
- [Posner, J., Russell, J. A., & Peterson, B. S. (2005). The circumplex model of affect: An integrative approach. *Development and Psychopathology*, 17(3), 715-734.](https://doi.org/10.1017/S0954579405050340)
- [McCrae, R. R., & Costa, P. T. (1997). Personality trait structure as a human universal. *American Psychologist*, 52(5), 509-516.](https://doi.org/10.1037/0003-066X.52.5.509)
- [Moshkina, L., & Arkin, R. C. (2005). Human perspective on affective robotic behavior: A longitudinal study. *IROS 2005*.](https://doi.org/10.1109/IROS.2005.1545395)
- [Moshkina, L., & Arkin, R. C. (2011). TAME: Time-varying affective response for humanoid robots. *International Journal of Social Robotics*, 3(3), 207-221.](https://link.springer.com/article/10.1007/s12369-011-0090-2)
- [Breazeal, C. (2003). Emotion and sociable humanoid robots. *International Journal of Human-Computer Studies*, 59(1-2), 119-155.](https://doi.org/10.1016/S1071-5819(03)00018-1)
- [Scherer, K. R. (2001). Appraisal considered as a process of multilevel sequential checking. In *Appraisal processes in emotion* (pp. 92-120). Oxford University Press.](https://doi.org/10.1093/oso/9780195130072.003.0005)
- [Becker-Asano, C., & Wachsmuth, I. (2010). Affective computing with primary and secondary emotions in a virtual human. *Autonomous Agents and Multi-Agent Systems*, 20(1), 32-49.](https://doi.org/10.1007/s10458-009-9094-9)
- [Becker-Asano, C., & Wachsmuth, I. (2010). WASABI: Affect simulation for agents with believable interactivity. *IEEE Transactions on Affective Computing*, 1(1), 10-24.](https://doi.org/10.1109/T-AFFC.2010.2)
- [Robert, L. P. (2018). Personality in the human robot interaction literature: A review and brief critique. *AMCIS 2018*.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3308191)
- [Tapus, A., & Mataric, M. J. (2008). Socially assistive robots: The link between personality, empathy, physiological signals, and task performance. *AAAI Spring Symposium*.](https://www.aaai.org/Papers/Symposia/Spring/2008/SS-08-04/SS08-04-019.pdf)
- [Widen, S. C., & Russell, J. A. (2003). A closer look at preschoolers' freely produced labels for facial expressions. *Developmental Psychology*, 39(1), 114-128.](https://doi.org/10.1037/0012-1649.39.1.114)
- [Kahn, P. H., et al. (2012). Robovie, you'll have to go into the closet now. *Developmental Psychology*, 48(2), 303-314.](https://doi.org/10.1037/a0027033)
- [Mehrabian, A., & Russell, J. A. (1974). *An approach to environmental psychology*. MIT Press.](https://mitpress.mit.edu/9780262130905/)
- [McCrae, R. R., & Costa, P. T. (2008). The Five-Factor Theory of personality. In *Handbook of personality* (3rd ed.). Guilford Press.](https://www.guilford.com/books/Handbook-of-Personality/John-Robins-Pervin/9781462544950)
