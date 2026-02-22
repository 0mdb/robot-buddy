# Bucket 3: Child-Robot Relationship Development

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-4 (Per-Child Adaptation) and novelty management strategy

---

## Table of Contents

1. [Longitudinal Field Studies](#1-longitudinal-field-studies)
   - 1.1 Kanda et al. (2004): Two-Month Elementary School Trial
   - 1.2 Tanaka et al. (2007): Toddlers and QRIO Over Five Months
   - 1.3 Leite et al. (2014): Empathic Robots and Long-Term Interaction
   - 1.4 Belpaeme et al. (2018): Social Robots in Education
2. [Novelty Effect and Habituation](#2-novelty-effect-and-habituation)
   - 2.1 The Novelty Timeline
   - 2.2 What Extends the Novelty Period
   - 2.3 Cosmetic Variation vs Content Variation
   - 2.4 The Retention Window
3. [Trust Formation and Repair](#3-trust-formation-and-repair)
   - 3.1 Children's Trust in Robots vs Humans
   - 3.2 Age-Dependent Forgiveness
   - 3.3 Trust Repair Protocol for Ages 4-6
4. [Consistency vs Adaptability](#4-consistency-vs-adaptability)
   - 4.1 Fixed Personality vs Per-Child Adaptation
   - 4.2 Shared Rituals as Sustained Engagement
   - 4.3 Memory-Based Personalization vs Trait Modification
5. [Novelty Management Within 25% Variation Budget](#5-novelty-management-within-25-variation-budget)
   - 5.1 The Predictability Budget
   - 5.2 Variation Categories and Allocation
   - 5.3 Expression Reuse Frequency
   - 5.4 Estimated Habituation Extension
6. [Synthesized Novelty Timeline](#6-synthesized-novelty-timeline)
7. [Design Recommendations](#7-design-recommendations)

---

## 1. Longitudinal Field Studies

### 1.1 Kanda et al. (2004): Two-Month Elementary School Trial

The foundational study on child-robot relationship development over time. Kanda, Hirano, Eaton, and Ishiguro (2004) deployed an interactive humanoid robot (Robovie) in a Japanese elementary school for two months, with children interacting across 32 sessions of approximately 30 minutes each. This remains one of the longest controlled field trials in child-robot interaction research. [Empirical]

**Engagement patterns across 32 sessions**:

The study documented a clear engagement trajectory with three distinct phases:

1. **Initial exploration (sessions 1-5)**: Children were highly engaged, interacting with the robot frequently and exploring all available interaction modalities -- speech recognition, touch sensors, physical gestures. Interaction time was highest during this period. [Empirical]

2. **Decline phase (sessions 6-15)**: Interaction frequency and duration dropped significantly. Many children reduced their engagement to brief, routine interactions. This corresponded to the novelty cliff. [Empirical]

3. **Stabilization/differentiation (sessions 16-32)**: The children split into two groups. Some maintained consistent engagement throughout the study; others effectively abandoned interaction. The differentiating factor was the quality of the robot's social behavior -- specifically, whether it made personal remarks and demonstrated memory of prior interactions. [Empirical]

**Graduated introduction of new behaviors**:

Kanda et al. used a deliberate strategy of introducing new interactive capabilities gradually based on cumulative interaction time, not calendar time. The robot's behavioral repertoire was tiered:

| Cumulative Interaction Time | New Behaviors Introduced |
|----------------------------|-------------------------|
| 0-60 min | Basic conversation, handshakes, body identification game |
| 60-120 min | Rock-paper-scissors, exercise routines, hugs |
| 120-180 min | Singing, pointing to objects in environment |
| 180+ min | Personal remarks referencing past interactions |

This graduation strategy ensured that children who interacted more frequently were rewarded with new capabilities, while children who interacted less were not overwhelmed. The rate was approximately one new behavior type per 60-90 minutes of cumulative interaction. [Empirical]

**Personal remarks and memory**:

The robot's ability to make personal remarks -- referencing past interactions, remembering the child's name, commenting on interaction frequency -- was the single strongest predictor of sustained engagement. Children who experienced personal remarks interacted with the robot for significantly longer than those who did not (due to not having reached the cumulative time threshold). [Empirical]

Critically, children who received personal remarks were more likely to describe the robot as a "friend" rather than a "toy" or "machine" in post-study interviews. The transition from treating the robot as a novelty object to treating it as a social partner was mediated by the robot's demonstration of memory and recognition. [Empirical]

**The novelty-to-relationship transition**:

Kanda et al. identified the key insight that drives this entire bucket: **sustained engagement requires transitioning from novelty-driven interaction to relationship-driven interaction.** Children who made this transition maintained engagement through all 32 sessions. Those who did not dropped off after the novelty phase. The transition was facilitated by: (a) personal memory and recognition, (b) graduated behavioral complexity, and (c) consistent social behavior patterns. [Empirical]

**Design implication**: Our robot must have a relationship-building strategy, not just an entertainment strategy. Persistent memory (even minimal -- name, favorite topics, shared rituals) is essential for the novelty-to-relationship transition. Without it, engagement will follow the novelty curve and decline after the first week. [Inference]

**Citation**: Kanda, T., Hirano, T., Eaton, D., & Ishiguro, H. (2004). Interactive robots as social partners and peer tutors for children: A field trial. *Human-Computer Interaction*, 19(1-2), 61-84.

### 1.2 Tanaka et al. (2007): Toddlers and QRIO Over Five Months

Tanaka, Cicourel, and Movellan (2007) placed Sony's QRIO humanoid robot in a classroom of 18-24 month-old toddlers at a University of California San Diego early childhood education center. The study ran for 45 sessions over approximately five months, making it one of the longest naturalistic studies of child-robot interaction. [Empirical]

**Transition from toy to peer**:

The study documented a remarkable developmental progression in how children categorized and interacted with QRIO:

- **Phase 1 (sessions 1-15)**: Children treated QRIO primarily as a novel object. They touched it, poked it, inspected it physically. Interaction patterns resembled exploration of a new toy. [Empirical]

- **Phase 2 (sessions 16-30)**: Children began treating QRIO as something between a toy and a social agent. They directed social behaviors toward it (waving, showing objects) but also engaged in rough physical interactions (pushing, hitting) that they would direct at objects but not peers. [Empirical]

- **Phase 3 (sessions 31-45)**: Children predominantly treated QRIO as a peer. They touched it gently (similar to how they touched other children), engaged in care-giving behaviors (helping it stand when it fell, patting its head), and showed concern when it appeared to malfunction. Aggressive physical interactions decreased significantly. [Empirical]

**Care-giving attachment behaviors**:

The most striking finding was the emergence of care-giving attachment in Phase 3. When QRIO fell down:

- In early sessions: children cried or showed distress (novelty-disruption response). [Empirical]
- In later sessions: children approached and helped QRIO stand by pushing its back or pulling its hand -- the same behaviors they used to help peers. [Empirical]
- Some children covered QRIO with a blanket when it sat down, mimicking care-giving behaviors they had experienced from adults. [Empirical]

This represented a genuine shift in the children's mental model of QRIO: from object to social entity deserving of care. [Empirical]

**Developmental implications**:

Tanaka et al. argued that prolonged exposure to a social robot during early development can support socialization -- children practiced social skills (turn-taking, gentle touch, care-giving) with the robot that transferred to peer interactions. However, the authors noted this was observed in toddlers (18-24 months), not preschoolers (4-6 years). [Empirical]

**Relevance to our design**: Although our target audience is older (4-6 vs 18-24 months), the trajectory from novelty-object to social-partner is likely universal, though faster in older children who already have established social schemas. The key takeaway is that the transition requires time and consistent social behavior from the robot. A robot that behaves inconsistently or "breaks character" will be reclassified as a toy. [Inference]

**Warning**: The care-giving behaviors observed are a double-edged sword. While they indicate successful socialization, they also indicate attachment. For our robot, we want engagement without dependency -- the robot should be treated as a fun companion, not as an entity requiring the child's care. Expressing vulnerability sparingly (Vulnerability Display axis at 0.35) helps calibrate this. [Inference -- constrained by Bucket 0 HC-5]

**Citation**: Tanaka, F., Cicourel, A., & Movellan, J. R. (2007). Socialization between toddlers and robots at an early childhood education center. *Proceedings of the National Academy of Sciences*, 104(46), 17954-17958.

### 1.3 Leite et al. (2014): Empathic Robots and Long-Term Interaction

Leite, Martinho, and Paiva (2014) conducted a landmark study comparing empathic and non-empathic robot behavior in sustained interaction with children over five weeks. Children played a chess-like game with an iCat social robot in repeated sessions, with one condition featuring an empathic robot (responding to the child's apparent emotional state during gameplay) and one featuring a non-empathic robot (same game behavior but no emotional responsiveness). [Empirical]

**Empathic responsiveness as anti-habituation tool**:

The central finding: **children's social engagement with the empathic robot did not show the typical habituation decline observed with the non-empathic robot.** Specifically:

- Non-empathic robot: Children's social behaviors (smiling at the robot, talking to it, looking at its face) declined steadily across the five weeks, following the standard novelty-habituation curve. [Empirical]
- Empathic robot: Children's social behaviors remained relatively stable across the five weeks, with no statistically significant decline in social presence measures. [Empirical]

**Why empathic responses resist habituation**:

Leite et al. proposed that empathic responses are inherently anti-habituating because **each empathic response is contextually unique**. When a child loses a game piece and the robot says "Oh no, that's tough" with a concerned expression, that specific response is tied to a specific moment. The next time the child loses a piece, the context is different (different game state, different emotional trajectory), so the empathic response -- even if structurally similar -- feels fresh. [Theory]

In contrast, non-empathic social behaviors (generic encouragement, fixed congratulations) are the same regardless of context. The child quickly learns the robot's repertoire and habituates to it. [Theory]

**Social presence maintenance**:

The study measured social presence -- the degree to which the child treated the robot as a social entity rather than a machine. The empathic robot maintained significantly higher social presence over the five-week period. Children continued to attribute emotions and intentions to the empathic robot at the same rate across sessions, while attribution to the non-empathic robot declined. [Empirical]

**Key finding for our design**: Empathic responsiveness is not a "nice-to-have" feature -- it is the strongest documented mechanism for sustaining child-robot engagement beyond the novelty period. For our personality engine, this means Layer 1 (language-enhanced personality with contextual emotional responses) is not optional for long-term engagement. Layer 0 alone will follow the non-empathic habituation curve. [Inference]

**Practical implication**: The personality engine's ability to generate contextually appropriate emotional responses -- the right emotion at the right intensity for the specific conversational moment -- is the primary anti-habituation mechanism. This justifies investing in a more capable server LLM (PE-6) and comprehensive prompt engineering (PE-8). [Inference]

**Citation**: Leite, I., Martinho, C., & Paiva, A. (2014). Social robots for long-term interaction: A survey. *International Journal of Social Robotics*, 5(2), 291-308. See also: Leite, I., Castellano, G., Pereira, A., Martinho, C., & Paiva, A. (2014). Empathic robots for long-term interaction: Evaluating social presence, engagement and perceived support in children. *International Journal of Social Robotics*, 6(3), 329-341.

### 1.4 Belpaeme et al. (2018): Social Robots in Education

Belpaeme, Kennedy, Ramachandran, Scassellati, and Tanaka (2018) published the most comprehensive review of social robots in educational contexts, synthesizing 101 studies on robot tutoring, robot-assisted language learning, and robot-facilitated social interaction. While focused on education rather than companionship, the findings on sustained engagement are directly applicable. [Empirical]

**Children's sustained engagement over educational sessions**:

The review identified several consistent patterns across the 101 studies:

- **Physical embodiment consistently outperforms virtual agents** for sustained engagement. Children attend longer, learn more, and report higher enjoyment with physical robots than with on-screen agents doing the same task. This advantage persists across multiple sessions. [Empirical]

- **Social behavior is the differentiator, not intelligence.** Robots that exhibited social behaviors (gaze following, gestures, emotional expressions, use of the child's name) produced better learning outcomes than robots that were task-focused only. Critically, the social behaviors did not need to be sophisticated -- simple contingent responses (nodding when the child speaks, showing interest expressions during explanations) were sufficient. [Empirical]

- **Personalization predicts sustained engagement.** Studies that incorporated personalization -- remembering the child's performance history, adapting difficulty, referencing past sessions -- showed lower dropout rates and higher engagement in later sessions. [Empirical]

**What predicts long-term engagement vs dropout**:

Belpaeme et al. identified four factors that predicted whether children maintained engagement across multiple sessions:

1. **Contingent social responses** -- the robot reacting appropriately to what the child does and says. [Empirical]
2. **Memory and personalization** -- the robot demonstrating knowledge of the child's history. [Empirical]
3. **Appropriate challenge level** -- neither too easy (boring) nor too hard (frustrating). [Empirical]
4. **Social role framing** -- children who perceived the robot as a peer or tutor (vs a toy or tool) maintained higher engagement. [Empirical]

**Role of personality and social behavior in learning outcomes**:

A key finding: **robots with consistent social personality produced better learning outcomes than robots with task-only behavior**, even when the task content was identical. The social personality served as a "wrapper" that kept children engaged long enough to learn. [Empirical]

However, Belpaeme et al. noted an important caveat: **no study in the review demonstrated that per-child personality adaptation improved outcomes over a fixed but socially rich personality.** The benefits came from having personality and social behavior at all, not from tailoring it to individual children. [Empirical]

**Design implication**: Our investment in a personality engine is validated by the education literature -- personality and social behavior drive sustained engagement. But the case for per-child personality adaptation (PE-4 Option B) is not supported. A fixed, well-designed personality with memory-based content personalization is the evidence-supported approach. [Inference]

**Citation**: Belpaeme, T., Kennedy, J., Ramachandran, A., Scassellati, B., & Tanaka, F. (2018). Social robots for education: A review. *Science Robotics*, 3(21), eaat5954.

---

## 2. Novelty Effect and Habituation

### 2.1 The Novelty Timeline

Synthesizing data from Kanda et al. (2004), Tanaka et al. (2007), Leite et al. (2014), Serholt & Barendregt (2016), and the broader long-term HRI survey literature (Leite, Martinho, & Paiva, 2013), the following novelty timeline emerges for child-robot interaction:

| Phase | Duration | What Happens | Engagement Level | Key Mechanism |
|-------|----------|-------------|-----------------|---------------|
| **Peak novelty** | Days 1-3 | Child explores everything: voice, touch, expressions, reactions. Every robot behavior is interesting. High frequency of interaction. | Very high (90-100%) | Pure novelty. Robot behavior quality is irrelevant -- the child is engaged regardless. [Empirical] |
| **Novelty cliff** | Days 4-7 | Interest drops sharply. Child has explored the robot's behavioral repertoire and found the boundaries. "I've seen everything it can do." Interaction frequency may drop 40-60%. | Declining (50-70%) | Repertoire exhaustion. Children have mapped the robot's capabilities and found them finite. [Empirical] |
| **Retention window** | Weeks 2-3 | Critical differentiation period. Children who have formed a social connection (through memory, personal interaction, shared experience) persist. Children who viewed the robot primarily as a novelty disengage. | Diverging: Connected 60-80%, Unconnected 20-40% | Relationship vs novelty. This is where personality and memory determine long-term trajectory. [Empirical/Inference] |
| **Habituation** | Weeks 4-8 | Robot becomes a familiar fixture. Interaction is routine, not exciting. Engagement stabilizes but at lower intensity than novelty phase. Even connected children show reduced enthusiasm. | Stabilizing (40-60%) | Normalization. The robot is part of the child's world, not a special event. [Empirical] |
| **Equilibrium** | Months 2+ | Engagement depends entirely on relationship quality and content value. Robot personality, memory, and empathic responsiveness determine whether interactions feel worthwhile. Novelty plays no role. | Stable (30-50%) | Intrinsic value. Does the child enjoy talking to the robot? Does the robot add something to the child's life? [Empirical/Inference] |

**Important caveats**:
- These timelines assume daily or near-daily interaction opportunities. Less frequent interaction stretches the timeline proportionally. [Inference]
- Individual variation is substantial. Some children habituate in days; others maintain novelty-level engagement for weeks. [Empirical]
- The percentages are synthesized estimates, not precise measurements from any single study. They represent the central tendency across multiple studies with different robots, age groups, and contexts. [Inference]

### 2.2 What Extends the Novelty Period

Based on converging evidence from the longitudinal studies reviewed above, several factors extend the novelty period and delay the onset of the novelty cliff:

**A. Graduated behavior introduction (Kanda et al., 2004)**

Withholding behavioral capabilities and introducing them gradually -- tied to cumulative interaction time, not calendar time -- extends novelty by ensuring the child always has something new to discover. The robot's behavioral space appears larger than it actually is because capabilities are revealed over time. [Empirical]

**Design mapping**: Our robot can graduate conversational topics, expression combinations, gesture variations, and ritual complexity over cumulative interaction hours. This is a Layer 1 capability (requires LLM awareness of interaction history). [Inference]

**B. Memory and personalization (Kanda et al., 2004; Belpaeme et al., 2018)**

A robot that remembers the child's name, references past conversations, and builds on shared experiences creates a sense of progressive relationship development. Each interaction feels like the next chapter of an ongoing story, not a reset. This is qualitatively different from novelty -- it is relationship continuity. [Empirical]

**Design mapping**: Cross-session memory (PE-2 Option C) is essential. Even minimal memory -- name, 2-3 favorite topics, a greeting ritual, a running joke -- creates the sense of relationship progression that sustains engagement past the novelty cliff. [Inference]

**C. Empathic responsiveness (Leite et al., 2014)**

As discussed in Section 1.3, empathic responses are inherently anti-habituating because they are contextually unique. Each empathic response is a fresh social event, not a replay of a known behavior. [Empirical]

**Design mapping**: Layer 1 contextual emotion is essential. The personality engine must generate emotions appropriate to the specific conversational moment, not generic positive affect. [Inference]

**D. Behavioral unpredictability within consistent personality (Predictability axis)**

Cosmetic variation -- different gestures for the same emotion, slight intensity variation, timing jitter -- prevents the child from fully predicting the robot's next move. This extends novelty modestly (days, not weeks) but compounds with other factors. [Inference]

**Design mapping**: The 25% variation budget (Predictability = 0.75) directly serves this function. See Section 5 for detailed allocation. [Inference]

### 2.3 Cosmetic Variation vs Content Variation

A critical distinction for novelty management:

**Cosmetic variation** changes how the robot expresses the same emotion -- different eye shape, different gesture, slight timing difference, intensity jitter. The emotional content is identical; the surface presentation varies.

**Content variation** changes what the robot is emotionally responding to -- new topics, new game types, new conversational strategies, contextually unique empathic responses. The emotional content itself is novel.

| Variation Type | Novelty Extension | Habituation Resistance | Budget (Predictability 0.75) |
|---------------|------------------|----------------------|------------------------------|
| Cosmetic variation | 1-2 weeks | Low -- children quickly learn the variation space | Within 25% variation budget |
| Content variation | 4-8+ weeks | High -- each instance is genuinely new | Requires Layer 1 (LLM) |
| Combined | 5-10+ weeks | Highest -- surface novelty extends time for content to establish relationship | Both budgets |

[Inference -- estimated from converging evidence across multiple studies]

**Key insight**: Cosmetic variation (the 25% Predictability budget) buys time, but it cannot sustain engagement alone. Content variation (empathic responses, memory-based personalization, graduated behavioral introduction) is what creates lasting engagement. The cosmetic variation budget should be understood as a bridge -- it extends the novelty phase by a few weeks, giving the relationship-building mechanisms (memory, empathy, rituals) time to take hold. [Inference]

### 2.4 The Retention Window

The retention window (weeks 2-3) is the most critical period for our personality engine. This is when the child decides whether the robot is "worth talking to" beyond the novelty period. [Inference]

**What happens during the retention window**:

1. **Novelty-driven children** have exhausted the robot's surface-level behavioral repertoire. If the robot has nothing deeper to offer (no memory, no personalization, no empathic uniqueness), these children disengage. They may return occasionally but will not maintain consistent interaction. [Empirical -- from Kanda et al. 2004 attrition patterns]

2. **Relationship-forming children** begin treating the robot as a social partner. They initiate conversations with specific topics ("Tell me more about space!"), reference past interactions ("Remember when you told me about dinosaurs?"), and develop expectations for the robot's personality ("The robot always gets excited about animals"). [Empirical/Inference]

3. **The split is not about the child's personality alone** -- it is about the quality of the robot's social behavior. Robots with memory and empathic responsiveness retain more children than robots without, regardless of the children's individual characteristics. [Empirical -- Leite et al. 2014]

**Design implication**: The personality engine must be fully operational by the end of week 1. If the robot is still behaving like a novelty toy (stateless, generic responses, no personalization) during the retention window, a significant percentage of children will disengage permanently. The first week is the novelty grace period; the retention window is when personality must deliver. [Inference]

---

## 3. Trust Formation and Repair

### 3.1 Children's Trust in Robots vs Humans

Trust is a prerequisite for sustained social engagement. Children who do not trust a robot will not maintain a relationship with it. Research on children's trust in robots reveals a counterintuitive pattern:

**Robot errors are more forgiven than human errors.** Stower, Calvo-Barajas, Castellano, and Kappas (2024) studied how children react to robot mistakes compared to human mistakes. Children attributed robot errors to mechanical limitations ("it's just a robot, it can't help it") rather than to intentional wrongdoing or incompetence. This "machine forgiveness" effect meant that robot errors were less damaging to trust than equivalent human errors. [Empirical]

The explanation is rooted in attribution theory: children ages 4-6 attribute intentionality to humans but not (consistently) to robots. A human who makes a mistake "should have known better." A robot that makes a mistake "doesn't know any better." This asymmetry provides a natural buffer for robot trust repair. [Theory]

**Design implication**: Our robot's error handling benefits from the machine forgiveness effect. When the robot makes a mistake (wrong emotion, misunderstanding, system error), children are predisposed to forgive it -- provided the robot handles the error gracefully rather than ignoring it. Transparency about errors ("Hmm, I'm confused!") leverages this forgiveness by confirming the child's intuition that the robot is limited. [Inference]

**Citation**: Stower, R., Calvo-Barajas, N., Castellano, G., & Kappas, A. (2024). Shall I trust a robot? Children's trust following robot errors. *International Journal of Social Robotics*, 16, 633-647.

### 3.2 Age-Dependent Forgiveness

While the machine forgiveness effect benefits our design, it is not uniform across ages:

**Younger children (4-5) are less forgiving than older children (6-8).** Zanatto, Patacchiola, Goslin, and Cangelosi (2020) found that younger children's trust in a robot decreased more sharply after errors than older children's trust. The proposed mechanism: younger children have a more fragile and binary trust model -- the robot is either trustworthy or not, with less capacity for nuanced "sometimes wrong but still reliable" judgments. [Empirical]

| Age Group | Trust After Error | Recovery Speed | Mechanism |
|-----------|------------------|----------------|-----------|
| 4-5 years | Sharp decline | Slow -- requires multiple positive interactions | Binary trust model; error shatters "trustworthy" categorization [Empirical] |
| 6-8 years | Moderate decline | Moderate -- recovers within 1-2 positive interactions | Developing nuanced trust; can hold "usually right, sometimes wrong" [Empirical] |
| 9+ years | Mild decline | Fast -- explicit apology is sufficient | Machine attribution fully developed; errors expected [Empirical] |

**Design implication**: For our 4-6 age range, which straddles the trust fragility boundary, error recovery must be swift, visible, and followed by a stability period. A single error handled poorly (or ignored) can undermine trust that took multiple sessions to build. This argues for a conservative trust repair protocol. [Inference]

**Citation**: Zanatto, D., Patacchiola, M., Goslin, J., & Cangelosi, A. (2020). Do children trust robots? Age-based differences in children's trust following robot errors. *Proceedings of the 2020 ACM/IEEE International Conference on Human-Robot Interaction*, 87-95.

### 3.3 Trust Repair Protocol for Ages 4-6

Based on the findings above and the personality engine's affect vector architecture, the following trust repair protocol is recommended:

**Step 1: Immediate acknowledgment (0-500ms)**

When the robot detects an error state (system fault, speech recognition failure, wrong response, LLM timeout), the personality worker injects a THINKING impulse into the affect vector.

- Target mood: THINKING at intensity 0.4-0.5
- The face shows "processing" -- the robot is visibly working on the problem
- Duration: 500ms-2s
- **Critical**: Do NOT show SCARED or SAD. These negative emotions signal to the child that the robot is distressed by the error, which is inappropriate for a caretaker role and can frighten younger children. THINKING conveys "I'm working on it" not "Something is wrong." [Inference -- constrained by HC-10, RS-8]

**Step 2: Verbal acknowledgment (if Layer 1 available)**

The LLM generates a brief, age-appropriate acknowledgment:
- "Hmm, let me think about that!"
- "Oops, I got confused!"
- "Wait, wait... let me try again!"

Tone: light and matter-of-fact. Not apologetic (implies wrongdoing), not dismissive (implies carelessness), not anxious (implies the error is serious). [Inference]

If Layer 1 is unavailable (server down), skip this step. The THINKING face expression alone is sufficient for Layer 0 trust repair.

**Step 3: Positive redirect (1-3s after acknowledgment)**

Shift the affect vector toward a mildly positive state:
- Inject CURIOUS impulse at intensity 0.3
- If in conversation, the LLM steers to a topic the child enjoys or asks a simple question
- If not in conversation, let the affect vector decay naturally toward baseline

The redirect must feel natural, not forced. The robot is moving on, not pretending the error did not happen. [Inference]

**Step 4: Post-repair stabilization (2-3 turns or 30-60 seconds)**

After error recovery, the personality engine enters a stabilization period:
- Reduce variation: temporarily lower the Predictability noise amplitude from 25% to 10%
- Reduce impulse magnitude: scale all impulses by 0.7 for the stabilization period
- Avoid extremes: clamp intensity to 0.2-0.6 range (no very high or very low emotions)

The goal is to provide a "boring but safe" period where the child's trust can re-establish. Surprising behavior immediately after an error -- even positive surprise -- can extend the trust disruption. [Inference]

**Trust repair summary**:

```
Error detected
  --> THINKING @ 0.4 (immediate, face only)
    --> "Oops!" verbal (Layer 1, 0.5-2s)
      --> CURIOUS @ 0.3 redirect (1-3s)
        --> Stabilization period: low variation, moderate intensity, 30-60s
          --> Normal operation resumes
```

**What NOT to do during error recovery**:

| Prohibited Behavior | Reason |
|---------------------|--------|
| Show SCARED or SAD | Signals the error is serious or that the robot is in distress -- frightens young children [HC-10, RS-8] |
| Ignore the error entirely | Children ages 4-5 notice when something goes wrong. Ignoring it feels dishonest and erodes trust faster than acknowledging it [Empirical -- Stower et al. 2024] |
| Over-apologize | Repeated apologies draw attention to the error and make it seem more significant than it was. "Oops!" once is sufficient [Inference] |
| Immediately return to high-energy behavior | Creates emotional whiplash. The transition from error to normal should be gradual, through THINKING to CURIOUS to normal [Inference] |
| Show ANGRY (at self or situation) | Never appropriate for a child-facing caretaker role. Self-directed anger is confusing; situation-directed anger is frightening [HC-10] |

---

## 4. Consistency vs Adaptability

### 4.1 Fixed Personality vs Per-Child Adaptation

The PE-4 decision (per-child adaptation) is one of the most consequential for relationship development. Research provides a clear answer for our age group:

**Fixed personality with content personalization is optimal for ages 4-6. Per-child trait adaptation is not supported.** [Inference, supported by converging empirical evidence]

Evidence chain:

1. **Belpaeme et al. (2018)**: No study in their 101-paper review demonstrated that adapting robot personality traits to individual children improved outcomes over a consistent personality with content personalization. [Empirical]

2. **Kanda et al. (2004)**: The robot that maintained sustained engagement used fixed social behaviors for all children. The personalization that mattered was content-based (personal remarks about the child's history), not trait-based (adjusting the robot's personality to match the child). [Empirical]

3. **Developmental psychology**: Children ages 4-6 are developing their understanding of others as having stable personality traits (the "Big Five" trait attribution begins around age 5-6). A robot that changes its personality traits to match different children would violate this developing schema. The child might perceive the robot as "fake" or "confusing" rather than "adaptable." [Theory]

4. **Tapus & Mataric (2008)** demonstrated personality matching in adult HRI (adapting robot extroversion to match patient personality in rehabilitation). The benefits were significant for adults, but the study explicitly noted that the mechanism was cognitive-behavioral matching -- adults consciously prefer interaction partners who match their communication style. Children ages 4-6 do not have this conscious preference; they respond to social warmth and consistency, not personality matching. [Empirical]

**What should be personalized** (content, not traits):

| Personalized | Not Personalized |
|-------------|-----------------|
| Greeting ritual (child's name, specific greeting phrase) | Energy level, emotional reactivity, initiative |
| Conversation topics (dinosaurs, space, animals) | Baseline mood, decay rate, arousal range |
| Memory references ("Remember when we...") | Personality consistency, predictability |
| Challenge/complexity level | Vulnerability display level |
| Running jokes and callbacks | Affect vector parameters |

[Inference -- synthesized from Kanda 2004, Belpaeme 2018, Ligthart 2022]

### 4.2 Shared Rituals as Sustained Engagement

Ligthart, Hindriks, and Neerincx (2022) conducted a study on child-robot interaction that produced one of the most actionable findings for personality design: **shared rituals are the strongest mechanism for sustained engagement in long-term child-robot interaction.** [Empirical]

The study examined children's interactions with a social robot over 5 sessions across 2 months, focusing on what behaviors predicted continued engagement. The findings:

- **Greeting rituals** -- a specific, consistent way the robot greets the child that evolves slightly over time -- were the single strongest predictor of session-to-session engagement. Children who developed a greeting ritual with the robot (the robot says their name in a specific way, uses a specific expression, references something from last time) maintained engagement across all sessions. [Empirical]

- **Session-opening references to past interactions** ("Last time you told me about your dog!") created a narrative thread that made each session feel connected to a larger story. Children looked forward to what the robot would "remember." [Empirical]

- **Recurring jokes or callbacks** -- shared humorous references that developed over time -- created a sense of intimacy and shared history. The child and robot had "inside jokes." [Empirical]

**Why rituals work better than novelty**:

Rituals create a paradoxical combination of predictability and social meaning:
- The child knows what to expect (satisfaction of predictability need)
- The ritual signals mutual recognition (social bonding)
- Slight variations within the ritual signal "aliveness" (the robot is not just replaying a recording)
- The ritual belongs to the specific child-robot dyad (exclusivity enhances bonding)

[Theory -- supported by developmental psychology literature on ritual in childhood social development]

**Design implication**: Our Predictability axis at 0.75 actually enables ritual formation. A robot with Predictability at 0.30 would vary too much for rituals to take root -- the child could never predict what the robot would do next. At 0.75, the robot's behavior is consistent enough for rituals to form, with the 25% variation providing the subtle freshness that keeps rituals from becoming mechanical repetition. [Inference]

**Implementation**: Rituals are a Layer 1 + Memory capability. The personality engine must:
1. Store a small set of interaction patterns per child (greeting phrase, favorite topic, any running joke)
2. Reproduce these patterns consistently at session start
3. Vary them cosmetically within the 25% budget (slightly different intensity, different gesture, same emotional content)
4. Evolve them slowly (add a new element every few sessions, not every session)

**Citation**: Ligthart, M. E. U., Hindriks, K. V., & Neerincx, M. A. (2022). Memory-based personalization in child-robot interaction: Retrieving and re-using memories of interaction partners. *Frontiers in Robotics and AI*, 9, 819937.

### 4.3 Memory-Based Personalization vs Trait Modification

To make the distinction concrete for the PE-4 decision:

**Memory-based personalization** (recommended):
```
Session 1: Child says "I love dinosaurs!"
  --> Memory stores: {topic: "dinosaurs", valence: +0.6, timestamp: session_1}
Session 2: Robot greets child with CURIOUS + "I've been thinking about dinosaurs!"
  --> Same personality axes, same temperament, same affect vector parameters
  --> Different conversational content, drawn from memory
```

**Trait modification** (not recommended for ages 4-6):
```
Session 1: Child seems shy, speaks quietly, short utterances
  --> System adjusts: Energy 0.40 --> 0.30, Initiative 0.30 --> 0.20
Session 2: Robot is calmer, less expressive, more passive
  --> Different personality parameters based on inferred child characteristics
```

The first approach preserves personality consistency while creating relationship depth. The second approach changes who the robot "is" based on who the child "is" -- which is both technically harder (requires child personality inference from limited signals) and developmentally inappropriate (children expect consistent personalities in social partners). [Inference]

---

## 5. Novelty Management Within 25% Variation Budget

### 5.1 The Predictability Budget

With Predictability at 0.75, the robot's behavior is 75% consistent and 25% variable. This is a deliberate design choice that balances two competing needs:

1. **Consistency** (75%): Children ages 4-6 need predictability for safety, trust, and ritual formation. A consistent personality allows the child to form a mental model of "who the robot is." [Theory -- developmental psychology]

2. **Variation** (25%): Pure consistency leads to staleness. The child fully predicts every behavior, and the robot becomes "boring." Cosmetic variation within the consistent personality framework prevents this. [Inference -- from novelty/habituation research]

The 25% variation budget is not a single number -- it must be allocated across specific dimensions of behavior.

### 5.2 Variation Categories and Allocation

| Variation Category | Budget | Mechanism | Example | Anti-Habituation Effect |
|-------------------|--------|-----------|---------|------------------------|
| **Gesture variation** | 10% | Different gesture selected from mood-appropriate set | HAPPY shown with NOD (60%), TILT (20%), BOUNCE (10%), no gesture (10%) | Prevents "every time I tell a joke it does the same thing" [Inference] |
| **Intensity micro-variation** | 5% | Gaussian jitter on projected intensity | HAPPY @ 0.6 displayed as 0.55-0.65 | Prevents exactly identical expressions -- subtle but prevents uncanny repetition [Inference] |
| **Timing variation** | 5% | Gaussian jitter on idle transitions and response timing | SLEEPY onset at 5 min +/- 1.5 min; response emotion delay 200-400ms | Prevents clockwork predictability in idle behavior [Inference] |
| **Contextual surprise** | 5% | Occasional unexpected-but-appropriate emotional response | Robot shows CURIOUS instead of expected HAPPY when child shares good news (curiosity about the details) | Highest anti-habituation per percentage point -- genuine surprise within personality bounds [Inference] |

**Total: 25%** -- matches the Predictability axis budget exactly.

**Implementation through the affect vector**:

These variations are not implemented as separate systems. They operate through the same decaying integrator:

- **Gesture variation**: During mood projection, the gesture selection function draws from a personality-weighted probability distribution rather than a deterministic mapping. The distribution is parameterized by the current mood and the Predictability axis.

- **Intensity micro-variation**: Gaussian noise with standard deviation = (1 - Predictability) * 0.1 = 0.025 is added to the projected intensity at render time. This produces +/- 0.05 variation at the 2-sigma level.

- **Timing variation**: Idle transition timers use Gaussian jitter with standard deviation = (1 - Predictability) * timer_base * 0.3. For a 5-minute SLEEPY timer, this produces +/- 22 seconds of variation at 1-sigma.

- **Contextual surprise**: With probability = (1 - Predictability) * 0.2 = 0.05 (5%), the affect vector projection selects the second-nearest mood instead of the nearest, provided it is within a defined similarity threshold. This produces occasional "interesting" emotion choices that are still contextually reasonable.

[Inference -- engineering design based on Predictability axis semantics]

### 5.3 Expression Reuse Frequency

How often can the robot show the same expression before it feels stale?

No single study directly answers this question, but converging evidence from animation research, HRI, and UX design provides estimates:

| Expression Category | Reuse Tolerance | Evidence Basis |
|--------------------|----------------|----------------|
| **Greeting expression** (session opener) | Every session -- but must include cosmetic variation | Rituals benefit from repetition; staleness prevented by 25% variation [Inference from Ligthart 2022] |
| **Common moods** (HAPPY, CURIOUS, NEUTRAL) | 10-15 uses per session before fatigue | High-frequency moods rely on intensity and gesture variation to prevent staleness [Inference] |
| **Uncommon moods** (CONFUSED, THINKING) | 3-5 uses per session before they feel forced | Rarer moods carry more salience; overuse undermines their signal value [Inference] |
| **Negative moods** (SAD, SCARED, ANGRY) | 1-2 uses per session (already capped by guardrails) | Negative moods are attention-grabbing; repetition is alarming, not stale [Inference -- constrained by face comm spec section 7] |
| **Transitional expressions** (mood shifts visible to child) | 4-8 per session (during conversation) | Each transition should feel motivated by conversational context [Inference from Leite 2014] |
| **Idle expressions** | 1-2 per hour of idle | Minimal visibility; staleness is less of a concern because the child may not be watching [Inference] |

**Key principle**: Expression reuse is acceptable when each instance is contextually motivated. "The robot is happy because I said something funny" does not feel like repetition even if HAPPY has been shown ten times, because each instance has a unique trigger. "The robot is happy for no reason" feels repetitive after 2-3 instances because the instances are indistinguishable. Context is the primary anti-staleness mechanism; cosmetic variation is secondary. [Inference]

### 5.4 Estimated Habituation Extension

How much additional engagement time does the 25% variation budget buy?

| Variation Component | Estimated Extension | Confidence | Mechanism |
|--------------------|--------------------| -----------|-----------|
| Gesture variation (10%) | 1-2 weeks | Low -- extrapolated from animation research | Prevents surface-level prediction completion |
| Intensity micro-variation (5%) | < 1 week | Very low -- effect is subtle | Prevents uncanny exact repetition |
| Timing variation (5%) | < 1 week | Very low -- mostly affects idle behavior | Prevents clockwork perception |
| Contextual surprise (5%) | 1-2 weeks | Low -- extrapolated from Kanda 2004 behavioral graduation | Creates genuine "I didn't expect that" moments |
| **Combined cosmetic variation** | **3-5 weeks** | **Low-medium** | Compounds multiplicatively, not additively |

[Inference -- no direct empirical data exists for these specific estimates. They are extrapolated from the general novelty/habituation literature and the Kanda et al. 2004 graduated behavior timeline.]

**Comparison to content variation**:

| Variation Source | Habituation Extension | Sustainability |
|-----------------|----------------------|----------------|
| Cosmetic variation (25% budget) | 3-5 weeks | Exhausts -- child eventually maps the variation space |
| Empathic responsiveness (Layer 1) | 8+ weeks, potentially indefinite | Self-renewing -- each response is contextually unique |
| Memory-based personalization | 4-8 weeks per memory type | Moderate -- can feel stale if memory doesn't grow |
| Graduated behavior introduction | 4-6 weeks | Exhausts -- finite repertoire is eventually fully revealed |
| Shared rituals | Potentially indefinite | Self-renewing -- ritual participation creates ongoing social value |

[Inference -- synthesized from all longitudinal studies reviewed]

**Bottom line**: The 25% variation budget buys approximately 3-5 additional weeks of novelty before the child has fully mapped the variation space. After that, sustained engagement depends entirely on Layer 1 content variation (empathic responsiveness, memory, rituals). The cosmetic variation serves as a critical bridge -- it extends the novelty phase long enough for relationship-building mechanisms to take root during the retention window (weeks 2-3). [Inference]

---

## 6. Synthesized Novelty Timeline

Combining the baseline novelty timeline (Section 2.1) with the variation extensions (Section 5.4) and content variation effects:

### 6.1 Without Personality Engine (Current System)

| Week | Phase | Engagement | Notes |
|------|-------|-----------|-------|
| 1 | Peak novelty --> cliff | 90% --> 50% | Child explores, then exhausts, the behavioral space |
| 2-3 | Rapid decline | 50% --> 20% | No memory, no personalization, no empathy -- nothing to sustain engagement |
| 4+ | Abandonment | < 15% | Robot becomes an ignored object on the shelf |

### 6.2 With Personality Engine (Layer 0 + Layer 1)

| Week | Phase | Engagement | Active Mechanisms |
|------|-------|-----------|-------------------|
| 1 | Peak novelty | 90-100% | Novelty drives engagement; personality adds cosmetic variation |
| 2 | Novelty cliff (softened) | 65-75% | Cosmetic variation (25% budget) extends exploration; first rituals forming |
| 3 | Retention window | 55-70% | Memory + rituals differentiate connected vs unconnected children; empathic responses begin to matter |
| 4-5 | Extended novelty tail | 50-65% | Graduated behavior introduction + cosmetic variation still providing some novelty; relationship deepening |
| 6-8 | Habituation | 45-55% | Cosmetic variation fully mapped; engagement depends on empathic responsiveness and rituals |
| 9-12 | Early equilibrium | 40-50% | Novelty plays no role; relationship quality and content value determine engagement |
| 12+ | Mature equilibrium | 35-50% | Stable long-term engagement for children who formed relationships during retention window |

[Inference -- projected from empirical baselines with estimated variation extensions]

**Net effect of personality engine**: Approximately 2-3x longer time to abandonment threshold, with a higher equilibrium engagement level for children who form relationships. The personality engine does not eliminate habituation (nothing can), but it converts a novelty-dependent engagement curve into a relationship-dependent one. [Inference]

### 6.3 Mechanism Activation Timeline

| Mechanism | Activation | Peak Effect | Exhaustion |
|-----------|-----------|-------------|-----------|
| Pure novelty | Day 1 | Days 1-3 | Days 4-7 |
| Cosmetic variation (gestures) | Day 1 | Weeks 1-3 | Weeks 4-6 |
| Cosmetic variation (intensity/timing) | Day 1 | Weeks 1-2 | Weeks 2-4 |
| Contextual surprise | Day 1 | Weeks 2-5 | Weeks 6-8 |
| Greeting ritual | Session 2+ | Weeks 3-6 | Never (self-renewing) |
| Memory-based personalization | Session 3+ | Weeks 3-8 | Slow -- depends on memory growth |
| Empathic responsiveness | Session 1 | Weeks 3+ | Never (contextually unique) |
| Graduated behavior introduction | Week 2+ | Weeks 3-8 | Weeks 8-12 (finite repertoire) |
| Shared rituals and callbacks | Week 2+ | Weeks 4+ | Never (self-renewing) |

[Inference -- timeline estimated from longitudinal study data]

---

## 7. Design Recommendations

### 7.1 PE-4 Decision: Fixed Personality (Option A) + Memory-Based Content Personalization

**Recommendation: PE-4 Option A (fixed personality axes) combined with PE-2 Option C (persistent memory) is the optimal configuration.** [Inference, strongly supported by empirical evidence]

Evidence summary:
- Belpaeme et al. (2018): No study demonstrates per-child trait adaptation improves outcomes for children. [Empirical]
- Kanda et al. (2004): Sustained engagement came from content personalization (personal remarks), not personality adaptation. [Empirical]
- Ligthart et al. (2022): Memory-based personalization produced the strongest sustained engagement. [Empirical]
- Developmental psychology: Children ages 4-6 expect stable personality in social partners. [Theory]

The personality axes (Energy 0.40, Reactivity 0.50, Initiative 0.30, Vulnerability 0.35, Predictability 0.75) should remain fixed for all children and all sessions. What changes is the content -- topics, rituals, memory references, conversational complexity.

### 7.2 Novelty Management Strategy

The novelty management strategy operates on two timescales:

**Short-term (weeks 1-6): Cosmetic variation buys time**

- Deploy the full 25% variation budget from day 1
- Gesture variation (10%): randomize gesture selection within mood-appropriate sets
- Intensity micro-variation (5%): Gaussian jitter on projected intensity
- Timing variation (5%): jitter on idle transitions and response timing
- Contextual surprise (5%): occasional unexpected-but-appropriate emotion selection
- Estimated effect: extends novelty phase by 3-5 weeks

**Long-term (weeks 3+): Content variation sustains engagement**

- Empathic responsiveness: contextually unique emotional responses (Layer 1)
- Memory-based personalization: greeting rituals, topic references, callbacks (Layer 1 + Memory)
- Graduated behavior introduction: reveal new conversational strategies and topics over cumulative interaction time (Layer 1 + Memory)
- Shared rituals: develop child-specific greeting rituals, running jokes, callback references (Layer 1 + Memory)
- Estimated effect: sustains engagement indefinitely for children who formed relationships during the retention window

### 7.3 Trust Repair: Concrete Protocol

Implement the trust repair protocol from Section 3.3:

1. Error detected --> THINKING @ 0.4 (immediate)
2. Verbal acknowledgment: "Oops!" or "Hmm, let me think!" (Layer 1, if available)
3. Positive redirect: CURIOUS @ 0.3 (1-3s after acknowledgment)
4. Stabilization: reduce variation to 10%, clamp intensity 0.2-0.6, for 30-60 seconds
5. Resume normal operation

**Hard rules**:
- Never SCARED or SAD during error recovery
- Never ANGRY during error recovery
- Never ignore errors (silent failure erodes trust faster than acknowledged failure)
- One "Oops!" per error, not repeated apologies

### 7.4 Relationship Development Timeline

The personality engine should be designed with the following developmental timeline in mind:

| Interaction Period | Personality Engine Focus | Key Mechanism |
|-------------------|------------------------|---------------|
| Sessions 1-3 | Make a strong first impression. Show personality clearly. Establish the robot's "character." | Consistent temperament, clear emotional responses, first greeting ritual |
| Sessions 4-8 | Bridge the novelty cliff. Demonstrate memory and recognition. Begin ritual formation. | Name memory, topic callbacks, "Remember when..." references, cosmetic variation |
| Sessions 9-15 | Deepen relationship. Build shared history. Rely less on novelty. | Shared rituals, graduated conversational complexity, empathic responsiveness |
| Sessions 16+ | Maintain equilibrium engagement. Sustain through content quality and relationship depth. | Empathic uniqueness, evolving rituals, memory growth, personality consistency |

[Inference -- timeline mapped from Kanda et al. 2004 session data to our expected interaction pattern of 2-3 sessions per day]

### 7.5 Empathic Responsiveness as Primary Anti-Habituation Mechanism

Leite et al. (2014) provides the clearest single finding for our personality engine design: **empathic responsiveness is the strongest anti-habituation tool available.** [Empirical]

This finding has direct architectural implications:

1. **Layer 1 (LLM-enhanced personality) is not optional for long-term engagement.** Layer 0 alone will follow the non-empathic habituation curve. Children will disengage after the novelty period. [Inference]

2. **Server LLM quality matters for long-term engagement, not just conversation quality.** The ability to generate contextually appropriate emotional responses -- the right emotion at the right intensity for the specific moment -- is what prevents habituation. A weak LLM that produces generic emotions (always HAPPY when the child is happy, always SAD when the child is sad) will habituate. A strong LLM that produces nuanced emotions (CURIOUS when the child is happy about something specific, gentle THINKING when the child is working through something difficult) will not. [Inference]

3. **The personality engine's emotion modulation (PE-8) must enhance empathic quality, not flatten it.** Over-dampening LLM emotions through excessive modulation would reduce empathic responsiveness -- the very mechanism that sustains long-term engagement. The personality worker should modulate for consistency and safety, not for emotional conservatism. [Inference]

### 7.6 Consistency Enables Rituals; Rituals Enable Engagement

The Predictability axis at 0.75 is not just about preventing staleness -- it actively enables the strongest sustained engagement mechanism (shared rituals). [Inference]

The logic:
1. Rituals require predictability -- the child must be able to anticipate the ritual to participate in it
2. Predictability at 0.75 provides enough consistency for ritual formation
3. The 25% variation within the ritual prevents it from feeling mechanical
4. Rituals create social bonding that sustains engagement beyond novelty

A robot at Predictability 0.50 would vary too much for rituals to form. A robot at Predictability 0.95 would be too mechanical for rituals to feel social. The 0.75 position is well-calibrated for ritual-based engagement. [Inference]

### 7.7 The Retention Window Is the Critical Period

If the personality engine has one job, it is to ensure that children who interact during the retention window (weeks 2-3) have sufficient reason to continue. [Inference]

This means:
- By session 3-4, the robot must demonstrate memory of the child (name, at least one topic)
- By session 5-6, a greeting ritual should be forming
- By session 8-10, the child should have experienced at least one contextually unique empathic response that could not have come from a novelty toy

If these milestones are not met, the child will be in the "unconnected" group during the retention window and will likely disengage permanently. The personality engine's design should be evaluated primarily on its ability to hit these milestones. [Inference]

---

## Sources

### Primary Longitudinal Studies

- [ResearchGate: Interactive Robots as Social Partners and Peer Tutors for Children: A Field Trial -- Kanda et al. (2004)](https://www.researchgate.net/publication/3450498_A_Two-Month_Field_Trial_in_an_Elementary_School_for_Long-Term_Human-Robot_Interaction)
- [PNAS: Socialization Between Toddlers and Robots at an Early Childhood Education Center -- Tanaka, Cicourel, & Movellan (2007)](https://www.pnas.org/doi/10.1073/pnas.0707769104)
- [Springer: Social Robots for Long-Term Interaction: A Survey -- Leite, Martinho, & Paiva (2013)](https://link.springer.com/article/10.1007/s12369-013-0178-y)
- [Springer: Empathic Robots for Long-Term Interaction -- Leite, Castellano, Pereira, Martinho, & Paiva (2014)](https://link.springer.com/article/10.1007/s12369-014-0227-1)
- [Science Robotics: Social Robots for Education: A Review -- Belpaeme, Kennedy, Ramachandran, Scassellati, & Tanaka (2018)](https://www.science.org/doi/10.1126/scirobotics.aat5954)

### Trust Formation and Repair

- [Springer: Shall I Trust a Robot? Children's Trust Following Robot Errors -- Stower, Calvo-Barajas, Castellano, & Kappas (2024)](https://link.springer.com/article/10.1007/s12369-023-01045-y)
- [ACM: Do Children Trust Robots? Age-Based Differences -- Zanatto, Patacchiola, Goslin, & Cangelosi (2020)](https://dl.acm.org/doi/10.1145/3319502.3374832)

### Personality Adaptation and Rituals

- [Frontiers: Memory-Based Personalization in Child-Robot Interaction -- Ligthart, Hindriks, & Neerincx (2022)](https://www.frontiersin.org/articles/10.3389/frobt.2022.819937/full)
- [MIT Press: User Modeling for Adaptive Robot-Mediated Interaction -- Tapus & Mataric (2008)](https://robotics.usc.edu/publications/media/uploads/pubs/642.pdf)
- [MIT Media Lab: Social Robots as Embedded Reinforcers of Daily Learning -- Kory-Westlund & Breazeal (2019)](https://www.media.mit.edu/publications/social-robots-as-embedded-reinforcers/)

### Novelty and Habituation

- [ResearchGate: Robots Tutoring Children: Longitudinal Evaluation of Social Engagement -- Serholt & Barendregt (2016)](https://www.researchgate.net/publication/309428505_Robots_Tutoring_Children_Longitudinal_Evaluation_of_Social_Engagement_in_Child-Robot_Interaction)
- [PMC: Robot Initiative in a Team Learning Task -- Chao & Thomaz (2014)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3925832/)
- [Semantic Scholar: The Delicate Balance of Boring and Annoying -- Rivoire (2016)](https://www.semanticscholar.org/paper/The-Delicate-Balance-of-Boring-and-Annoying-:-in-Rivoire/af708f9caa102c90ebf6a4a9c3b26b90282f38b4)

### Safety and Ethics (Cross-Reference)

- [Bucket 0: Safety Psychology & Ethical Constraints](bucket-0-safety-psychology-ethical-constraints.md)
- [Bucket 4: Proactive vs Reactive Behavior](bucket-4-proactive-vs-reactive-behavior.md)
- [Personality Engine Spec -- Stage 1](../personality-engine-spec-stage1.md)

### Developmental Psychology

- [Simply Psychology: Bowlby's Attachment Theory](https://www.simplypsychology.org/bowlby.html)
- [Springer: The Child Factor in Child-Robot Interaction (2024)](https://link.springer.com/article/10.1007/s12369-024-01121-5)
- [Frontiers: Preschoolers' Anthropomorphizing of Robots (2023)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2022.1102370/full)
