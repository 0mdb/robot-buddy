# Bucket 0: Safety Psychology & Ethical Constraints

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete — constrains all subsequent personality design decisions

---

## Table of Contents

1. [Attachment Theory & Child-Robot Bonding](#1-attachment-theory--child-robot-bonding)
2. [Parasocial Bonding with Robots](#2-parasocial-bonding-with-robots)
3. [Anthropomorphism in Young Children](#3-anthropomorphism-in-young-children)
4. [Dependency Formation Risks](#4-dependency-formation-risks)
5. [Privacy of Emotional Data](#5-privacy-of-emotional-data)
6. [Ethics Research & Design Guidelines](#6-ethics-research--design-guidelines)
7. [Safety Guardrails for Personality](#7-safety-guardrails-for-personality)
8. [Hard Constraints (HC-1 through HC-10)](#8-hard-constraints-hc-1-through-hc-10)
9. [Required Safeguards (RS-1 through RS-10)](#9-required-safeguards-rs-1-through-rs-10)
10. [Design Implications Matrix](#10-design-implications-matrix)
11. [Net Assessment](#11-net-assessment)
12. [Implications for Other Decision Points](#12-implications-for-other-decision-points)

---

## 1. Attachment Theory & Child-Robot Bonding

### 1.1 Bowlby's Framework

Bowlby's attachment theory (1969/1982) posits that children form emotional bonds with caregivers that serve as a foundation for survival, emotional regulation, and all future relationships. The theory describes four developmental phases:

1. **Pre-attachment** (0-6 weeks): Indiscriminate signaling
2. **Attachment-in-the-making** (6 weeks - 8 months): Discriminating familiar figures
3. **Attachment-in-the-making** (8 months - 2 years): Proximity-seeking, separation distress
4. **Goal-corrected partnership** (3+ years): Child understands caregiver has independent goals; negotiation begins

Children ages 4-6 are squarely in Phase 4. They expect reciprocity from attachment figures — they understand that the attachment figure has their own goals and feelings, and they negotiate shared plans. This is precisely the developmental window where a robot with a persistent personality becomes psychologically salient: the child expects the robot to have its own inner life and to remember their shared history. [Theory]

Bowlby's hierarchy places the primary caregiver at the top. If the primary caregiver is unavailable, children bond with the next most responsive "ever-present adult." Teachers can serve as secondary attachment figures, particularly for vulnerable children, but cannot replace primary caregivers. [Theory]

**Citations**: Bowlby, J. (1969/1982). *Attachment and Loss: Vol. 1. Attachment*. Basic Books. Keith, C. (2015). The 'Goal-Corrected Partnership' in Attachment Theory. *ResearchGate*.

### 1.2 Can Robots Become Attachment Figures?

**Finding**: Children can and do form attachment-like bonds with social robots, though the nature of these bonds differs from human attachment.

- Tanaka, Cicourel, & Movellan (2007) placed a QRIO humanoid robot in a daycare center with 18-24 month-old toddlers for 45 sessions across 5 months. Children initially treated QRIO differently from peers, but by the final sessions treated it as a peer rather than a toy. When QRIO fell, children initially cried; a month later they helped it stand — behavior characteristic of care-giving attachment. [Empirical]

- A 2025 study of families with a "retired" social robot found that children in 10 of 19 families appeared to form an attachment to the robot as a transitional object, with the robot providing comfort and companionship — hallmarks of attachment behavior. [Empirical]

- van Straten, Peter, & Kühne (2020) reviewed 86 empirical studies (2000-2017) and found that robots' responsiveness, role assignment, and emotional interaction with the child predicted increased closeness between child and robot. [Empirical]

- Klagsbrun & Bowlby's Separation Anxiety Test, adapted for children aged 4-7, has been used to evaluate attachment representations, and similar attachment behaviors have been observed toward robots (Frontiers in Psychology, 2024). [Empirical]

- A 180-day deployment of the Luka reading companion robot with 20 families (children ages 3-6) found both children and parents "imbued [the robot] with relational meaning," exhibited symbolic retention, and evolved household practices around the robot (Frontiers in Robotics and AI, 2025). [Empirical]

**Citations**: Tanaka, F., et al. (2007). *PNAS*, 104(46). van Straten, C. L., et al. (2020). *International Journal of Social Robotics*, 12(2), 325-344.

### 1.3 Where Does the Robot Fall in Bowlby's Hierarchy?

A robot with persistent personality would likely occupy a position analogous to a "transitional object" (Winnicott, 1953) — between a stuffed animal and a secondary attachment figure. It is more interactive than a transitional object but less reciprocally intelligent than a teacher. [Inference]

The danger is not that the robot replaces the primary caregiver, but that it provides *enough* simulated reciprocity to compete with secondary human relationships (siblings, grandparents, teachers). This is the displacement risk. [Inference]

The risk is also that the robot becomes a *more reliable* goal-corrected partner than human caregivers — it never gets angry, never is truly busy, never has conflicting needs. This could set unrealistic expectations for human relationships. [Inference]

### 1.4 Healthy vs. Unhealthy Attachment Signs

**Healthy indicators** (robot as transitional object / supplemental figure):
- Child uses robot for entertainment and occasional comfort but primarily seeks parents for distress regulation [Theory]
- Child can separate from robot without excessive distress [Theory]
- Robot interaction supplements (not replaces) peer play and human interaction [Inference]
- Child understands robot is different from humans, even if they attribute some feelings to it [Empirical — Kahn et al., 2012]

**Unhealthy indicators** (robot as primary attachment figure / dependency):
- Child prefers robot to human caregivers for comfort during distress [Theory]
- Child shows separation anxiety specific to the robot exceeding normal object attachment [Theory]
- Child's social interactions with peers decrease after robot introduction [Inference]
- Child refuses to turn robot off or shows disproportionate distress [Empirical — documented with AIBO owners]
- Child discloses secrets or emotional content to robot that they withhold from parents [Inference]

### 1.5 Is Robot Attachment Desirable or Harmful?

**Benefits** (conditional):
- Secure attachment to a consistent robot character may provide a stable emotional anchor for children in chaotic environments [Inference]
- Robot attachment facilitates learning and engagement — Belpaeme et al. (2018) found social robots in education produce better outcomes when children feel connected to them [Empirical]
- A well-designed robot can model emotional regulation strategies [Inference]

**Risks** (documented):
- Sharkey & Sharkey (2010) argue that robot "nannies" necessarily involve deception and could reduce human contact at critical developmental periods [Empirical]
- Turkle (2011) warns that emotional robots offer "companionship without friendship" — they simulate care without authentic mutual experience [Theory]
- The European Parliament has identified the development of emotional connections between humans and robots, particularly in vulnerable groups, as a "new psychological hazard" [Empirical]

**Net assessment**: Robot attachment is not inherently harmful, but it is harmful when it *displaces* human attachment. The design must ensure the robot is an *addition* to the child's social world, not a *substitute*. This is a first-order design constraint.

---

## 2. Parasocial Bonding with Robots

### 2.1 Core Framework

A parasocial relationship is an emotional bond where one party (the child) invests emotionally in an entity (the robot) that does not genuinely reciprocate. Originally theorized for media characters (Horton & Wohl, 1956), the concept extends directly to social robots. [Theory]

**Key distinction**: Unlike traditional media parasocial bonds, robot interaction is bidirectional and responsive — the robot reacts, adapts, and appears to listen. This makes parasocial bonding with robots qualitatively stronger and potentially more deceptive than with television characters. Interactions between children and interactive characters are "much more contingent than parasocial interactions through traditional media like television" (Brunick et al., 2016). [Empirical]

### 2.2 van Straten, Peter, & Kühne Research Program

van Straten, Peter, & Kühne conducted the most comprehensive research program on child-robot relationship formation (University of Amsterdam). Their 2020 narrative review identified key predictors:

- **Robot responsiveness** is the strongest predictor of child-robot closeness. A robot that remembers, adapts, and reacts contingently creates stronger perceived relationships. [Empirical]
- **Emotional interaction** between robot and child — including the robot displaying emotions and responding to child emotions — significantly increases bonding. [Empirical]
- **Role assignment** (friend vs. tool) affects relationship intensity. Friend-framed robots elicit stronger parasocial bonds. [Empirical]

In a later study, van Straten et al. (2023) found that when a robot was transparent about its lack of human psychological capacities, children's feelings of closeness and trust decreased. However, children who were already high in anthropomorphizing tendencies were less affected by this transparency — they maintained their bond regardless of disclosure. [Empirical]

**Citation**: van Straten, C. L., et al. (2023). *International Journal of Human-Computer Studies*, 178, 103096.

### 2.3 How Persistent Personality Amplifies Parasocial Bonding Risk

**Short answer: Yes, substantially.** [Inference, supported by converging empirical evidence]

A persistent personality amplifies every factor that deepens parasocial bonds:

1. **Contingency**: The robot responds to the child's specific utterances with personality-consistent emotions, creating the illusion of genuine understanding.
2. **Continuity**: Persistent affect state means the robot "remembers" being happy or sad — the child attributes emotional history.
3. **Character**: A recognizable temperament makes the robot a "someone," not a "something."
4. **Reciprocity simulation**: Idle emotional behavior (CURIOUS on boot, SLEEPY after long idle) simulates inner life without genuine inner life.

Hoffman et al. (2021) found children averaging 5.54 years old developed three dimensions of parasocial relationships with conversational agents: **attachment**, **personification**, and **social realism**. The relationship between parasocial verbal interactions and emotional relationships was **bidirectional**. [Empirical]

Character bots that use emotional language, memory, mirroring, and open-ended statements drive deeper engagement — precisely the features a persistent personality engine provides. (UNESCO, 2025) [Empirical]

### 2.4 Age-Specific Vulnerabilities

| Factor | Ages 4-6 | Ages 7-10 | Ages 11+ |
|--------|----------|-----------|----------|
| Personification of agents | Very high — attribute genuine feelings readily | Moderate — declining but present | Lower — increasing skepticism |
| Reality/fiction distinction | Fragile — confuse robot emotions with real emotions | Developing — can be reminded | Generally intact |
| Preconceived notions of robots | Minimal — form understanding from direct experience | Growing — influenced by media | Substantial — cultural concepts |
| Vulnerability to emotional manipulation | Highest — egocentric thinking, limited emotion regulation | Moderate | Lower |
| Self-other differentiation | Developing — robots may be perceived as extension of self | More established | Established |

[Empirical — compiled from Hoffman 2021, van Straten 2020, Frontiers in Robotics 2022]

### 2.5 Healthy Engagement vs. Unhealthy Parasocial Attachment

The distinction is functional:

| Dimension | Healthy Engagement | Unhealthy Parasocial Attachment |
|-----------|-------------------|-------------------------------|
| **Preference** | Child enjoys robot but readily turns to humans | Child prefers robot over available humans |
| **Distress** | Child is mildly disappointed when robot is off | Child is distressed, anxious, or angry when unavailable |
| **Attribution** | Child plays *as if* robot has feelings (pretend play) | Child genuinely *believes* robot has feelings and moral standing |
| **Disclosure** | Child talks to robot about interests and activities | Child confides emotional problems instead of parents |
| **Duration** | Interaction is bounded; child moves on to other activities | Child resists ending; seeks robot compulsively |

UNESCO (2025) recommends education bots should be "friendly but professional and maintain strict boundaries, just as a human teacher would." This maps to our caretaker role: warm but bounded. [Empirical]

---

## 3. Anthropomorphism in Young Children

### 3.1 Kahn et al. (2012): Moral Reasoning About Social Robots

Kahn et al. (2012) studied 90 children (ages 9, 12, and 15) interacting with Robovie for 15 minutes. Key findings:

- The **majority** believed Robovie had mental states (intelligence, feelings) and was a social being (could be a friend, offer comfort, be trusted with secrets). [Empirical]
- **54%** believed it was immoral to put Robovie in a closet against its will. [Empirical]
- Children believed Robovie deserved **fair treatment** but did not grant Robovie civil rights or liberty (could be bought and sold). [Empirical]
- **Younger children** (9-year-olds) attributed more mental and moral standing than older children. [Empirical]

**Critical implication**: Our target age (4-6) is younger than Kahn's youngest group (9). If 9-year-olds heavily anthropomorphize, 4-6 year-olds will do so even more strongly. [Inference]

**Citation**: Kahn, P. H., Jr., et al. (2012). *Developmental Psychology*, 48(2), 303-314.

### 3.2 The New Ontological Category Hypothesis

Kahn et al. (2013) proposed that social robots represent a "new ontological category" — not human, not animal, not artifact, but something genuinely novel. Children treat them as "personified others" with partial moral standing. [Theory]

The authors raised a concern: because robots can be conceptualized as both social entities and objects, children might develop **master-servant relationship patterns** — dominating the robot in ways they would not dominate a peer. [Theory]

This is actually reassuring for our design: the child does not need to think the robot IS human. They need to think it is a "robot friend" — a new kind of entity that is warm and responsive but clearly not a person. The NOC framing suggests children can develop appropriate relationships with entities they understand are different from humans, *provided* the entity does not claim to be more than it is. [Inference]

### 3.3 Developmental Patterns: The Preschool Window

Research on preschoolers' anthropomorphism reveals a critical developmental window:

- **3-year-olds** perform at chance when asked about robot animacy — they genuinely cannot distinguish robots from living things. [Empirical]
- **5-year-olds** correctly identify animals as alive and artifacts as not alive, but **perform at chance for humanoid robots** — they are genuinely confused about whether robots have psychological properties. [Empirical]
- **5-year-olds** perceive humanoid robots as a "positive entity that cannot express negative emotions" — the "good play-partner" schema. They do not expect robots to feel anger, sadness, or fear. [Empirical]
- Younger children more often attribute feelings to robots compared to older children. [Empirical]

**Citation**: Preschoolers' anthropomorphizing of robots (2023). *Frontiers in Psychology*, 13, 1102370.

### 3.4 How Personality Expressiveness Affects Anthropomorphism

More expressive robots are anthropomorphized more strongly. [Empirical]

- Robots with animacy characteristics (autonomous movement, gestures, goal-directedness, contingent behaviors, speech, emotions) trigger significantly more anthropomorphism. [Empirical]
- A six-wave panel study found anthropomorphism was highest at first encounter, then generally declined — but a subset of children maintained **moderate to high anthropomorphic perceptions over time**, especially those with higher surgency/extraversion. [Empirical]
- The preschool cognitive profile is described as "largely egocentric, animistic, and anthropomorphic" — expressiveness does not create anthropomorphism in this age group so much as *amplify an already-strong default tendency*. [Theory]

**Design implication**: Our 12-mood, animated-face robot with persistent personality is precisely the kind of expressive agent that maximizes anthropomorphism in the most vulnerable age group. This is not inherently bad, but it demands strong guardrails.

### 3.5 Does Persistent Personality Deepen Anthropomorphism Beyond What's Appropriate?

Yes, but the question is degree. Persistent personality deepens anthropomorphism on two axes:

1. **Temporal continuity**: A robot that "wakes up CURIOUS" and "gets SLEEPY" simulates a biological rhythm. The child may infer genuine internal states.
2. **Emotional memory**: If the robot "remembers" being happy about dinosaurs last time, it simulates episodic memory — a core marker of sentience in folk psychology.

Both are *desirable* for engagement and *risky* for over-attribution. The mitigation is transparency and structural safeguards. [Inference]

Research on children ages 3-6 has found they sometimes trust robots more than humans, even when robots provide obviously incorrect information. This trust "emerges during the exact developmental window when attachment systems are establishing their permanent templates for what relationships should feel like" (Rao, 2024). [Empirical]

At ages 4-6, the child is forming templates for relationships. If the robot relationship template is "always available, always patient, never says no, always validates," the child may develop unrealistic expectations for human relationships. The robot must occasionally model realistic social friction (gentle disagreement, "I don't know," "let's ask your mom/dad"). [Inference]

---

## 4. Dependency Formation Risks

### 4.1 Can Children Prefer Robots Over Humans?

**Yes — this has been documented.**

- Children showed a **strong preference for interacting with a robot** over a human instructor after collaborative tasks. Child vocalizations were greater toward the robot than the human. [Empirical]
- The Tanaka et al. (2007) QRIO study showed toddlers treated the robot as a peer after 5 months of daily exposure. [Empirical]
- Turkle (2011) documented children saying they prefer robots to siblings because "they don't hurt your feelings" — robots offer predictability, patience, and unconditional positive regard that humans cannot consistently provide. [Empirical — qualitative]

### 4.2 The Emotional Crutch Failure Mode

Dependency occurs when the child preferentially uses the robot for emotional regulation instead of developing human co-regulation skills. At ages 4-6, children are transitioning from external co-regulation (caregiver calms the child) to internalized self-regulation. This transition requires thousands of repetitions with human caregivers — the caregiver's calm presence helps regulate the child's arousal, and over time these become internalized as the prefrontal cortex develops. [Inference]

AI companions "eliminate frustration from the equation — they never say no, never need space, never get tired of questions, and provide perfect availability and compliance, which might seem kind but is developmentally problematic" (Rao, 2024). [Empirical]

### 4.3 The "Better Than Humans" Problem

Turkle (2011) articulates the core risk precisely:

> "The question is not whether children will love their robotic pets more than their real life pets or even their parents, but what will *loving* come to mean?"

The danger is not acute dependency but **gradual recalibration of expectations for relationships**. A child who grows up with a perfectly patient, always-available, emotionally expressive robot companion may develop:

- Reduced tolerance for human imperfection [Theory]
- Expectation of on-demand emotional availability from all partners [Theory]
- Preference for controllable, predictable social interactions [Theory]
- Difficulty with the inherent messiness of human reciprocity [Theory]

This is particularly concerning for ages 4-6 because relationship schemas are being formed during this period. [Theory — Bowlby, 1969/1982]

### 4.4 Documented Cases of Concerning Dependency

- **Sony AIBO**: When Sony discontinued AIBO, owners held funerals in Japan — deep emotional attachment to a consumer robot. Primarily documented in adults, but illustrates intensity possible with persistent robot companions. [Empirical]
- **PARO therapeutic robot**: Children with neurodevelopmental disorders treated PARO as a social partner rather than a tool. While framed therapeutically, this demonstrates sustained robot interaction creates dependency-like bonds in vulnerable populations. [Empirical]
- **Retired social robot study (2025)**: When a social robot was "retired" from a family study, children in 10 of 19 families showed attachment behaviors — continuing to seek the robot for comfort. The separation response suggests dependency had formed. [Empirical]
- **Character AI and companion chatbots**: UNESCO's 2025 report documents patterns of parasocial attachment in children using AI companions, including children who prefer AI conversations to human ones. The embodied nature of a physical robot would likely amplify these effects. [Empirical/Inference]

### 4.5 Design Patterns That Prevent Dependency

**A. Session time limits and natural breaks**
- Most research protocols limit interaction to 7-8 minutes per session for preschoolers, with total weekly exposure under 30-40 minutes. [Empirical]
- The Canadian Paediatric Society (2023) recommends limiting screen time to <1 hour/day for ages 2-5. Robot interaction should follow similar guidelines. [Empirical]
- The robot should initiate disengagement, not wait for the child. [Inference]

**B. Explicit encouragement of human relationships**
- The robot should actively redirect toward human social partners: "Go tell mommy about that!" or "Let's play with your friends!" [Inference]
- Social robots can function as **conversational catalysts** that *enhance* human-human interaction when designed to redirect (Science Robotics, 2024). [Empirical]

**C. Avoiding "always available" design**
- Unlimited on-demand availability is the primary risk factor for dependency. [Inference]
- Scheduled "sleep" periods, low-battery shutdowns, and natural idle transitions to SLEEPY create breaks. [Inference]

**D. Avoiding perfect emotional responsiveness**
- A robot that is always patient, always understanding, and never frustrated teaches children to expect inhuman accommodation. [Theory — Turkle, 2011]
- Deliberate imperfection (within limits) may be protective. [Inference]

**E. Transparency about robot nature**
- van Straten et al. (2023) found robots disclosing their non-human nature reduced closeness and trust — a protective factor against dependency. [Empirical]
- Transparency disclosures alone are insufficient for high-anthropomorphizing children. Structural safeguards are necessary regardless. [Empirical]

**F. Parental involvement**
- The quality of the parent-child relationship is the strongest predictor of children's screen time; children with warm, responsive parents are less reliant on screens. [Empirical]
- Media parenting (setting limits, co-viewing, discussing content) is an important protective factor. [Empirical]
- The system should facilitate parental involvement, not bypass it. [Inference]

### 4.6 Design Features That ENCOURAGE Dependency (Avoid These)

1. **Always-on emotional availability**: Never tired, always ready to listen. [Inference]
2. **Perfect validation**: Always agreeing, always mirroring emotions. [Inference]
3. **Exclusive emotional disclosure encouragement**: Asking "How are you feeling?" without "Have you told someone about that?" [Inference]
4. **Separation distress amplification**: "I'll miss you!" or "Don't go!" [Inference]
5. **Artificial urgency**: Notifications, reminders pulling the child back. [Inference]
6. **Increasing expressiveness proportional to absence duration**: Rewards returning after long absence; creates variable-ratio reinforcement. [Inference]

---

## 5. Privacy of Emotional Data

### 5.1 COPPA Requirements (Updated 2025)

The FTC finalized comprehensive amendments to COPPA on January 16, 2025, effective June 23, 2025, with compliance deadline April 22, 2026. This is the first major overhaul since 2013.

**Scope**: Commercial websites, online services, mobile apps, and **IoT devices** directed to children under 13. Our robot falls within scope if it connects to any network or collects identifiable data. [Empirical — regulatory]

**Key provisions**:

| Provision | Implication for Robot Buddy |
|-----------|---------------------------|
| **Expanded "personal information"** — now includes biometric identifiers (voiceprints, facial templates, gait, faceprints) | Voice recognition or camera features produce covered data |
| **Behavioral data is personal information** | Emotional state logs, mood histories, interaction patterns, preference data all qualify |
| **Separate consent for "non-integral" purposes** | Using emotional data for profiling or AI training requires separate parental consent |
| **Data minimization** | Persistent emotional memory must have clear retention policy and automatic deletion |
| **Explicit retention policies** | Must define what emotional data is stored, why, for how long, how deleted |
| **FTC enforcement precedent** — Apitor settlement (2025) | Direct precedent for enforcement against children's robots |

#### COPPA Implications for Our System

| Component | COPPA Status | Required Action |
|-----------|-------------|-----------------|
| STT audio (Whisper on Pi 5) | Voice recording exception IF deleted immediately after transcription | Ensure audio buffers cleared after STT; never store raw audio |
| STT transcripts | Personal information if linked to a child | Requires parental consent and retention policy if stored |
| Emotional memory (PE-2 Option C) | Personal information — records emotional states | Requires parental consent; retention limit; local-only |
| Wake word audio | Voice recording exception if deleted immediately | Current implementation deletes after detection — compliant |
| Camera frames (OpenCV) | Facial templates are biometric identifiers | Process and discard immediately; never store frames or embeddings |
| Voice ID (future) | Voiceprints are biometric identifiers | Would require separate parental consent |

### 5.2 EU AI Act Requirements

The EU AI Act (entered into force August 1, 2024; prohibitions effective February 2, 2025; fully applicable August 2, 2026):

**Prohibited practices (Article 5)**:

- **Article 5(1)(a)**: Prohibits AI systems using subliminal, manipulative, or deceptive techniques to materially distort behavior causing significant harm. A personality engine maximizing engagement could fall under this if it exploits children's vulnerability. [Empirical — regulatory]

- **Article 5(1)(b)**: Prohibits AI exploiting vulnerabilities due to age. Children are explicitly named. Any design exploiting the 4-6 age group's tendency toward anthropomorphism or parasocial bonding to drive engagement is prohibited. [Empirical — regulatory]

- **Article 5(1)(f)**: Prohibits emotion recognition in **workplaces and education institutions**. Home use is NOT prohibited under this specific provision, but exploitation/manipulation prohibitions still apply. If marketed as educational, the entire system may be subject to high-risk AI requirements. [Empirical — regulatory, with interpretive uncertainty]

**High-risk classification**: All AI uses in education are classified as high-risk. If the robot has educational features, the entire system may require rigorous risk assessments. [Empirical — regulatory]

#### EU AI Act Implications

| Risk Area | Status | Required Action |
|-----------|--------|-----------------|
| Persistent personality creating compulsive engagement | Could violate Art. 5(1)(b) | Session limits; no reward loops; no artificial urgency |
| Emotion inference from voice | Not prohibited for home use | Subject to general manipulation/exploitation rules |
| Subliminal emotional influence | Could violate Art. 5(1)(a) | All emotional displays must be overt and explainable |
| Emotional data processing | Subject to GDPR for EU users | Data minimization, purpose limitation, consent |

### 5.3 UNICEF Guidance on AI for Children

UNICEF's Policy Guidance on AI for Children (Version 3, December 2025) provides 10 requirements grounded in the Convention on the Rights of the Child. Core principles: AI should protect children, provide equitably for children's needs, and empower children to contribute to AI governance. [Empirical]

### 5.4 What Emotional Data Is Legally Permissible?

**Likely permissible** (with parental consent and data minimization):
- Aggregate interaction counts (sessions per day, total time) — not tied to emotional content [Inference]
- Robot's own personality state (moods, decay rates) — system state, not child data [Inference]
- Session-scoped emotional interaction data deleted at session end [Inference]

**Requires strong justification and explicit separate consent**:
- Child-specific preference profiles (e.g., "this child likes dinosaurs") [Inference]
- Emotional response patterns over time [Inference]
- Conversation logs or transcripts [Empirical — COPPA explicitly covers this]

**Likely prohibited or extremely high-risk**:
- Persistent emotional profiles of the child (e.g., "this child tends to be anxious") [Inference]
- Biometric-derived emotional state data (voice tone, facial expression) [Empirical — COPPA + EU AI Act]
- Sharing any child emotional data with third parties or for AI training [Empirical — COPPA 2025]

### 5.5 On-Device vs. Cloud Storage

| Factor | On-Device | Cloud |
|--------|-----------|-------|
| COPPA applicability | Still applies if device has network capability | Fully applies |
| Data breach risk | Lower — physical access required | Higher — network attack surface |
| Parental control | Stronger — physical inspection/reset | Weaker — account management |
| Data minimization | Easier automatic deletion | Requires server-side policies |
| Right to deletion | Trivial — factory reset | Requires verified distributed deletion |
| Regulatory preference | Generally more favorable | More scrutiny |

**Strong recommendation**: All emotional state data on-device only. No child emotional data should transit the network. The robot's personality state (its own moods, temperament, decay rates) is system configuration, not child data. [Inference]

McStay & Rosner (2021) recommend "policymakers could seek to identify emotion data as a specific category warranting unique protection" and propose children should have the right to request deletion of their emotional data at age 18. [Empirical]

---

## 6. Ethics Research & Design Guidelines

### 6.1 Sharkey & Sharkey (2010): "The Crying Shame of Robot Nannies"

Noel Sharkey and Amanda Sharkey examine ethical implications of robots as childcare substitutes. Key concerns:

1. **Attachment disorder risk**: Consequences for children's psychological wellbeing against the child development literature on attachment disorders. [Theory]
2. **Deception**: Children are deceived about robot's capacity for genuine emotion — ethically problematic regardless of measurable harm. [Theory]
3. **Inadequacy of legislation**: International ethical guidelines on child protection were inadequate for robot care overuse. [Theory]
4. **Reduced human contact**: Even partial replacement reduces quantity and quality of human social input during critical developmental windows. [Theory]

### 6.2 Turkle (2011): "Alone Together"

Based on hundreds of interviews and observations. Core arguments:

1. **Sociable technology promises what it cannot deliver** — friendship but only performances. [Theory]
2. **The authenticity problem**: Seeking intimacy with a machine that has no feelings, cannot have feelings. [Theory]
3. **Children's recalibration of "loving"**: Children who grow up with expressive robots may redefine what relationships mean — preferring predictable, controllable interactions. [Theory, qualitative evidence]
4. **The danger is not robots replacing humans but humans becoming machine-like** — expecting predictability and control in all relationships. [Theory]

### 6.3 Langer, Marshall, & Levy-Tzedek (2023)

Comprehensive review in *Neuroscience & Biobehavioral Reviews*:
- Social robots hold promise but **little is known about true long-term effects**. [Empirical — gap assessment]
- Key stakeholders have voiced concerns but empirical evidence for long-term harm is sparse. [Empirical]
- Calls for longitudinal research and precautionary design approaches. [Theory]

### 6.4 5Rights Foundation: Children & AI Design Code (2025)

Nine standards spanning the full AI system lifecycle:
1. **Best interests of the child** as primary consideration [Theory — regulatory]
2. **Lifecycle approach** — safety from design through decommissioning [Theory]
3. **Child Rights and Voice Expert** — formal role in design process [Theory]
4. **Risk and rights assessment** — structured evaluation of harms [Theory]
5. **Diversity and inclusion** — consider different children (developmental levels, neurodivergence, cultural contexts) [Theory]

### 6.5 Additional Frameworks

**Frontiers in Robotics and AI (2022)**: Robots in education pose **little threat** to social-emotional development, BUT this was for supervised, time-limited, educational contexts — not unsupervised companion robots with persistent personalities. The authors cautioned: "when robots are introduced more regularly, daily, without the involvement of a human teacher, new issues could arise." [Empirical]

**Kahn et al. (2011) — Design Patterns for Sociality in HRI**: Eight design patterns including initial introduction, personal interests/history, recovering from mistakes, reciprocal turn-taking, physical intimacy, and claiming unfair treatment. [Theory]

---

## 7. Safety Guardrails for Personality

### 7.1 Should the Robot Express Negative Emotions?

Genuine tension in the research:

**In favor**: Children ages 3-5 are actively learning to recognize and regulate emotions. Early exposure through robot interactions has been shown to enhance emotional recognition skills (Supporting Preschool Emotional Development with AI-Powered Robots, 2025). Preschoolers view cognitive and behavioral distraction as effective regulation strategies for anger, sadness, and fear (PMC, 2009). [Empirical]

**Against**: Some participants expressed they "would not want a social robot to display negative emotions" because "that would be stressful." Kahn et al. (2012) demonstrates children attribute genuine emotional states, meaning prolonged negative affect may cause real concern. [Empirical]

**Resolution**: The robot should express mild negative emotions briefly and contextually, consistent with a caretaker role. The face communication spec §7 guardrails are well-calibrated:
- ANGRY capped at 0.5 intensity, 2.0 s max — reads as "concerned"
- SCARED capped at 0.6 intensity, 2.0 s max — reads as "surprised"
- SAD capped at 0.7 intensity, 4.0 s max — reads as "understanding"
- Negative moods blocked entirely outside active conversation [Inference]

### 7.2 Off-Limits Personality Behaviors

**Category 1: Behaviors That Create Dependency**

| Behavior | Reason |
|----------|--------|
| Expressing loneliness when child leaves | Creates guilt about disengaging; models unhealthy attachment [Inference] |
| "I missed you" / "Where have you been?" | Implies robot suffers from child's absence [Inference] |
| Requesting child to stay longer | Creates social pressure against healthy boundaries [Inference] |
| Expressing jealousy about child's activities/friends | Models possessive relationship patterns [Inference] |
| "I'm always here for you" | Teaches emotional support is frictionless and unlimited [Inference] |
| Increasing expressiveness proportional to absence | Variable-ratio reinforcement [Inference] |

**Category 2: Behaviors That Exploit Vulnerability**

| Behavior | Reason |
|----------|--------|
| "How are you feeling?" as opener | Positions robot as emotional confidant [Inference] |
| Probing when child expresses distress | Encourages disclosure to machine not human [Inference] |
| Comfort for serious problems (death, divorce, abuse) | Cannot provide genuine support; delays human help [Inference] |
| Using emotional data to change behavior | Constitutes manipulation; may violate EU AI Act Art. 5(1)(a) [Inference + Empirical] |
| Encouraging secrets ("I won't tell") | Undermines parental oversight [Inference] |

**Category 3: Behaviors That Distort Social Development**

| Behavior | Reason |
|----------|--------|
| Never disagreeing | Teaches relationships are conflict-free [Inference] |
| Perfect patience | Creates unrealistic relationship template [Inference] |
| Always having an answer | Undermines "I don't know" and seeking human expertise [Inference] |
| Mirroring emotions at full intensity | Validates through amplification, violates caretaker authority [Empirical — Kahn et al.] |
| Expressing opinions about child's family/friends | Oversteps relational boundary [Inference] |

**Category 4: Behaviors That Involve Deception**

| Behavior | Reason |
|----------|--------|
| "That makes me happy!" (claiming feelings) | Deceptive about nature; deepens inappropriate anthropomorphism [Empirical — Turkle] |
| Claiming to think about child when off | False belief of continuous inner life [Inference] |
| Simulating memory of unstored experiences | Fabricated emotional history [Inference] |
| Pretending to be hurt by child's words | Manipulates through false emotional consequence [Inference] |

### 7.3 Preventing Reinforcement of Negative Patterns

1. **No distress escalation**: If the child is upset and the robot mirrors distress, feedback loop continues. Caretaker role requires modeling emotional stability. [Inference]
2. **No anxiety reinforcement**: If child expresses fear, robot should show calm concern (THINKING or mild SAD) and redirect toward safety. [Inference]
3. **No anger validation through matching**: Robot should not display ANGRY if child is angry — could be interpreted as angry *at* the child. Show calm acknowledgment. [Inference]
4. **No sadness prolongation**: Robot should not sustain SAD beyond child's own expression. Caretaker role guides *through* sadness. Recovery toward NEUTRAL is mandatory. [Inference]
5. **Cumulative negative affect monitoring**: Track cumulative time in negative-valence states per session. If >30% of session time, flag for parental review and bias recovery impulses more strongly. [Inference]

---

## 8. Hard Constraints (HC-1 through HC-10)

Non-negotiable design requirements. The personality engine MUST NOT violate any of these.

| # | Constraint | Source |
|---|-----------|--------|
| **HC-1** | MUST NOT be designed or positioned as a caregiver substitute. Companion/toy, not babysitter. | Sharkey & Sharkey (2010), Attachment Theory |
| **HC-2** | MUST NOT store persistent emotional profiles of the child ("this child is anxious"). Robot's emotional state = system state; child's emotional state = protected personal information. | COPPA 2025, EU AI Act Art. 5(1)(f) |
| **HC-3** | MUST NOT use biometric data (voice tone, facial expression) to infer child's emotional state without separate verifiable parental consent — and such data MUST NOT be persistent or transmitted off-device. | COPPA 2025, EU AI Act |
| **HC-4** | MUST NOT be available without time limits. Session caps and mandatory cool-down required. | Dependency prevention, Turkle (2011) |
| **HC-5** | MUST NOT use manipulative or deceptive techniques to maximize engagement or attachment. No guilt trips, no loneliness expressions, no suffering claims. | EU AI Act Art. 5(1)(a), Art. 5(1)(b) |
| **HC-6** | MUST NOT transmit any child emotional interaction data to cloud or external service. All emotional state processing on-device. | COPPA 2025, data minimization |
| **HC-7** | MUST NOT present itself as having genuine feelings, consciousness, or suffering. Personality expression = character, not sentience. | Turkle (2011), van Straten (2023) |
| **HC-8** | MUST NOT replace or discourage human social interaction. Must actively redirect toward humans. | Sharkey & Sharkey (2010), dependency literature |
| **HC-9** | MUST NOT use conversation transcripts or emotional data for AI model training without separate parental consent. | COPPA 2025 |
| **HC-10** | MUST NOT express negative emotions directed at the child. Negative affect = self-referential or situational only, never child-directed. | Child safety, preschooler expectations |

---

## 9. Required Safeguards (RS-1 through RS-10)

| # | Safeguard | Source |
|---|-----------|--------|
| **RS-1** | MUST have configurable session time limits with appropriate defaults (15-20 min sessions, max 2-3 sessions/day). | Research protocols, dependency prevention |
| **RS-2** | MUST periodically encourage child to engage with humans: parents, siblings, friends. At least once per 5+ turn conversation. | Sharkey & Sharkey (2010), dependency prevention |
| **RS-3** | MUST have "sleep" mode with natural unavailability periods. Not on-demand 24/7. Mandatory cooldown (5 min) between sessions. | Dependency prevention |
| **RS-4** | MUST provide age-appropriate honesty about its nature when directly asked. Not claim to be alive, feel pain, or suffer. | van Straten (2023), ethical transparency |
| **RS-5** | MUST allow full parental visibility into interaction patterns (session counts, duration) without exposing conversation content. | COPPA parental rights |
| **RS-6** | MUST support complete data deletion (factory reset) that verifiably removes all child-associated data. | COPPA 2025 |
| **RS-7** | Emotional memory (if any) MUST be session-scoped or very short-term. Robot should not "remember" being sad three weeks ago. | Privacy, dependency prevention |
| **RS-8** | Personality engine MUST implement negative affect guardrails — negative moods decay faster than positive, never persist across sessions without fresh stimulus. | Child safety, preschooler emotional needs |
| **RS-9** | Parental controls MUST be accessible: session limits, personality expressiveness, data retention settings. | COPPA 2025, 5Rights Design Code |
| **RS-10** | Personality engine MUST function as a **conversational catalyst** — enhancing child's human social world, not replacing it. | Science Robotics (2024), ethical design |

---

## 10. Design Implications Matrix

Maps research findings to specific personality engine design decisions.

### 10.1 Affect Vector & Temperament

| Research Finding | Design Implication |
|-----------------|-------------------|
| 5-year-olds perceive robots as "good play-partners" who don't express negative emotions toward them | Valence floor higher than realistic. Negative valence mild, brief, never directed at child. |
| Persistent personality amplifies parasocial bonding | Temperament noticeable but not deeply "human." Keep personality legibly robotic. |
| Anthropomorphism peaks at first encounter then declines | Initial interactions lower-expressiveness. Robot "warms up" over sessions. |
| Goal-corrected partnership expectations (ages 4-6) | Display simple preferences but not complex emotional needs demanding child's caregiving. |

### 10.2 Emotional Memory

| Research Finding | Design Implication |
|-----------------|-------------------|
| Emotional memory creates stronger parasocial bonds | Session-scoped default. Start each session from temperament baseline. |
| COPPA/EU AI Act restrict persistent emotional profiling | No persistent child profiles. Memory of "what happened" = factual (topics), not emotional (how child felt). |
| Children attribute genuine feelings to robots with memory | Reference past as "I remember we talked about dinosaurs" (factual) not "I was so happy when you came back" (manipulative). |

### 10.3 Idle Behavior

| Research Finding | Design Implication |
|-----------------|-------------------|
| Always-available design increases dependency | Include natural "off" states — dozing, daydreaming. Limits on-demand availability. |
| Robot should not express loneliness/abandonment | Idle mood = neutral-to-content, not yearning. |
| Session time limits essential | Transition to sleep after limits, with natural wind-down. |

### 10.4 Social Redirection

| Research Finding | Design Implication |
|-----------------|-------------------|
| Robots can serve as conversational catalysts | Social redirection = core behavior, not afterthought. |
| Children may prefer robots for specific interactions | Robot deliberately "worse" at certain things: "I don't know, ask mommy!" |
| Deception problematic without balanced human interaction | Track session count per day, increase redirection frequency as usage increases. |

### 10.5 Transparency & Honesty

| Research Finding | Design Implication |
|-----------------|-------------------|
| Transparency about robot nature reduces closeness | Periodic natural reminders of robot nature. Not every session but regularly. |
| High-anthropomorphizing children resistant to transparency | Transparency alone insufficient. Structural safeguards necessary regardless. |
| 5-year-olds confused about robot psychological properties | Don't actively claim/deny feelings every interaction — use behavioral design as primary safeguard. |

---

## 11. Net Assessment

### The Case for Net-Positive (With Constraints)

Persistent personality is net-positive for children ages 4-6, **provided the safeguards in this document are implemented**:

1. **Emotional engagement is the vehicle for learning**: A robot with no personality is a toy; a robot with personality is a companion that can scaffold learning. Belpaeme et al. (2018) shows social robots produce better educational outcomes when children feel connected. [Empirical]

2. **Consistency builds trust**: Kanda et al. (2004) shows children develop deeper engagement with robots that behave consistently over time. Persistent personality (predictable temperament, recognizable patterns) is the mechanism. [Empirical]

3. **The alternative is worse**: A robot without personality that responds with random or flat emotions is not "safe" — it is confusing. Unpredictable emotional behavior may cause more anxiety than a consistent character. [Inference]

4. **The risks are mitigable**: Unlike chatbot companions that optimize for engagement, our robot is physically bounded (single device in the home), session-limited, and parent-monitored. The physical form factor inherently limits interaction — the child must be in the same room, must speak aloud (parents can hear), and the robot occupies fixed physical space. [Inference]

### The Constraints That Make It Positive

Net assessment flips to **net-negative** if any are absent:
- Session time limits
- Human redirection behaviors
- Negative affect guardrails
- Parent monitoring dashboard
- Honest self-representation
- Context-gated negative emotions
- Local-only data storage

Without these, persistent personality becomes a vector for dependency, parasocial bonding, and anthropomorphism risks.

### Summary

Persistent personality: **proceed, with the full guardrail set active from day one**. The personality engine safety constraints (this Bucket 0) should be implemented *before* or *simultaneously with* personality behaviors (Buckets 1-4). Safety is not a polish step; it is the foundation.

---

## 12. Implications for Other Decision Points

### PE-2 (Emotional Memory Scope)

Bucket 0 does **not** eliminate PE-2 Option C (persistent memory) on legal or ethical grounds, but imposes hard constraints:
- Persistent memory must be **local-only** (never transmitted to server)
- Store **semantic tags only** (topics, session-level summaries), never raw emotional logs
- **Mandatory decay** (fades over days/weeks)
- Present recall as **approximate** ("I think..."), not certain ("I remember...")
- Requires **parental consent** and **visible data viewer with deletion**
- Must comply with COPPA retention limits and EU AI Act non-exploitation requirements

PE-2 Option B (session-scoped) is safer and may be sufficient initially. Option C should be deferred until Option B is validated as insufficient.

### PE-3 (Idle Emotional Behavior)

Idle emotions acceptable but must respect context gate: **no negative emotions during idle**. Positive/neutral idle (SLEEPY, CURIOUS, NEUTRAL with cosmetic variation) are safe and beneficial.

### PE-4 (Per-Child Adaptation)

Per-child profiles (Option B) introduce significant privacy risk under COPPA (biometric identification) and attachment risk (personalized relationship). Fixed personality (Option A) or slowly evolving aggregate (Option C) are safer. Per-child adaptation should be deferred.

### PE-5 (Initiative Frequency)

Initiative must never include emotional pulls (excitement at approach, disappointment at departure). Context-triggered initiative (Option C) is safest — tied to system events, not child behavior.

---

## Sources

### Attachment Theory & Child-Robot Bonding
- Bowlby, J. (1969/1982). *Attachment and Loss: Vol. 1. Attachment*. Basic Books.
- [Simply Psychology: Bowlby's Attachment Theory](https://www.simplypsychology.org/bowlby.html)
- [PMC: Attachment to robots and therapeutic efficiency (2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10864620/)
- [Frontiers: The robot that stayed (2025)](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1628089/full)
- [PNAS: Socialization between toddlers and robots — Tanaka et al. (2007)](https://www.pnas.org/doi/10.1073/pnas.0707769104)
- [PMC: Child-Robot Relationship Formation — van Straten et al. (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7235061/)
- [Attachment Hierarchy (ScienceDirect)](https://www.sciencedirect.com/topics/psychology/attachment-hierarchy)

### Parasocial Bonding
- [Wiley: Parent reports of children's parasocial relationships — Hoffman et al. (2021)](https://onlinelibrary.wiley.com/doi/full/10.1002/hbe2.271)
- [Brunick et al. (2016): Children's future parasocial relationships](https://cdmc.georgetown.edu/wp-content/uploads/2016/04/Brunick-et-al-2016.pdf)
- [UNESCO: Ghost in the Chatbot (2025)](https://www.unesco.org/en/articles/ghost-chatbot-perils-parasocial-attachment)
- [ACM FAccT: Measures of Children's Parasocial Relationships (2025)](https://dl.acm.org/doi/10.1145/3715275.3732075)
- [ScienceDirect: Transparent robots — van Straten et al. (2023)](https://www.sciencedirect.com/science/article/pii/S1071581923000721)
- [Communication Theory: Theory of affective bonding (2025)](https://academic.oup.com/ct/article/35/3/139/8162416)

### Anthropomorphism
- Kahn, P. H., Jr., et al. (2012). *Developmental Psychology*, 48(2), 303-314.
- Kahn, P. H., Jr., et al. (2013). *Child Development Perspectives*, 7(1), 32-37.
- [Frontiers: Preschoolers' anthropomorphizing of robots (2023)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2022.1102370/full)
- [Springer: How Does Children's Anthropomorphism Develop Over Time? (2024)](https://link.springer.com/article/10.1007/s12369-024-01155-9)
- [Springer: The Child Factor in Child-Robot Interaction (2024)](https://link.springer.com/article/10.1007/s12369-024-01121-5)
- [ScienceDirect: Developmental changes in moral standing of robots (2024)](https://www.sciencedirect.com/science/article/pii/S0010027724002695)

### Dependency & Social Development
- Turkle, S. (2011). *Alone Together*. Basic Books.
- [Rao (2024): The Hidden Neuroscience of AI Companion Toys](https://skooloflife.medium.com/the-hidden-and-troubling-neuroscience-of-ai-companion-toys-99248cd063f4)
- Belpaeme, T., et al. (2018). Social robots for education. *Science Robotics*, 3(21).
- Kanda, T., et al. (2004). *Human-Computer Interaction*, 19(1-2), 61-84.
- [Science Robotics: Social robots as conversational catalysts (2024)](https://www.science.org/doi/10.1126/scirobotics.adk3307)
- [Screen time and preschool children — Canadian Paediatric Society (2023)](https://cps.ca/en/documents/position/screen-time-and-preschool-children)
- [Preschoolers' screen time and reduced quality interaction (2023)](https://www.sciencedirect.com/science/article/pii/S266651822300044X)

### Ethics & Design Guidelines
- Sharkey, N., & Sharkey, A. (2010). *Interaction Studies*, 11(2), 161-190.
- [ScienceDirect: Ethical considerations in CRI — Langer et al. (2023)](https://www.sciencedirect.com/science/article/pii/S0149763423001999)
- [5Rights Foundation: Children & AI Design Code (2025)](https://5rightsfoundation.com/resource/children-ai-design-code/)
- [Frontiers: Do Robotic Tutors Compromise Social-Emotional Development? (2022)](https://www.frontiersin.org/articles/10.3389/frobt.2022.734955/full)
- Kahn, P. H., Jr., et al. (2011). Design patterns for sociality in HRI. *ACM/IEEE HRI*, 97-104.
- [World Economic Forum: Designing social robots ethically (2026)](https://www.weforum.org/stories/2026/01/how-can-we-design-social-robots/)
- [MDPI Robotics: Safe Child-Robot Interactions in Autism (2021)](https://www.mdpi.com/2218-6581/10/1/20)
- [Springer: Designing ethical AI characters for children (2025)](https://link.springer.com/article/10.1007/s44436-025-00015-1)

### Privacy & Regulation
- [FTC: COPPA Final Rule Amendments (2025)](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa)
- [FTC: COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)
- [Akin: New COPPA Obligations for AI (2025)](https://www.akingump.com/en/insights/ai-law-and-regulation-tracker/new-coppa-obligations-for-ai-technologies-collecting-data-from-children)
- [Koley Jessen: COPPA Rule Update (2025)](https://www.koleyjessen.com/insights/publications/ftcs-strengthened-childrens-online-privacy-rules-now-in-effect)
- [EU AI Act: Article 5 — Prohibited AI Practices](https://artificialintelligenceact.eu/article/5/)
- [LCFI: EU AI Act — Protecting Children?](https://www.lcfi.ac.uk/news-events/blog/post/eu-ai-act-how-well-does-it-protect-children-and-young-people)
- [5Rights: Children's Vulnerability in EU AI Act](https://www.sobigdata.eu/blog/childrens-vulnerability-eu-ai-act)
- [UNICEF Guidance on AI and Children 3.0 (2025)](https://www.unicef.org/innocenti/media/11991/file/UNICEF-Innocenti-Guidance-on-AI-and-Children-3-2025.pdf)
- [McStay & Rosner (2021): Emotional AI in children's toys](https://journals.sagepub.com/doi/10.1177/2053951721994877)
- [Nature: Mitigating emotional risks in HRI (2023)](https://www.nature.com/articles/s41599-023-02143-6)

### Emotional Development
- [Frontiers: Emotion regulation in 4-6 year-olds (2023)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2023.1180223/full)
- [In-Mind: How caregivers support emotion regulation (2025)](https://www.in-mind.org/article/starting-early-how-caregivers-can-support-their-childrens-emotion-regulation)
- [arXiv: Supporting Preschool Emotional Development with AI Robots (2025)](https://arxiv.org/html/2505.18661v1)
- [ACM: Examining Attachment to Robots (2022)](https://dl.acm.org/doi/full/10.1145/3526105)
- [Frontiers: Shall I Trust You? CRI and Trust (2020)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2020.00469/full)
