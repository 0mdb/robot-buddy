# Bucket 7: The Device/Server Split

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-9 (Device/Server Boundary) and worker architecture design

---

## Table of Contents

1. [Rule-Based Emotion Engines in Social Robotics](#1-rule-based-emotion-engines-in-social-robotics)
2. [Finite State Machines vs Continuous Models for Personality](#2-finite-state-machines-vs-continuous-models-for-personality)
3. [Hybrid Deterministic+LLM Architectures](#3-hybrid-deterministicllm-architectures)
4. [Graceful Degradation Patterns](#4-graceful-degradation-patterns)
5. [State Synchronization Between Device and Server](#5-state-synchronization-between-device-and-server)
6. [The Exact Boundary: Responsibility Matrix](#6-the-exact-boundary-responsibility-matrix)
7. [Worker Architecture: PersonalityWorker Design](#7-worker-architecture-personalityworker-design)
8. [Latency Budget Analysis](#8-latency-budget-analysis)
9. [Design Recommendations](#9-design-recommendations)

---

## 1. Rule-Based Emotion Engines in Social Robotics

### 1.1 TAME: Traits, Attitudes, Moods, and Emotions (Moshkina & Arkin, 2005/2011)

TAME is the most directly relevant precedent for a pure rule-based personality engine. The architecture separates personality into four hierarchical layers -- traits (constant, operator-defined), attitudes (learned evaluations toward objects/events), moods (diffuse background states), and emotions (short-term stimulus responses) -- each operating on a different timescale with purely deterministic rules mapping between them. [Empirical]

Key design principles from TAME that apply directly to our system:

- **Big Five trait parameterization**: Each of the five personality dimensions (mapped to our Energy, Reactivity, Initiative, Vulnerability, Predictability axes) modulates the gain, threshold, and decay rate of emotional responses. Moshkina & Arkin validated that participants could reliably distinguish between high and low Extraversion configurations without any ML -- purely from rule-parameterized behavior differences. [Empirical]

- **Mood as weighted accumulator**: Mood in TAME is computed as a weighted sum of recent emotion activations, decaying exponentially toward a personality-determined baseline. This is architecturally identical to our decaying integrator model with the temperament baseline as the attractor. [Theory]

- **No language understanding required**: TAME processes perceptual stimuli categories (e.g., "obstacle detected," "social stimulus present," "task failure") and maps them to appraisal values through lookup tables. The entire system runs as a finite set of stimulus-response rules with parameterized gains. No NLP, no LLM, no semantic understanding. [Empirical]

- **Strengths validated**: Deterministic, reproducible, fast (< 1 ms per evaluation cycle), debuggable (every personality decision traceable to a specific rule + parameter value). Participants perceived the robot as having a distinct "character" based solely on rule-parameterized behavior. [Empirical]

- **Weaknesses observed**: Cannot reason about conversational content. Cannot distinguish "the child said something sad" from "the child said something exciting" without a separate language understanding module. Personality is recognizable at the trait level but flat at the contextual level -- the robot reacts the same way to all stimuli within a category regardless of semantic nuance. [Inference]

**Citation**: Moshkina, L., & Arkin, R. C. (2011). TAME: Time-varying affective response for humanoid robots. *International Journal of Social Robotics*, 3(3), 207-221.

### 1.2 Kismet: Homeostatic Drives (Breazeal, 2003)

Kismet's emotion system is organized around three homeostatic drives (social stimulation, fatigue, play) that produce continuous emotional cycling without any language or learning component. The drives drift from equilibrium over time and the robot generates behavior to restore balance. [Empirical]

Relevant findings for our architecture:

- **Emotion emerges from drive dynamics, not classification**: Kismet does not receive an emotion label and display it. Instead, internal drives produce points in a valence-arousal-stance space, and the emotion display is a projection from that space. This is exactly our affect vector approach -- emotion is computed, not assigned. [Theory]

- **Smooth transitions in VA space look natural**: Breazeal specifically noted that smooth interpolation between emotional states in the continuous VA space looked more natural than discrete switching between categorical emotions. The continuous integrator model preserves this property. [Empirical]

- **Homeostatic cycling provides idle "aliveness"**: Even without any social interaction, Kismet's drives produce visible emotional cycling (alert --> bored --> sleepy --> alert). This prevents the "dead idle" failure mode. Our idle behavior catalog (Bucket 4) serves the same function through deterministic rules rather than homeostatic drives, but the principle is identical. [Theory]

- **Attractor basins were hand-tuned and brittle**: Small parameter changes in Kismet's drive system caused unnatural oscillation or emotional "sticking." This is a known risk of coupled dynamical systems and argues for our simpler approach (decaying integrator with impulses rather than coupled homeostatic drives). [Empirical]

**Citation**: Breazeal, C. (2003). Emotion and sociable humanoid robots. *International Journal of Human-Computer Studies*, 59(1-2), 119-155.

### 1.3 WASABI: Mass-Spring-Damper Mood Model (Becker-Asano & Wachsmuth, 2010)

WASABI (Wasabi Affect Simulation for Agents with Believable Interactivity) models the relationship between emotion and mood as a mass-spring-damper system in valence-arousal space. Emotions are impulse forces applied to a "mood mass" that oscillates and decays toward a personality-determined equilibrium. [Empirical]

Key design insights:

- **Second-order dynamics produce natural overshoot**: Unlike a first-order exponential decay (our current integrator), the mass-spring-damper system allows mood to temporarily overshoot its target and oscillate before settling. This produces behaviors like "recovery bounce" (the lift of relief after a negative emotion passes) without explicit rules. [Theory]

- **Mood inertia is physically intuitive**: Heavy mass = high emotional inertia (stoic personality). Light mass = responsive to every impulse (reactive personality). Damping coefficient = how quickly emotions settle. Spring constant = how strongly personality pulls mood back to baseline. These map cleanly to our personality axes: Reactivity -> mass/damping, Energy -> baseline position, Predictability -> spring constant. [Theory]

- **Sigmoid activation for emotion intensity**: WASABI uses a sigmoid function to map the continuous VA position to emotion intensity, producing more natural intensity curves than linear mapping. Emotions feel "reluctant to start" (low signal stays low) and "eager to saturate" (high signal quickly reaches full expression). This prevents the uncanny valley of perfectly linear emotional intensity. [Theory]

- **Decay-to-neutral limitation**: WASABI's default behavior when no events occur is monotonic decay toward neutral. This is the "dead idle" failure mode we explicitly avoid. WASABI by itself does not solve idle aliveness -- it needs impulse sources. [Empirical]

**Implication for our system**: Our first-order decaying integrator is simpler than WASABI's mass-spring-damper but loses the overshoot/oscillation behavior. If emotional transitions feel too "flat" in testing, upgrading to second-order dynamics is a well-understood change with minimal architectural impact. Stage 2 should spec the integrator as a pluggable module. [Inference]

**Citation**: Becker-Asano, C., & Wachsmuth, I. (2010). WASABI: Affect simulation for agents with believable interactivity. *IEEE Transactions on Affective Computing*, 1(1), 10-24.

### 1.4 What Personality Quality Is Achievable With Rules Alone?

Synthesizing across TAME, Kismet, and WASABI, the following personality capabilities are fully achievable with deterministic rules and no ML:

| Capability | Achievable (Rules Only)? | Quality Level | Evidence |
|-----------|-------------------------|---------------|----------|
| Recognizable temperament (calm vs energetic) | Yes | High | TAME participants distinguished traits [Empirical] |
| Idle emotional behavior (aliveness) | Yes | Medium-high | Kismet drive cycling, our idle catalog [Empirical] |
| Emotional inertia (no mood whiplash) | Yes | High | Decaying integrator is mathematical [Theory] |
| Event-driven emotion (boot, battery, error) | Yes | High | Simple stimulus-response rules [Theory] |
| Guardrail enforcement | Yes | High | Hard constraints on affect vector [Theory] |
| Contextual emotion during conversation | No | N/A | Requires semantic understanding [Inference] |
| Personality-consistent response text | No | N/A | Requires language generation [Theory] |
| Empathic mirroring of child's mood | Partial | Low | Can mirror valence signal, not content [Inference] |
| Conversational emotional arc | No | N/A | Requires multi-turn context understanding [Inference] |
| Memory-informed personalization | Partial | Low | Can retrieve stored tags, cannot reason about them [Inference] |

**Bottom line**: Rules alone produce a robot that has a recognizable temperament, maintains emotional inertia, shows signs of life during idle, and responds appropriately to system events. It cannot understand what the child is saying, produce contextually appropriate emotional responses to conversation, or maintain a coherent emotional arc across a multi-turn dialogue. This is precisely our Layer 0 capability set. [Inference]

---

## 2. Finite State Machines vs Continuous Models for Personality

### 2.1 FSM-Based Emotion Models

Finite state machines are the most common implementation pattern for emotion in games and animation. Each emotional state is a node; transitions are triggered by events with optional guard conditions. The model is simple, predictable, and visually debuggable (the state graph can be drawn). [Theory]

Common patterns:

- **Flat FSM**: States are peer-level (HAPPY, SAD, NEUTRAL, EXCITED). Transitions fire on events. Used in simple NPC emotion in games. Problem: exponential transition explosion (N states require up to N^2 transitions). [Theory]

- **Hierarchical FSM (HFSM)**: States grouped into families (POSITIVE/NEGATIVE/NEUTRAL superstates). Transitions between families are coarse; within-family transitions are fine-grained. Reduces transition count but adds complexity. [Theory]

- **Behavior Trees**: An alternative to FSMs popular in game AI. Nodes are conditions or actions; the tree is evaluated top-to-bottom. Emotion is a subtree that modulates behavior selection. More composable than FSMs but harder to reason about global state. [Theory]

### 2.2 FSM Limitations for Our Use Case

For our personality engine, a pure FSM has several critical limitations:

1. **No intensity**: FSMs are binary -- you are in a state or not. Emotional intensity requires either (a) multiple states per emotion (HAPPY_LOW, HAPPY_MED, HAPPY_HIGH -- tripling state count) or (b) a continuous variable alongside the FSM (which is a hybrid model, not a pure FSM). [Theory]

2. **No smooth transitions**: FSM transitions are instantaneous. The affect vector must traverse continuous VA space to produce natural-looking face transitions. An FSM can trigger a transition, but the actual interpolation still requires a continuous model. [Theory]

3. **No stacking**: In an FSM, receiving a second HAPPY event while already in HAPPY does nothing (or restarts the state). In a continuous model, the second impulse pushes the affect vector further into positive valence, producing a natural intensification. [Theory]

4. **Transition explosion**: With 12 moods and multiple trigger types (system events, conversation events, idle timers, memory), the transition matrix becomes unwieldy. Our idle behavior catalog alone defines 11 trigger-mood pairs (Bucket 4 Section 3.3). Adding conversation-driven emotions, guardrail-triggered overrides, and initiative behaviors would require hundreds of transitions. [Inference]

### 2.3 What Our Decaying Integrator Gains Over a Pure FSM

The continuous affect vector with decaying integrator is strictly more expressive than any FSM representation of the same personality:

| Property | FSM | Decaying Integrator | Advantage |
|----------|-----|-------------------|-----------|
| Emotional intensity | Discrete (requires state multiplication) | Continuous (magnitude of affect vector) | Natural intensity variation |
| Transition smoothness | Instantaneous | Exponential decay in VA space | Natural-looking face transitions |
| Impulse stacking | None (repeat events ignored) | Additive (multiple impulses compound) | Realistic emotional buildup |
| Temporal dynamics | Timer-based state transitions | Continuous decay toward baseline | Time-rate invariant; mathematically principled |
| Personality parameterization | Different transition tables per personality | Different baseline/decay/scaling per personality | Continuous personality variation (not just presets) |
| Debuggability | High (draw the state graph) | Medium (log affect vector trajectory) | FSM wins, but trajectory logging is tractable |
| Hysteresis | Requires explicit self-transitions | Natural (affect must cross threshold past new mood before switching) | Integrator provides hysteresis "for free" |

**The integrator IS more expressive than a pure FSM, but we also use rules.** The hybrid approach (PE-1 Option C) means we get the integrator's continuous dynamics for smooth baseline behavior plus discrete rules for event-triggered behavior that the integrator cannot express (e.g., "on boot, inject CURIOUS impulse"). This is not an FSM driving the integrator -- it is the integrator as the primary model with rules providing impulse sources. [Inference]

### 2.4 Behavior Trees as an Alternative

Behavior trees offer a middle ground between FSMs and continuous models. Some social robotics projects (particularly ROS-based systems) use behavior trees to organize personality-related decision-making. The tree structure naturally handles priority (higher nodes evaluated first) and fallback (if one behavior fails, try the next). [Theory]

For our system, behavior trees would be applicable to the rule layer (deciding which impulse to inject based on current context) but not to the integrator layer (which is pure math). We could implement the rule triggers as a behavior tree rather than a flat if/else chain. However, our rule set is small enough (approximately 20-30 rules covering idle, events, guardrails, and initiative) that a behavior tree adds architectural overhead without proportional benefit. A priority-ordered rule table achieves the same result with less abstraction. [Inference]

---

## 3. Hybrid Deterministic+LLM Architectures

### 3.1 The Emerging Pattern: Fast Rules + Slow Intelligence

As LLMs have become capable enough for emotional reasoning (2024-2025), a clear architectural pattern has emerged in social robotics and virtual companion systems: a fast, deterministic rule layer handles immediate responses while a slower LLM layer provides contextual intelligence. This is not yet widely published in academic literature -- most published hybrid architectures predate modern LLMs -- but the pattern is converging across multiple independent projects. [Inference]

The key insight driving this pattern: **LLM latency (200-2000 ms) is incompatible with real-time emotional display, but LLM reasoning is essential for contextually appropriate emotion.** The solution is temporal separation: rules react immediately, LLM catches up and refines. [Theory]

### 3.2 Precedent: Two-Process Emotion Models

The psychological literature provides a strong theoretical foundation for the fast/slow split. Dual-process theories of emotion (LeDoux, 1996; Scherer, 2001) distinguish between:

- **Fast appraisal** (subcortical, < 100 ms): Immediate, automatic evaluation of stimuli on basic dimensions -- is this good/bad? Is this threatening? This produces coarse emotional reactions without cognitive evaluation. Maps to our Layer 0 rules. [Theory]

- **Slow appraisal** (cortical, 200+ ms): Deliberate evaluation of context, meaning, social implications. Refines or overrides the fast response. Maps to our Layer 1 LLM processing. [Theory]

LeDoux (1996) specifically demonstrated that the brain's amygdala (fast path) produces emotional responses before the cortex (slow path) completes its analysis. The cortex then modulates the amygdala's output. This is directly analogous to: rules produce an immediate personality-consistent response; LLM refines it with contextual understanding. [Theory]

**Citation**: LeDoux, J. (1996). *The emotional brain: The mysterious underpinnings of emotional life*. Simon & Schuster.

### 3.3 Architectural Patterns for the Split

Based on available architectures and extrapolation from adjacent domains (smart speakers, virtual companions, game NPCs), three patterns exist for splitting personality between on-device rules and server LLM:

**Pattern A: LLM-Primary (Thin Client)**

The LLM owns all emotion decisions. The on-device layer is a simple passthrough that displays what the LLM says. When the server is down, the device has minimal or no personality.

```
On-Device: display(LLM_emotion) or display(NEUTRAL) if offline
Server: all emotion reasoning, personality, memory
```

Used by: Early smart speaker personality systems (Alexa, Google Assistant pre-2024), basic chatbot companions. [Inference]

**Strengths**: Simple device code. Single source of truth. Easy to update personality (server-side only).
**Weaknesses**: Complete personality loss on server failure. Latency-bound -- emotion display waits for LLM response. No idle personality. Our PE-9 Option B.

**Pattern B: Rules-Primary (Smart Client)**

On-device rules handle all personality decisions. The LLM provides text and optionally suggests emotions, but the device makes all final decisions. LLM suggestions are treated as hints, not commands.

```
On-Device: full personality engine (rules + integrator), final emotional authority
Server: text generation + emotion hint (suggestion only)
```

Used by: TAME-based systems, Kismet (no server at all), some consumer companion robots (EMO). [Inference]

**Strengths**: Full personality without server. Fast. Deterministic. Debuggable.
**Weaknesses**: Cannot understand conversation content. Emotion suggestions from LLM may be overridden even when correct. Our PE-9 Option A.

**Pattern C: Balanced Split (Our Design Direction)**

On-device rules own the affect vector, baseline, idle behavior, and guardrails. The LLM provides context-aware impulses that feed INTO the affect vector. The device applies personality modulation to LLM suggestions. Final emotion is always the integrator's output, not raw LLM output.

```
On-Device: affect vector, baseline, decay, idle rules, guardrails, modulation
Server: context-aware impulses (emotion suggestions), personality-aware text
Both: personality profile (synchronized)
```

This is the pattern implied by PE-1 (Hybrid), PE-8 (Both), and PE-9 (Balanced split). [Inference]

**Strengths**: Personality always present (Layer 0). Contextual intelligence when available (Layer 1). Single emotional authority (integrator on device). Graceful degradation built in.
**Weaknesses**: Requires state synchronization. Two systems must agree on personality. More complex than either A or B alone.

### 3.4 How the Split Handles Latency

The critical insight of Pattern C is temporal layering:

```
t=0ms     Event occurs (child speaks, system event, timer fires)
t=0-1ms   Layer 0 rules evaluate → immediate impulse into affect vector
t=1-20ms  Affect vector updates → face receives new mood (next tick cycle)
t=200ms+  LLM processes context → produces emotion suggestion
t=201ms+  Suggestion arrives as impulse → affect vector adjusts
t=220ms+  Face smoothly transitions to LLM-refined emotion
```

The child sees an immediate response (Layer 0) that is refined moments later (Layer 1). The transition is smooth because the integrator interpolates -- there is no visible "jump" from the rule-based response to the LLM-refined response. The LLM impulse simply nudges the affect vector toward a more contextually appropriate position. [Inference]

If the LLM is slow (> 2 seconds) or unavailable, the rule-based response stands. The child still sees an immediate, personality-consistent reaction -- just not one informed by conversational context. [Inference]

---

## 4. Graceful Degradation Patterns

### 4.1 Degradation Scenarios

The personality system must handle four degradation scenarios:

| Scenario | Server State | LLM Available | Latency | Duration |
|----------|-------------|---------------|---------|----------|
| **Normal** | Healthy, connected | Yes | < 500 ms | Indefinite |
| **Slow** | Connected but congested | Yes, delayed | 500 ms - 2 s | Minutes to hours (GPU contention, model loading) |
| **Timeout** | Connected but unresponsive | Effectively no | > 2 s | Minutes (network issue, server overloaded) |
| **Offline** | Not reachable | No | N/A | Minutes to hours (server crash, network outage, Wi-Fi loss) |

### 4.2 Degradation Quality Assessment

What personality quality is achievable at each degradation level?

| Capability | Normal (Full) | Slow (500ms-2s) | Timeout (>2s) | Offline |
|-----------|---------------|-----------------|---------------|---------|
| Temperament baseline | Full | Full | Full | Full |
| Emotional inertia (decay) | Full | Full | Full | Full |
| Idle behavior (SLEEPY, CURIOUS, etc.) | Full | Full | Full | Full |
| Guardrail enforcement | Full | Full | Full | Full |
| Event-driven emotion (boot, battery) | Full | Full | Full | Full |
| Conversation emotion (context-appropriate) | Full | Delayed but accurate | Stale or rules-only | Rules-only (valence mirror) |
| Personality-consistent text | Full | Delayed | Stale or canned | Canned responses or silence |
| Conversational emotional arc | Full | Degraded (gaps) | None | None |
| Empathic mirroring | Full (content-aware) | Delayed | Signal-only (arousal match) | Signal-only |
| Memory-informed personalization | Full | Full (memory is local) | Full (memory is local) | Full (memory is local) |
| TTS with emotion prosody | Full | Delayed | Fallback prosody | No TTS (no text to speak) |

[Inference -- quality levels estimated from capability dependencies]

**Key observation**: Layer 0 capabilities (temperament, inertia, idle, guardrails, events, memory retrieval) are fully maintained at all degradation levels because they run entirely on-device. Only Layer 1 capabilities (contextual emotion, text, arc, deep empathy) degrade. This validates the balanced split -- the personality "floor" is always present. [Inference]

### 4.3 Transition Behavior: How to Degrade Smoothly

The most important design question is not what to lose but **how to lose it** without the child noticing a jarring change.

**Precedent: Cloud-dependent IoT devices** (smart speakers, cloud cameras, connected toys):

- **Amazon Echo / Alexa**: When cloud is unavailable, the device plays a brief error tone and says "I'm having trouble connecting right now." It does not attempt to maintain the illusion of normal function. The transition is explicit and abrupt. [Empirical -- observable behavior]

- **Google Nest**: Similar to Alexa -- explicit "I can't reach Google right now" announcement. No graceful degradation of capability; binary on/off. [Empirical -- observable behavior]

- **Anki Cozmo / Vector**: The Vector robot had both on-device and cloud processing. When cloud was unavailable, it fell back to on-device responses with reduced vocabulary and simpler interactions. The transition was not announced -- the robot simply became "quieter" and less responsive. Users reported this felt natural, like the robot was "in a mood." [Empirical -- user reports]

- **Jibo (consumer social robot, 2017-2019)**: When Jibo's cloud servers were shut down, the robot became essentially non-functional -- it could not understand speech, respond to questions, or display most personality behaviors. This is the worst case of server dependency and a cautionary tale for our design. [Empirical]

**Design principle for our system: Silent degradation, not announced degradation.** The robot should NOT tell the child "I'm having trouble thinking right now" or visibly indicate that something is wrong. Instead, the personality should smoothly reduce capability: [Inference]

1. **Normal to Slow** (< 500 ms to 500 ms-2 s): No visible change needed. The integrator's continuous dynamics absorb the delay -- the affect vector continues evolving from Layer 0 impulses while the LLM catches up. When the LLM response arrives (late), it applies as a gentle correction. The child sees a smooth emotional trajectory with a slightly delayed contextual refinement. [Inference]

2. **Slow to Timeout** (500 ms-2 s to > 2 s): The personality worker stops waiting for LLM impulses and relies entirely on Layer 0. During conversation, this means emotion is driven by signal-level features (speech activity, silence, session timing) rather than content. The robot's emotion becomes less contextually precise but remains personality-consistent. It may feel "distracted" or "in its own world" -- acceptable for a companion robot. [Inference]

3. **Timeout to Offline**: Conversation capability is lost (no text generation, no TTS). The robot enters a conversation-unavailable state. Personality continues through idle behavior. If the child tries to talk, the robot shows THINKING (attempting to connect) then gently returns to its current idle state. No error message, no announcement. The robot simply does not respond verbally. [Inference]

4. **Recovery**: When the server returns, the personality worker resumes sending personality context to the LLM. The next LLM response includes the personality profile. From the child's perspective, the robot gradually becomes "more responsive" -- not a binary switch back to full capability. [Inference]

### 4.4 Should the Robot Announce Degradation?

**No.** For children ages 4-6, announcing "I can't think right now" or "my brain is slow" introduces concepts that violate our design philosophy:

- It implies the robot has a "brain" that can break (deepens anthropomorphism inappropriately -- HC-1). [Inference]
- It creates anxiety ("is my robot broken?") that the child cannot resolve. [Inference]
- It draws attention to a technical state the child does not need to understand. [Inference]

Instead, the robot should express degradation through personality-appropriate affect: a slight drift toward SLEEPY or THINKING during timeout, return to normal idle behavior during offline. The child perceives the robot as "sleepy" or "thoughtful," not "broken." This is consistent with how humans naturally reduce responsiveness when tired or distracted. [Inference]

**Exception**: If a parent/caregiver checks the dashboard, they should see clear server connectivity status. Degradation transparency is for adults, not children. [Inference]

### 4.5 Layer 0 Floor Quality: Is It Enough?

The critical question: is a robot with only Layer 0 personality still an acceptable experience?

**Assessment**: Layer 0 personality maps to Anki Vector's offline mode -- the robot is "quieter," has recognizable personality (temperament baseline, idle behavior, event responses), but cannot engage in contextually appropriate conversation or display content-aware emotion. For our target age group (4-6), this is acceptable for periods of minutes to hours because: [Inference]

1. Children ages 4-6 attribute personality to objects with far less behavioral complexity (stuffed animals, dolls) -- basic temperament and idle behavior are sufficient for perceived "aliveness." [Theory -- Kahn et al., 2012]

2. The robot's physical presence and animated face already communicate personality through the face MCU's breathing, blinking, and gaze behavior -- these continue regardless of server state. [Inference]

3. Most robot interaction sessions are 15-20 minutes. Server outages that span multiple sessions are rare. Layer 0 needs to sustain personality for hours, not days. [Inference]

4. Parents can restart the robot or check the dashboard if behavior seems "off" for extended periods. [Inference]

**However**: If the server is down for an extended period (> 24 hours), the robot should not attempt to maintain the illusion of full capability. It should gracefully enter a persistent SLEEPY state (already part of the idle catalog) that communicates "I'm resting" rather than "I'm broken." This could be triggered by a simple rule: `if server_unreachable > 4_hours: bias_baseline_toward_sleepy`. [Inference]

---

## 5. State Synchronization Between Device and Server

### 5.1 What Needs to Be Synchronized

The personality worker on Pi 5 maintains the full personality state. The server LLM needs a subset of this state to generate personality-consistent responses. The question is what to send, how often, and in which direction.

**State owned by device (personality worker)**:

| State Element | Size (approx) | Update Frequency | Server Needs It? |
|--------------|---------------|-----------------|-----------------|
| Affect vector (valence, arousal) | 8 bytes | 1 Hz | Yes -- for prompt context |
| Current projected mood + intensity | 4 bytes | 1 Hz | Yes -- for prompt context |
| Temperament baseline (v, a) | 8 bytes | Never changes | Yes -- at session start |
| Personality axis positions (5 floats) | 20 bytes | Never changes | Yes -- at session start |
| Conversation state (active, idle, etc.) | 1 byte | Event-driven | No -- server has its own |
| Idle timer (seconds since last interaction) | 4 bytes | 1 Hz | No |
| Session count (total interactions) | 4 bytes | Per-session | Optional |
| Memory tags (semantic, local) | Variable (~1 KB) | Per-session | Yes -- for personalization |
| Guardrail state (active constraints) | ~20 bytes | Event-driven | No -- guardrails are device-only |
| Recent affect trajectory (last 10 points) | 80 bytes | 1 Hz | Optional -- for arc context |

**State owned by server**:

| State Element | Size | Update Frequency | Device Needs It? |
|--------------|------|-----------------|-----------------|
| Conversation history (turns) | Variable (~4 KB) | Per-turn | No -- server manages |
| LLM emotion suggestion | ~20 bytes | Per-turn | Yes -- as impulse input |
| Generated text | Variable | Per-turn | No -- goes to TTS directly |
| TTS prosody tag | ~10 bytes | Per-turn | Partially -- should match personality worker's mood |

### 5.2 Synchronization Direction: Primarily Device-to-Server

The synchronization is primarily **one-way: device --> server**. The personality worker sends a personality profile to the server; the server uses it in the LLM prompt. The server sends back emotion suggestions as events that flow through the normal NDJSON pipeline. [Inference]

**Why not two-way?** Two-way synchronization (server also pushes personality state updates back to device) creates a feedback loop: device sends state --> server modifies state --> device receives modification --> device sends updated state. This is both architecturally complex and potentially unstable. Instead: [Inference]

- **Device is the single source of personality truth.** It maintains the affect vector, applies all rules, enforces guardrails.
- **Server receives personality context** (read-only from its perspective) and uses it to inform LLM behavior.
- **Server sends emotion suggestions** as events (just like any other worker event). The personality worker treats these as impulses, not directives.

This is consistent with PE-8 Option C (prompt injection + output modulation) and the existing BaseWorker architecture where workers communicate through events, not shared state.

### 5.3 The personality.llm.profile Event

The personality worker periodically emits a profile event containing the information the server needs for prompt injection. Based on the analysis above:

```json
{
  "type": "personality.llm.profile",
  "payload": {
    "axes": {
      "energy": 0.40,
      "reactivity": 0.50,
      "initiative": 0.30,
      "vulnerability": 0.35,
      "predictability": 0.75
    },
    "current_affect": {
      "valence": 0.15,
      "arousal": -0.10
    },
    "current_mood": "CONTENT",
    "current_intensity": 0.25,
    "baseline_mood": "NEUTRAL",
    "session_context": {
      "session_count": 42,
      "last_session_mood": "HAPPY",
      "seconds_since_last_session": 14400
    },
    "memory_tags": [
      {"tag": "likes_dinosaurs", "strength": 0.8},
      {"tag": "name_emma", "strength": 1.0},
      {"tag": "ritual_goodbye_wave", "strength": 0.9}
    ],
    "active_guardrails": ["HC-5", "HC-10"],
    "profile_hash": "a3f2b1c4"
  }
}
```

### 5.4 Synchronization Frequency

**At conversation start**: Full profile (all fields). The server needs the complete personality context to construct the system prompt. ~1 KB payload over WebSocket -- negligible. [Inference]

**During conversation**: Incremental updates (current_affect, current_mood, current_intensity) at 1 Hz. The server uses these to maintain awareness of the personality worker's emotional state for prompt injection on subsequent turns. Only ~50 bytes per update. [Inference]

**During idle**: No synchronization needed. There is no server interaction during idle. [Inference]

**On personality state change**: Immediate push of the changed fields (e.g., if a guardrail activates, or if a new memory tag is created). Event-driven, not periodic. [Inference]

### 5.5 Latency Tolerance for Synchronization

The personality profile is used in the LLM system prompt, which is constructed at the start of each turn. Synchronization latency of up to 1 second is acceptable -- the profile is a slowly-changing context, not a real-time control signal. If the latest 1 Hz update is missed, the previous one is close enough. [Inference]

The emotion suggestion from server to device is more latency-sensitive but is not a synchronization problem -- it is a normal event in the NDJSON pipeline with the same latency characteristics as any AI worker event. [Inference]

---

## 6. The Exact Boundary: Responsibility Matrix

### 6.1 Responsibility Matrix

Based on Phase 1 decisions (PE-1 through PE-5) and the analysis above, here is the definitive responsibility matrix for the device/server split:

| Responsibility | On-Device (Pi 5 Personality Worker) | Server (3090 Ti LLM) | Shared |
|---------------|-------------------------------------|---------------------|--------|
| **Affect vector maintenance** | OWNS -- sole writer of (valence, arousal) | -- | -- |
| **Temperament baseline** | OWNS -- static parameters from axes | -- | -- |
| **Decay computation** | OWNS -- exponential decay toward baseline | -- | -- |
| **Impulse application** | OWNS -- applies all impulses to affect vector | -- | -- |
| **Mood projection** | OWNS -- affect --> (mood_id, intensity) | -- | -- |
| **Idle behavior rules** | OWNS -- full idle catalog (Bucket 4) | -- | -- |
| **Event-driven emotion** | OWNS -- boot, battery, error, approach | -- | -- |
| **Guardrail enforcement** | OWNS -- HC-1..10, RS-1..10, duration caps | -- | -- |
| **Initiative triggers** | OWNS -- context suppression, SI=0.30 rules | -- | -- |
| **Emotional memory storage** | OWNS -- local semantic tags, decay management | -- | -- |
| **Conversation emotion selection** | Modulates (final authority) | Suggests (LLM impulse) | LLM suggests, worker integrates |
| **Personality-consistent text** | -- | OWNS -- system prompt + generation | Personality profile sent device-->server |
| **TTS prosody emotion** | Provides final mood for prosody tag | Applies prosody tag from personality worker's mood | Mood flows device-->server |
| **Conversational memory context** | Stores tags locally | Uses tags in system prompt | Tags flow device-->server |
| **Empathic mirroring** | Signal-level (arousal match from speech) | Content-level (understanding why child is sad) | Both contribute impulses |
| **Error recovery emotion** | OWNS -- THINKING impulse + recovery drift | May generate "I'm not sure" text | Independent but aligned |
| **Graceful degradation** | OWNS -- Layer 0 always available | N/A when unavailable | -- |
| **Session management** | Tracks session count, timing | Tracks conversation turns | Both maintain counts |
| **Personality profile for LLM** | Emits personality.llm.profile events | Receives, injects into system prompt | One-way device-->server |

### 6.2 Decision Authority Hierarchy

When device rules and LLM suggestions conflict (e.g., LLM suggests EXCITED at 0.9, but guardrails cap positive arousal during idle), the resolution follows a strict hierarchy:

```
1. Guardrails (HIGHEST) -- hard constraints, never overridden
   e.g., HC-10: no negative affect outside conversation --> veto LLM's SAD suggestion during idle

2. Affect vector integrator -- smooths everything through decay dynamics
   e.g., LLM suggests EXCITED 0.9, but current affect is near NEUTRAL -->
   impulse applied, affect moves toward EXCITED but doesn't jump there instantly

3. Personality modulation -- axis-derived scaling on LLM impulses
   e.g., Energy=0.40 scales arousal impulse by 0.8 --> EXCITED becomes moderate, not extreme

4. LLM suggestion (LOWEST) -- treated as impulse input, not as a command
   The LLM's emotion is a recommendation; the integrator processes it through
   decay, scaling, and guardrails before it reaches the face
```

[Inference -- hierarchy derived from PE-1 (hybrid), PE-8 (both prompt + modulation), and face comm spec Section 7 guardrails]

### 6.3 What the Child Experiences at Each Layer

| Scenario | Layer 0 Only (Offline) | Layer 0 + Layer 1 (Full) |
|----------|----------------------|-------------------------|
| Robot boots up | CURIOUS face for 30-60s, decays to CONTENT | Same |
| Child approaches | Arousal lifts slightly, eyes track | Same + greeting text if conversation starts |
| Child says "I saw a dinosaur today!" | Mild positive impulse (speech detected = social stimulus) | CURIOUS/EXCITED impulse matched to content + "Wow, tell me more about the dinosaur!" |
| Child says "I'm sad" | Arousal drops slightly (low-energy speech detected) | Empathic shift to gentle CONCERNED + "Oh, I'm sorry to hear that. What happened?" |
| Robot idle for 10 minutes | Drifts to SLEEPY per idle catalog | Same (no conversation = Layer 1 irrelevant) |
| Low battery | CONCERNED face at 20%, SLEEPY at 10% | Same |
| Error occurs | THINKING face, recovery drift to baseline | Same + optional "Hmm, let me figure this out" text |

**Critical insight**: The idle experience (which is the majority of the robot's time) is IDENTICAL at Layer 0 and Layer 0 + Layer 1. The child only notices the difference during conversation. This means the degradation primarily affects active conversation sessions, not the robot's passive "aliveness." [Inference]

---

## 7. Worker Architecture: PersonalityWorker Design

### 7.1 BaseWorker Integration

The personality worker follows the existing BaseWorker pattern exactly. From the codebase (`supervisor_v2/workers/base.py`):

- Separate process, launched by WorkerManager
- NDJSON over stdin (inbound events from Core) and stdout (outbound state to Core)
- Automatic 1 Hz heartbeat via `health_payload()`
- Graceful shutdown on `system.lifecycle.shutdown`
- Domain-based message routing

The personality worker's domain is `"personality"`. All inbound events are prefixed with `personality.*` and routed by WorkerManager. All outbound events use the same prefix.

### 7.2 Event Flow Diagram

```
                    ┌─────────────────────────────────────────────────────┐
                    │              SUPERVISOR (Pi 5)                       │
                    │                                                     │
  ┌──────────┐     │  ┌──────────────────────────────────────────────┐   │
  │ Face MCU │◄────┼──│              Tick Loop (50 Hz)                │   │
  │ (ESP32)  │     │  │                                              │   │
  └──────────┘     │  │  reads: _personality_snapshot                │   │
                    │  │  applies: modulate() or idle mood            │   │
                    │  │  sends: SET_STATE(mood_id, intensity)        │   │
                    │  └─────────┬───────────────▲──────────────────┘   │
                    │            │               │                       │
                    │    routes events     reads snapshot                │
                    │            │               │                       │
                    │  ┌─────────▼───────────────┴──────────────────┐   │
                    │  │       WorkerManager (Core)                  │   │
                    │  │                                              │   │
                    │  │  Routes events by domain prefix:             │   │
                    │  │    personality.* --> PersonalityWorker        │   │
                    │  │    ai.*          --> AIWorker                 │   │
                    │  │                                              │   │
                    │  │  Forwards cross-worker events:               │   │
                    │  │    ai.conversation.emotion                   │   │
                    │  │      --> personality.event.ai_emotion        │   │
                    │  │    personality.llm.profile                   │   │
                    │  │      --> ai worker --> server                │   │
                    │  └──────┬──────────────────────┬──────────────┘   │
                    │         │ stdin                 │ stdin            │
                    │         ▼                       ▼                  │
                    │  ┌──────────────┐    ┌─────────────────┐          │
                    │  │ Personality  │    │   AI Worker      │          │
                    │  │ Worker       │    │                  │          │
                    │  │              │    │ WebSocket ◄──────┼────┐     │
                    │  │ RECEIVES:    │    │ to server        │    │     │
                    │  │  .config.init│    │                  │    │     │
                    │  │  .event.*    │    │ RECEIVES:        │    │     │
                    │  │              │    │  .config.init    │    │     │
                    │  │ EMITS:       │    │  .cmd.*          │    │     │
                    │  │  .state.snap │    │                  │    │     │
                    │  │  .llm.profile│    │ EMITS:           │    │     │
                    │  │  .mood.over  │    │  .conversation.* │    │     │
                    │  └──────────────┘    └─────────────────┘    │     │
                    │                                              │     │
                    └──────────────────────────────────────────────┼─────┘
                                                                   │
                                                            WebSocket
                                                                   │
                                                    ┌──────────────▼─────┐
                                                    │  SERVER (3090 Ti)   │
                                                    │                     │
                                                    │  LLM (Qwen/upgrade) │
                                                    │  - System prompt v2  │
                                                    │    (includes         │
                                                    │     personality      │
                                                    │     profile)         │
                                                    │  - Emotion suggest   │
                                                    │  - Text generation   │
                                                    │                     │
                                                    │  Orpheus TTS        │
                                                    │  - Prosody from      │
                                                    │    personality mood  │
                                                    └─────────────────────┘
```

### 7.3 Inbound Events (Worker Receives)

| Event Type | Source | Payload | Worker Action |
|-----------|--------|---------|---------------|
| `personality.config.init` | Core (on startup) | Axis positions, persistence path, feature flags | Initialize integrator parameters, load memory |
| `personality.event.ai_emotion` | AI worker (via Core) | `{emotion, intensity, session_id, turn_id}` | Convert to impulse, apply personality modulation, inject into affect vector |
| `personality.event.conv_started` | Core | `{session_id}` | Set conversation_active flag, suppress idle rules, reset arc tracking |
| `personality.event.conv_ended` | Core | `{session_id, turns}` | Clear conversation_active, begin post-conversation warm decay, update memory |
| `personality.event.turn_completed` | AI worker (via Core) | `{session_id, turn_id, text_summary}` | Update conversational arc tracking, potential memory tag creation |
| `personality.event.system_state` | Core | `{event: "boot"|"low_battery"|"error"|"shutdown"}` | Inject system event impulse per idle behavior catalog |
| `personality.event.child_approach` | Core (proximity/wake) | `{source: "wake_word"|"button"|"proximity"}` | Arousal lift impulse, transition from idle to alert |
| `system.lifecycle.shutdown` | Core | -- | Persist memory, clean shutdown |

### 7.4 Outbound Events (Worker Emits)

| Event Type | Target | Payload | Frequency |
|-----------|--------|---------|-----------|
| `personality.state.snapshot` | Core (tick loop reads) | `{baseline_mood, baseline_intensity, idle_mood, idle_intensity, emotion_bias, emotional_context, affect_v, affect_a, llm_profile_hash}` | 1 Hz baseline + on significant change |
| `personality.llm.profile` | AI worker (via Core) | Full personality profile (Section 5.3) | At conversation start + 1 Hz during conversation |
| `personality.mood.override` | Core (tick loop) | `{mood_id, intensity, reason, duration_ms}` | Rare -- only for guardrail-triggered overrides |
| `personality.lifecycle.started` | Core | -- | Once, on startup |
| `personality.status.health` | Core | `{affect_v, affect_a, layer, conversation_active}` | 1 Hz (BaseWorker heartbeat) |

### 7.5 Worker Class Shape

Based on the plan file and BaseWorker pattern:

```python
class PersonalityWorker(BaseWorker):
    domain = "personality"

    def __init__(self) -> None:
        super().__init__()
        # Integrator state
        self._affect_v: float = 0.0    # valence [-1, 1]
        self._affect_a: float = 0.0    # arousal [-1, 1]
        self._baseline_v: float = 0.0  # from axes
        self._baseline_a: float = 0.0  # from axes

        # Parameters (set from axis positions on config.init)
        self._decay_rate: float = 0.05
        self._impulse_scale: float = 1.0
        self._noise_amplitude: float = 0.0  # from Predictability

        # State
        self._conversation_active: bool = False
        self._current_mood: str = "NEUTRAL"
        self._current_intensity: float = 0.2
        self._idle_timer_s: float = 0.0
        self._server_available: bool = True
        self._last_snapshot_hash: str = ""

        # Memory
        self._memory_tags: list[dict] = []
        self._persistence_path: str = ""

    async def run(self) -> None:
        """Main loop: 1 Hz integrator tick + snapshot emission."""
        # Wait for config
        await self._configured.wait()
        # Load persisted memory
        self._load_memory()
        # Main loop
        while self.running:
            self._tick_integrator(dt=1.0)
            self._apply_idle_rules()
            self._enforce_guardrails()
            self._project_mood()
            self._emit_snapshot()
            await asyncio.sleep(1.0)

    async def on_message(self, envelope: Envelope) -> None:
        """Route inbound events to handlers."""
        # ... dispatch by envelope.type ...

    def _tick_integrator(self, dt: float) -> None:
        """Decay affect toward baseline."""
        decay = 1 - math.exp(-self._decay_rate * dt)
        self._affect_v += (self._baseline_v - self._affect_v) * decay
        self._affect_a += (self._baseline_a - self._affect_a) * decay
        # Add noise from Predictability axis
        self._affect_v += random.gauss(0, self._noise_amplitude * dt)
        self._affect_a += random.gauss(0, self._noise_amplitude * dt)

    def _apply_impulse(self, target_v: float, target_a: float,
                       magnitude: float) -> None:
        """Inject an impulse into the affect vector."""
        direction_v = target_v - self._affect_v
        direction_a = target_a - self._affect_a
        norm = math.sqrt(direction_v**2 + direction_a**2) or 1.0
        self._affect_v += (direction_v / norm) * magnitude * self._impulse_scale
        self._affect_a += (direction_a / norm) * magnitude * self._impulse_scale
```

### 7.6 Tick Loop Integration

The tick loop (50 Hz) reads the personality worker's snapshot and applies it. From the plan file, refined:

```python
# In TickLoop.__init__:
self._personality_snapshot: PersonalitySnapshot | None = None

# In _handle_worker_events():
if env.type == "personality.state.snapshot":
    self._personality_snapshot = PersonalitySnapshot.from_payload(env.payload)

# In _emit_mcu() — during conversation:
if self._personality_snapshot and self._conversation_emotion:
    mood_id, intensity = self._personality_snapshot.modulate(
        self._conversation_emotion, self._conversation_intensity
    )
    self._face.send_state(mood_id, intensity)

# During idle — apply personality's idle recommendation:
elif self._personality_snapshot and not self._conversation_active:
    snap = self._personality_snapshot
    if snap.idle_mood is not None:
        self._face.send_state(snap.idle_mood, snap.idle_intensity)
```

The tick loop never modifies personality state -- it only reads the latest snapshot. This maintains the "slow state, fast application" principle: personality computation happens at 1 Hz in the worker; the tick loop applies it at 50 Hz. [Inference]

---

## 8. Latency Budget Analysis

### 8.1 Component Latencies

| Component | Operation | Typical Latency | Worst Case | Notes |
|-----------|-----------|----------------|------------|-------|
| **Tick loop** | Read snapshot + apply mood | < 0.1 ms | < 1 ms | Struct read + simple math |
| **Face MCU serial** | Send SET_STATE command | ~2 ms | ~5 ms | 115200 baud, ~20 byte command |
| **Face MCU render** | Apply mood parameters to display | ~4 ms | ~8 ms | LVGL render at 30 FPS |
| **Personality worker** | Integrator tick + rule eval + projection | ~0.5 ms | ~2 ms | Pure math + rule table lookup |
| **Personality worker** | Process AI emotion impulse | ~0.1 ms | ~0.5 ms | Scale + inject into integrator |
| **NDJSON IPC** | Worker stdout --> Core stdin | ~0.5 ms | ~2 ms | Pipe write + JSON parse |
| **AI worker** | Receive WebSocket message + emit event | ~1 ms | ~5 ms | JSON parse + NDJSON write |
| **Server LLM** | Generate emotion + text response | 200-800 ms | 2000 ms | Depends on model, load, sequence length |
| **Server TTS** | Generate speech audio | 100-400 ms | 1000 ms | First-chunk latency; streams thereafter |
| **Network (LAN)** | Pi 5 <--> Server WebSocket RTT | ~2 ms | ~20 ms | Local network, wired preferred |
| **STT (Whisper)** | Transcribe utterance | 500-2000 ms | 3000 ms | CPU-intensive; varies by utterance length |
| **Wake word** | Detect "Hey Buddy" | ~50 ms | ~200 ms | Silero VAD + custom detector |

### 8.2 End-to-End Latency Paths

**Path A: Child speaks --> emotion displayed on face (full pipeline)**

```
Child speaks                                        t = 0 ms
  │
  ├── Wake word detection .......................... t = 50 ms
  ├── Audio streaming to server (via AI worker) .... t = 60 ms
  ├── STT processing on server ..................... t = 60-2060 ms (parallel with streaming)
  ├── LLM generates emotion + text ................. t = 2060-2860 ms
  ├── Emotion event sent via WebSocket ............. t = 2862 ms
  ├── AI worker emits ai.conversation.emotion ...... t = 2863 ms
  ├── Core routes to personality worker ............ t = 2864 ms
  ├── Personality worker processes impulse ......... t = 2864.5 ms
  ├── Next 1 Hz snapshot includes new affect ....... t = 2865-3865 ms (worst: wait for next tick)
  ├── Tick loop reads snapshot ..................... t = 3865 ms
  ├── Tick loop sends SET_STATE to face MCU ........ t = 3867 ms
  ├── Face MCU renders new mood .................... t = 3871 ms
  │
  └── Total: ~3-4 seconds (end-to-end)             t ≈ 3000-4000 ms
```

**This is too slow.** A 3-4 second delay between the child finishing speech and the robot showing an appropriate emotion is noticeable and breaks the illusion of emotional responsiveness.

**Path B: Child speaks --> emotion displayed (with Layer 0 fast path)**

```
Child speaks                                        t = 0 ms
  │
  ├── Wake word detection .......................... t = 50 ms
  │
  ├── FAST PATH (Layer 0):
  │   ├── Speech activity detected (VAD signal) .... t = 50 ms
  │   ├── Personality worker: "speech started"
  │   │   impulse (arousal lift, mild positive) .... t = 52 ms
  │   ├── Next snapshot (event-triggered, not 1 Hz). t = 53 ms
  │   ├── Tick loop applies: slight arousal lift ... t = 54 ms
  │   ├── Face shows ATTENTIVE/engaged expression .. t = 58 ms
  │   └── Latency: ~8 ms from speech detection      ◄── FAST RESPONSE
  │
  ├── SLOW PATH (Layer 1, parallel):
  │   ├── Audio streaming + STT + LLM .............. t = 2860 ms
  │   ├── Emotion impulse arrives .................. t = 2864 ms
  │   ├── Affect vector adjusts smoothly ........... t = 2865 ms
  │   ├── Face transitions to content-appropriate
  │   │   emotion (e.g., CURIOUS, EMPATHETIC) ...... t = 2870 ms
  │   └── Latency: ~2.8 s from speech detection     ◄── REFINED RESPONSE
  │
  └── Child perceives: immediate attentive reaction,
      followed by smooth transition to contextual emotion
```

**This is the key architectural insight.** The Layer 0 fast path provides an immediate, personality-consistent reaction within one tick cycle (~20 ms). The Layer 1 slow path refines the emotion with contextual understanding 2-3 seconds later. The integrator ensures the transition between fast and slow responses is smooth -- no visible jump. [Inference]

**Path C: Idle behavior (no server involved)**

```
Idle timer crosses 5-minute threshold              t = 0 ms
  │
  ├── Personality worker: idle rule fires .......... t = 0.5 ms
  ├── SLEEPY impulse injected into integrator ...... t = 0.6 ms
  ├── Snapshot emitted (event-triggered) ........... t = 1 ms
  ├── Tick loop reads snapshot ..................... t = 1-20 ms (next tick)
  ├── Face MCU receives SET_STATE .................. t = 22 ms
  ├── Face begins transition to SLEEPY ............. t = 26 ms
  │
  └── Total: < 30 ms from rule trigger              FAST
```

### 8.3 Latency Budget Breakdown

| Budget Category | Allocated Time | Actual (Typical) | Margin | Notes |
|----------------|---------------|-------------------|--------|-------|
| **Tick loop cycle** | 20 ms (50 Hz) | ~2-5 ms | 15 ms+ | Comfortable headroom |
| **Personality snapshot** | 1000 ms (1 Hz baseline) | ~0.5 ms compute | ~999 ms | Event-driven emission closes gap for urgent events |
| **Layer 0 fast response** | 20 ms (one tick) | ~8-20 ms | Minimal but sufficient | Must fit within one tick cycle |
| **Layer 1 LLM response** | 2000 ms (target) | 200-800 ms (good model) | 1200 ms+ | Budget for 2x peak load |
| **Layer 1 emotion-to-face** | 100 ms (after LLM) | ~30 ms | 70 ms | Pipeline: impulse --> snapshot --> tick --> face |
| **End-to-end speech-to-emotion** | 3000 ms (acceptable) | ~2800 ms | 200 ms | Tight but acceptable with fast-path mitigation |
| **Idle rule-to-face** | 50 ms | ~26 ms | 24 ms | No server dependency |
| **Graceful degradation detection** | 2000 ms (timeout) | N/A | N/A | Timer-based; after 2s without LLM response, Layer 0 stands |

### 8.4 Bottleneck Analysis

| Bottleneck | Severity | Mitigation |
|-----------|----------|------------|
| **STT latency** (500-2000 ms) | High -- dominates end-to-end path | Stream audio to server for incremental transcription; consider server-side Whisper for lower latency |
| **LLM generation** (200-800 ms) | Medium-high -- second largest contributor | Model upgrade (PE-6) may improve. Speculative emotion prediction from partial transcription. |
| **1 Hz snapshot rate** | Medium -- can add up to 1000 ms in worst case | Mitigated by event-triggered emission for high-priority events (emotion impulses, guardrail triggers) |
| **Personality worker process overhead** | Low -- NDJSON IPC adds ~1 ms | Acceptable; process isolation is worth the overhead |
| **Network RTT** | Low -- LAN, ~2 ms | Only relevant if Wi-Fi, which could spike to 20-50 ms |

### 8.5 Pipelining Opportunities

1. **Speculative fast-path emotion**: When speech is detected, the personality worker can immediately inject a generic "attentive" impulse (slight arousal lift, slight positive valence). This provides an immediate facial response while the full pipeline processes. The subsequent LLM emotion refines the affect vector smoothly. [Inference]

2. **Streaming LLM emotion**: If the server can emit an emotion suggestion based on partial transcription (before generating the full text response), the affect vector can begin adjusting earlier. The emotion arrives 500-1000 ms before the text, allowing the face to lead the voice -- which is actually more natural (humans show facial emotion before speaking). [Inference]

3. **Parallel TTS and emotion**: The server currently generates text then TTS sequentially. If emotion is emitted with the text (before TTS), the face can display the emotion while TTS is still processing audio. The face leads the voice by 100-400 ms, which matches natural human behavior. [Inference]

4. **Tick loop interpolation**: The tick loop runs at 50 Hz but receives snapshots at 1 Hz. Between snapshots, the tick loop can interpolate the affect vector's predicted decay trajectory, providing smoother transitions. This is a pure on-device optimization with no server dependency. [Inference]

---

## 9. Design Recommendations

### 9.1 The Split: What Each Side Owns

**Recommendation: PE-9 Option C (Balanced Split) with these specific boundaries:**

**On-device personality worker (always running, zero server dependency)**:
- Affect vector: sole writer, decay computation, impulse application, bounds enforcement
- Temperament: static baseline from axis positions
- Idle behavior: full catalog from Bucket 4 (boot CURIOUS, idle SLEEPY drift, battery CONCERNED, etc.)
- Guardrails: HC-1 through HC-10, RS-1 through RS-10, face comm spec Section 7 constraints
- Initiative: context suppression rules, SI=0.30 frequency limits
- Memory: local semantic tag storage, decay management, tag retrieval
- Mood projection: affect vector --> (mood_id, intensity) with hysteresis
- Fast-path emotion: immediate arousal/valence shift from speech activity signals
- Degradation management: detect server unavailability, maintain Layer 0 personality

**Server LLM (enhances when available, not required)**:
- Context-aware emotion suggestion: understand conversation content --> suggest (emotion, intensity)
- Personality-consistent text: generate responses that match personality profile
- TTS prosody: apply emotion tag from personality worker's final mood projection
- Semantic memory creation: identify what to remember from conversation (personality worker stores it)
- Complex empathic reasoning: understand why the child is feeling a particular way

**Synchronized (device --> server, one-way)**:
- Personality profile: axis positions, current affect, current mood, memory tags
- Session context: session count, time since last session, last session mood

### 9.2 Degradation Strategy

**Recommendation: Silent degradation with personality-appropriate affect.**

- Do not announce server issues to the child
- Express degradation through personality: slight drift toward SLEEPY/THINKING during timeout
- Layer 0 floor quality is acceptable for ages 4-6 (recognizable temperament, idle aliveness, event responses)
- Extended offline (> 4 hours): bias baseline toward SLEEPY ("resting robot")
- Recovery: smooth return to full capability over several turns, not binary switch
- Dashboard: show full server status to parents/caregivers

### 9.3 Synchronization Strategy

**Recommendation: One-way device-->server via personality.llm.profile events.**

- Full profile at conversation start (~1 KB)
- Incremental affect updates at 1 Hz during conversation (~50 bytes)
- No server-->device personality state pushes (avoid feedback loops)
- LLM emotion suggestions flow through normal event pipeline as impulses, not personality state

### 9.4 Latency Mitigation

**Recommendation: Dual-path (fast + slow) with event-triggered snapshots.**

- Layer 0 fast path: speech activity --> immediate arousal lift --> face responds in < 20 ms
- Layer 1 slow path: LLM emotion --> impulse --> smooth transition over 200-800 ms
- Event-triggered snapshot emission: do not wait for 1 Hz tick when a high-priority impulse arrives
- Explore streaming emotion from server (emotion before text, face leads voice)
- Accept 2-3 second end-to-end for contextual emotion; mitigate perceived latency with fast path

### 9.5 Worker Architecture

**Recommendation: Standard BaseWorker with 1 Hz main loop + event-triggered fast path.**

- Domain: `"personality"`
- Main loop: 1 Hz integrator tick, idle rule evaluation, snapshot emission
- Event handler: immediate impulse application + event-triggered snapshot for high-priority events
- Health payload: current affect, active layer, conversation state
- Memory persistence: save to file on session end and shutdown; load on startup
- Process isolation: personality crash does not break tick loop or face rendering (tick loop uses last-known snapshot)

### 9.6 Open Questions for Stage 2

1. **Integrator order**: First-order (exponential decay) is simpler but misses overshoot/bounce. Should Stage 2 specify a second-order option (mass-spring-damper) as a configurable upgrade path?

2. **Fast-path impulse calibration**: How much arousal lift for "speech detected"? Too much = every conversation starts at the same energy. Too little = no visible fast response. Needs empirical tuning.

3. **Profile size optimization**: The personality.llm.profile payload could grow with memory tags. At what point does profile size impact LLM context window budget? Define a max profile size.

4. **Degradation detection threshold**: "Server unavailable" is currently defined as "> 2 seconds without LLM response." Is this the right threshold? Should it be based on consecutive failures rather than single timeout?

5. **TTS prosody routing**: The current pipeline sends TTS prosody from the AI worker directly. Routing through the personality worker's final mood adds one more hop. Is the added latency (~2 ms) worth the consistency guarantee?

---

## Sources

- [Springer: TAME: Time-Varying Affective Response for Humanoid Robots -- Moshkina & Arkin (2011)](https://link.springer.com/article/10.1007/s12369-011-0090-2)
- [ScienceDirect: Emotion and Sociable Humanoid Robots -- Breazeal (2003)](https://www.sciencedirect.com/science/article/abs/pii/S1071581903000181)
- [IEEE: WASABI: Affect Simulation for Agents with Believable Interactivity -- Becker-Asano & Wachsmuth (2010)](https://ieeexplore.ieee.org/document/5764659)
- [Simon & Schuster: The Emotional Brain -- LeDoux (1996)](https://www.simonandschuster.com/books/The-Emotional-Brain/Joseph-LeDoux/9780684836591)
- [Cambridge: Component Process Model of Emotion -- Scherer (2001)](https://doi.org/10.1093/oso/9780195130072.003.0005)
- [ScienceDirect: Explorations in Engagement for Humans and Robots -- Sidner et al. (2005)](https://www.sciencedirect.com/science/article/pii/S0004370205000512)
- [Springer: Social Robots for Long-Term Interaction: A Survey -- Leite et al. (2013)](https://link.springer.com/article/10.1007/s12369-013-0178-y)
- [ACM: Interactive Robots as Social Partners -- Kanda et al. (2004)](https://dl.acm.org/doi/10.1145/1015047.1015058)
- [MIT Media Lab: A Motivational System for Regulating Human-Robot Interaction -- Breazeal (1998)](https://robots.media.mit.edu/wp-content/uploads/sites/7/2015/01/Breazeal-AAAI-98.pdf)
- [ACM: What is Proactive Human-Robot Interaction? -- Zafari & Koeszegi (2024)](https://dl.acm.org/doi/10.1145/3650117)
- [PMC: Robot Initiative in a Team Learning Task -- Chao & Thomaz (2014)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3925832/)
- [Semantic Scholar: The Delicate Balance of Boring and Annoying -- Rivoire (2016)](https://www.semanticscholar.org/paper/The-Delicate-Balance-of-Boring-and-Annoying-:-in-Rivoire/af708f9caa102c90ebf6a4a9c3b26b90282f38b4)
- [PMC: Children's Moral Reasoning About Social Robots -- Kahn et al. (2012)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4137393/)
- [Springer: Emotion and Mood Blending in Embodied Artificial Agents (2022)](https://link.springer.com/article/10.1007/s12369-022-00915-9)
- [Living.AI: EMO Robot](https://living.ai/emo/)
- [Jibo Post-Mortem: Lessons from a Social Robot Startup](https://spectrum.ieee.org/jibo-is-probably-totally-dead-now)
