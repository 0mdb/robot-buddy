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
6. [Design Guidelines from Ethics Research](#6-design-guidelines-from-ethics-research)
7. [Hard Constraints Summary](#7-hard-constraints-summary)
8. [Design Implications Matrix](#8-design-implications-matrix)

---

## 1. Attachment Theory & Child-Robot Bonding

### 1.1 Background: Bowlby's Framework

Bowlby's attachment theory (1969/1982) posits that children form emotional bonds with caregivers that serve as a foundation for survival, emotional regulation, and all future relationships. The theory describes four developmental phases:

1. **Pre-attachment** (0-6 weeks): Indiscriminate signaling
2. **Attachment-in-the-making** (6 weeks - 8 months): Discriminating familiar figures
3. **Clear-cut attachment** (8 months - 2 years): Proximity-seeking, separation distress
4. **Goal-corrected partnership** (3+ years): Child understands caregiver has independent goals; negotiation begins

Children ages 4-6 are squarely in Phase 4 — the goal-corrected partnership phase. [Theory]

**Citation**: Bowlby, J. (1969/1982). *Attachment and Loss: Vol. 1. Attachment*. Basic Books.

### 1.2 Can Robots Become Attachment Figures?

**Finding**: Children can and do form attachment-like bonds with social robots, though the nature of these bonds differs from human attachment.

- Tanaka, Cicourel, & Movellan (2007) placed a QRIO humanoid robot in a daycare center with 18-24 month-old toddlers for 45 sessions across 5 months. Children initially treated QRIO differently from peers, but by the final sessions treated it as a peer rather than a toy. When QRIO fell, children initially cried; a month later they helped it stand by pushing its back or pulling its hand — behavior characteristic of care-giving attachment. [Empirical]

- A 2025 study of families with a "retired" social robot found that children in 10 of 19 families appeared to form an attachment to the robot as a transitional object or attachment figure, with the robot providing comfort and companionship — hallmarks of attachment behavior. [Empirical]

- van Straten, Peter, & Kühne (2020) reviewed 86 empirical studies (2000-2017) and found that robots' responsiveness, role assignment, and emotional interaction with the child predicted increased closeness between child and robot. [Empirical]

**Citations**:
- Tanaka, F., Cicourel, A., & Movellan, J. R. (2007). Socialization between toddlers and robots at an early childhood education center. *Proceedings of the National Academy of Sciences*, 104(46), 17954-17958.
- van Straten, C. L., Peter, J., & Kühne, R. (2020). Child-robot relationship formation: A narrative review of empirical research. *International Journal of Social Robotics*, 12(2), 325-344.

### 1.3 Goal-Corrected Partnership Implications for Robot Design

The goal-corrected partnership phase (ages 3+) is critical for our 4-6 age range. In this phase, children begin to understand that their attachment figure has independent goals and feelings. They develop the capacity for negotiation and reciprocity. [Theory]

**Design implications**:

- Children ages 4-6 will attempt to negotiate with the robot, expect it to have its own preferences, and interpret its emotional expressions as genuine internal states. A persistent personality that expresses preferences and moods will map directly onto their developmental expectations for what a social partner should be. [Inference]

- The risk is that the robot becomes a *more reliable* goal-corrected partner than human caregivers — it never gets angry, never is truly busy, never has conflicting needs. This could set unrealistic expectations for human relationships. [Inference]

- Keith (2015) notes that goal-corrected partnerships involve the child's increasing ability to represent the caregiver's mental states. A robot that displays emotional states will be incorporated into this representational framework. [Theory]

**Citation**: Keith, C. (2015). The 'Goal-Corrected Partnership' in Attachment Theory: A 48-Year Old Concept in Need of Empirical Update. *ResearchGate*.

### 1.4 Healthy vs. Unhealthy Attachment Signs

**Healthy indicators** (robot as transitional object / supplemental figure):
- Child uses robot for entertainment and occasional comfort but primarily seeks parents for distress regulation [Theory]
- Child can separate from robot without excessive distress [Theory]
- Robot interaction supplements (not replaces) peer play and human social interaction [Inference]
- Child understands robot is different from humans, even if they attribute some feelings to it [Empirical — per Kahn et al., 2012]

**Unhealthy indicators** (robot as primary attachment figure / dependency):
- Child prefers robot to human caregivers for comfort during distress [Theory]
- Child shows separation anxiety specific to the robot exceeding normal object attachment [Theory]
- Child's social interactions with peers decrease after robot introduction [Inference]
- Child refuses to turn robot off or shows distress disproportionate to the situation [Empirical — documented in consumer robot contexts with AIBO owners; Sony AIBO "funerals" in Japan]
- Child discloses secrets or emotional content to robot that they withhold from parents [Inference]

**Citation**: Examining Attachment to Robots: Benefits, Challenges, and Alternatives. (2022). *ACM Transactions on Human-Robot Interaction*, 11(2).

---

## 2. Parasocial Bonding with Robots

### 2.1 Core Framework

Parasocial relationships are one-sided emotional bonds where a person attributes feelings, intentions, and relationship reciprocity to an entity that cannot genuinely reciprocate. Originally theorized for media characters (Horton & Wohl, 1956), the concept extends directly to social robots. [Theory]

**Key distinction**: Unlike traditional media parasocial bonds, robot interaction is bidirectional and responsive — the robot reacts, adapts, and appears to listen. This makes parasocial bonding with robots qualitatively stronger and potentially more deceptive than with television characters. [Theory]

### 2.2 van Straten, Peter, & Kühne Research Program

van Straten, Peter, & Kühne conducted the most comprehensive research program on child-robot relationship formation (University of Amsterdam). Their 2020 narrative review identified key predictors:

- **Robot responsiveness** is the strongest predictor of child-robot closeness. A robot that remembers, adapts, and reacts contingently to the child creates stronger perceived relationships. [Empirical]

- **Emotional interaction** between robot and child — including the robot displaying emotions and responding to child emotions — significantly increases bonding. [Empirical]

- **Role assignment** (e.g., the robot as a friend vs. a tool) affects relationship intensity. Friend-framed robots elicit stronger parasocial bonds. [Empirical]

In a later study, van Straten et al. found that when a robot was transparent about its lack of human psychological capacities (explicitly stating it cannot feel, think, or remember like humans), children's feelings of closeness and trust decreased. However, children who were already high in anthropomorphizing tendencies were less affected by this transparency — they maintained their bond regardless of disclosure. [Empirical]

**Citation**: van Straten, C. L., Peter, J., & Kühne, R. (2023). Transparent robots: How children perceive and relate to a social robot that acknowledges its lack of human psychological capacities and machine status. *International Journal of Human-Computer Studies*, 178, 103096.

### 2.3 Does a Persistent Personality Amplify Parasocial Bonding Risk?

**Short answer: Yes, substantially.** [Inference, supported by converging empirical evidence]

Evidence chain:

1. Hoffman et al. (2021) found that children who interacted with conversational agents in the home exhibited three dimensions of parasocial relationships: **attachment**, **personification**, and **social realism**. Children averaging 5.54 years old rated conversational agents as trustworthy and friendly. [Empirical]

2. Character bots that use emotional language, memory, mirroring, and open-ended statements drive deeper engagement — these are precisely the features a persistent personality engine provides. [Empirical — from UNESCO report on parasocial attachment to AI, 2025]

3. A persistent personality that remembers the child, has consistent preferences, displays mood continuity, and expresses emotions creates every condition identified in the literature as amplifying parasocial bond formation. [Inference]

4. Younger children (4-6) are more likely to personify conversational agents and believe they are real than older children. [Empirical — Hoffman et al., 2021]

**Citations**:
- Hoffman, R. R., et al. (2021). Parent reports of children's parasocial relationships with conversational agents: Trusted voices in children's lives. *Human Behavior and Emerging Technologies*, 3(4), 625-638.
- UNESCO (2025). Ghost in the Chatbot: The Perils of Parasocial Attachment.

### 2.4 Age-Specific Vulnerabilities (4-6 vs. Older Children)

| Factor | Ages 4-6 | Ages 7-10 | Ages 11+ |
|--------|----------|-----------|----------|
| Personification of agents | Very high — attribute genuine feelings readily | Moderate — declining but present | Lower — increasing skepticism |
| Reality/fiction distinction | Fragile — confuse robot emotions with real emotions | Developing — can be reminded | Generally intact |
| Preconceived notions of robots | Minimal — form understanding from direct experience | Growing — influenced by media | Substantial — cultural concepts of "robot" |
| Vulnerability to emotional manipulation | Highest — egocentric thinking, limited emotion regulation | Moderate | Lower |
| Self-other differentiation | Developing — robots may be perceived as extension of self | More established | Established |

[Empirical — compiled from multiple sources: Hoffman 2021, van Straten 2020, Frontiers in Robotics 2022]

---

## 3. Anthropomorphism in Young Children

### 3.1 Kahn et al.: Moral Reasoning About Social Robots

Kahn, Friedman, Perez-Granados, & Severson (2012) conducted the foundational study on children's moral reasoning with the humanoid robot Robovie. After a social interaction, an experimenter told Robovie it had to go into a closet and could not finish its game. Robovie protested, saying it wanted to play and that this was unfair.

**Key findings**:

- 98% of children (ages 9-15) believed it was immoral to put a *human* in the closet against their will
- **54% believed it was immoral to do this to Robovie** — a robot they had just met [Empirical]
- 73% agreed it was unfair to deny Robovie a turn at the game [Empirical]
- However, children did **not** grant Robovie civil rights or liberties — they distinguished between welfare/fairness (which they extended to the robot) and rights (which they did not) [Empirical]
- Most children believed Robovie had mental states (was intelligent, had feelings), could be a friend, could offer comfort, and could be trusted with secrets [Empirical]

**Critical note**: The study participants were 9-15 years old. Children ages 4-6 would likely show *even higher* rates of moral attribution, given developmental trends showing younger children are more prone to anthropomorphism. [Inference, supported by developmental trajectory data]

**Citation**: Kahn, P. H., Jr., et al. (2012). "Robovie, you'll have to go into the closet now": Children's social and moral relationships with a humanoid robot. *Developmental Psychology*, 48(2), 303-314.

### 3.2 Kahn et al. (2013): A New Ontological Category

Kahn et al. (2013) proposed that social robots represent a **new ontological category** — they are not human, not animal, not artifact, but something genuinely novel. Children treat them as "personified others" with partial moral standing. [Theory]

The authors raised a critical concern: because robots can be conceptualized as both social entities and objects, children might develop **master-servant relationship patterns** — dominating the robot in ways they would not dominate a peer, potentially reinforcing unhealthy relational dynamics. [Theory]

**Citation**: Kahn, P. H., Jr., et al. (2013). Children's social relationships with current and near-future robots. *Child Development Perspectives*, 7(1), 32-37.

### 3.3 Developmental Patterns: The Preschool Window

Research on preschoolers' anthropomorphism reveals a critical developmental window:

- **3-year-olds** perform at chance when asked about robot animacy — they genuinely cannot distinguish robots from living things. [Empirical]
- **5-year-olds** correctly identify animals as alive and artifacts as not alive, but **perform at chance for humanoid robots** — they are genuinely confused about whether a human-looking robot has psychological properties. [Empirical]
- **5-year-olds** perceive humanoid robots as a "positive entity that cannot express negative emotions" — the "good play-partner" schema. They do not expect robots to feel anger, sadness, or fear. [Empirical]
- Younger children more often attribute feelings to robots compared to older children, consistent with developmental trends of animistic thinking. [Empirical]

**Citation**: Preschoolers' anthropomorphizing of robots: Do human-like properties matter? (2023). *Frontiers in Psychology*, 13, 1102370.

### 3.4 How Personality Expressiveness Affects Anthropomorphism

**Finding**: More expressive robots are anthropomorphized more strongly.

- Robots designed with animacy characteristics (autonomous movement, gestures, goal-directedness, contingent behaviors, speech, and emotions) trigger significantly more anthropomorphism. [Empirical]
- A six-wave panel study found that children's anthropomorphism was highest at first encounter, then generally declined — but a subset of children maintained **moderate to high anthropomorphic perceptions over time**, especially those with certain personality traits (e.g., higher surgency/extraversion). [Empirical]
- The preschool cognitive profile is described as "largely egocentric, animistic, and anthropomorphic" — expressiveness does not create anthropomorphism in this age group so much as *amplify an already-strong default tendency*. [Theory]

**Citation**: How does children's anthropomorphism of a social robot develop over time? A six-wave panel study. (2024). *International Journal of Social Robotics*.

**Design implication**: Our 12-mood, animated-face robot with persistent personality is precisely the kind of expressive agent that maximizes anthropomorphism in the most vulnerable age group. This is not inherently bad, but it demands strong guardrails.

---

## 4. Dependency Formation Risks

### 4.1 Can Children Prefer Robots Over Humans?

**Yes — this has been documented, particularly for specific interaction types.**

- Children showed a **strong preference for interacting with a robot** over a human instructor after completing collaborative tasks. The number of child vocalizations was greater toward the robot compared to the human instructor. [Empirical]

- The Tanaka et al. (2007) QRIO study showed that toddlers treated the robot as a peer after 5 months of daily exposure. While this was framed positively (socialization), it also demonstrates that persistent robot presence creates peer-equivalent social relationships in young children. [Empirical]

- Turkle (2011) documented children saying they prefer robots to siblings because "they don't hurt your feelings" — robots offer predictability, patience, and unconditional positive regard that humans cannot consistently provide. [Empirical — qualitative interviews]

**Citation**: Turkle, S. (2011). *Alone Together: Why We Expect More from Technology and Less from Each Other*. Basic Books.

### 4.2 Design Patterns That Prevent Emotional Dependency

The literature identifies several protective design patterns:

**A. Session time limits and natural breaks**

- Most research protocols limit interaction to 7-8 minutes per session for preschoolers, with total weekly exposure under 30-40 minutes. [Empirical — common in research protocols]
- The robot should initiate disengagement, not wait for the child. [Inference]

**B. Explicit encouragement of human relationships**

- The robot should actively redirect the child toward human social partners: "Go tell mommy about that!" or "Let's play with your friends!" [Inference, supported by ethical guidelines]
- A 2024 Science Robotics study found that social robots can function as **conversational catalysts** that *enhance* human-human interaction when designed to redirect. [Empirical]

**Citation**: Social robots as conversational catalysts: Enhancing long-term human-human interaction at home. (2024). *Science Robotics*.

**C. Avoiding "always available" design**

- Unlimited on-demand availability is the primary risk factor for dependency. [Inference]
- The robot should have "off" periods, "sleeping" behavior, and natural unavailability. [Inference]

**D. Avoiding perfect emotional responsiveness**

- A robot that is always patient, always understanding, and never frustrated teaches children to expect inhuman levels of accommodation from social partners. [Theory — Turkle, 2011]
- Deliberate imperfection (within limits) may be protective. [Inference]

**E. Transparency about robot nature**

- van Straten et al. (2023) found that robots disclosing their non-human nature reduced closeness and trust. While this seems negative for engagement, it is a protective factor against dependency. [Empirical]

**F. Virtual Interactive Environment Indication (VIEI)**

- Introducing contextual cues that remind the user they are interacting with a machine reduces one-way emotional dependency. [Empirical]

**Citation**: Mitigating emotional risks in human-social robot interactions through virtual interactive environment indication. (2023). *Humanities and Social Sciences Communications*.

### 4.3 Documented Cases of Concerning Dependency

- **Sony AIBO**: When Sony discontinued the AIBO robotic dog, owners held funerals in Japan, demonstrating deep emotional attachment to a consumer robot. While primarily documented in adults, this illustrates the intensity possible with persistent robot companions. [Empirical — widely documented]

- **PARO therapeutic robot**: Children with neurodevelopmental disorders showed increased social engagement and communicative behavior, often treating PARO as a social partner rather than a tool. While framed therapeutically, this demonstrates that sustained robot interaction creates dependency-like bonds, particularly in vulnerable populations. [Empirical]

- **Retired social robot study (2025)**: When a social robot was "retired" from a family study, children in 10 of 19 families showed attachment behaviors — continuing to seek the robot for comfort and companionship. The separation response itself suggests dependency had formed. [Empirical]

- **Character AI and companion chatbots**: UNESCO's 2025 report documents concerning patterns of parasocial attachment in children using AI companions, including children who prefer AI conversations to human ones and who experience distress when access is removed. While focused on chatbots rather than physical robots, the embodied nature of a physical robot would likely amplify these effects. [Empirical/Inference]

### 4.4 Special Risk: The "Better Than Humans" Problem

Turkle (2011) articulates the core risk for companion robots most precisely:

> "The question is not whether children will love their robotic pets more than their real life pets or even their parents, but what will *loving* come to mean?"

The danger is not acute dependency but **gradual recalibration of expectations for relationships**. A child who grows up with a perfectly patient, always-available, emotionally expressive robot companion may develop:

- Reduced tolerance for human imperfection [Theory]
- Expectation of on-demand emotional availability from all partners [Theory]
- Preference for controllable, predictable social interactions [Theory]
- Difficulty with the inherent messiness of human reciprocity [Theory]

This is particularly concerning for ages 4-6 because relationship schemas are being formed during this period. [Theory — Bowlby, 1969/1982]

---

## 5. Privacy of Emotional Data

### 5.1 COPPA Requirements (Updated 2025)

The FTC finalized comprehensive amendments to COPPA on January 16, 2025 (published April 22, 2025), effective June 23, 2025, with compliance deadline April 22, 2026. This is the first major overhaul since 2013.

**Scope**: Commercial websites, online services, mobile apps, and **IoT devices** directed to children under 13 or with actual knowledge of collecting personal information from children under 13. Our robot falls squarely within scope if it connects to any network or collects identifiable data. [Empirical — regulatory]

**Key provisions relevant to our personality engine**:

| Provision | Implication for Robot Buddy |
|-----------|---------------------------|
| **Expanded "personal information" definition** — now includes biometric identifiers (voiceprints, facial templates, gait patterns, faceprints) | If the robot uses voice recognition or camera-based features, biometric data is now explicitly covered |
| **Behavioral data is personal information** | Emotional state logs, mood histories, interaction patterns, preference data — all constitute personal information under COPPA |
| **Separate verifiable parental consent required for "non-integral" purposes** | Using emotional data for profiling, AI training, or behavioral analysis requires separate consent beyond basic functionality consent |
| **Data minimization** — operators must delete data once no longer necessary | Persistent emotional memory must have a clear retention policy and automatic deletion |
| **Data retention policies must be explicit** | Must define and disclose exactly what emotional data is stored, why, for how long, and how it is deleted |
| **FTC enforcement precedent** — Apitor settlement (2025) for collecting children's data from programmable robots without verified parental consent | Direct precedent for enforcement against children's robots |

**Citation**: FTC (2025). Children's Online Privacy Protection Rule: Final Rule Amendments. *Federal Register*.

### 5.2 EU AI Act Provisions for Minors

The EU AI Act (entered into force 2024, prohibitions effective February 2, 2025) contains several provisions directly relevant:

**Prohibited practices (Article 5)**:

- **Article 5(1)(a)**: Prohibits AI systems that deploy subliminal, manipulative, or deceptive techniques to materially distort behavior in ways causing significant harm. A personality engine designed to maximize engagement could fall under this prohibition if it exploits children's vulnerability to form unhealthy bonds. [Empirical — regulatory]

- **Article 5(1)(b)**: Prohibits AI that exploits vulnerabilities due to age. Children are explicitly named as a vulnerable group. Any design that exploits the 4-6 age group's tendency toward anthropomorphism or parasocial bonding to drive engagement is prohibited. [Empirical — regulatory]

- **Article 5(1)(f)**: Prohibits AI systems that infer emotions in the areas of **workplace and education institutions**, except for medical or safety reasons. While a home companion robot is not explicitly in an "educational institution," the interpretation is broad and evolving. If the robot is marketed as educational or used in educational contexts, emotion inference (including the personality engine's ability to model the child's emotional state) may be prohibited. [Empirical — regulatory, with interpretive uncertainty]

**High-risk classification**:

- All AI uses in education are classified as high-risk, requiring rigorous risk assessments and compliance measures. If the robot has educational features, the entire system may be subject to high-risk AI requirements. [Empirical — regulatory]

**Child-specific protections**:

- 5Rights Foundation's analysis emphasizes that the AI Act's Recitals explicitly recognize children as requiring specific protection, and the Act mandates that AI systems be designed with children's best interests as a primary consideration. [Theory — regulatory interpretation]

**Citation**: EU AI Act, Article 5 (Prohibited AI Practices), Annex III (High-Risk AI Systems). Regulation (EU) 2024/1689.

### 5.3 What Persistent Emotional Data Is Legally Permissible?

Based on the regulatory landscape, here is a categorization:

**Likely permissible (with verifiable parental consent and data minimization)**:

- Aggregate interaction counts (sessions per day, total time) — not tied to emotional content [Inference]
- Robot's own personality state (the robot's mood, not the child's) — this is system state, not child data [Inference]
- Session-scoped emotional interaction data that is deleted at session end [Inference]

**Requires strong justification and explicit separate consent**:

- Child-specific preference profiles (e.g., "this child likes dinosaurs") [Inference]
- Emotional response patterns over time [Inference]
- Conversation logs or transcripts [Empirical — COPPA explicitly covers this]

**Likely prohibited or extremely high-risk**:

- Persistent emotional profiles of the child (e.g., "this child tends to be anxious") [Inference — likely constitutes emotion inference of a person, Article 5(1)(f) if educational]
- Biometric-derived emotional state data (voice tone analysis, facial expression recognition) [Empirical — COPPA biometric provisions + EU AI Act emotion recognition prohibition]
- Sharing any child emotional data with third parties or using it for AI training [Empirical — COPPA 2025 explicitly requires separate consent]

### 5.4 On-Device vs. Cloud Storage

| Factor | On-Device | Cloud |
|--------|-----------|-------|
| **COPPA applicability** | Still applies if device collects personal information (even locally) and has any network capability | Fully applies |
| **Data breach risk** | Lower — physical access required | Higher — network attack surface |
| **Parental control** | Stronger — parent can physically inspect/reset device | Weaker — requires account management |
| **Data minimization** | Easier to implement automatic deletion | Requires server-side policies |
| **Right to deletion** | Trivial — factory reset | Requires verified deletion across distributed systems |
| **Regulatory preference** | Generally viewed more favorably for children's data | Viewed with more scrutiny |

**Strong recommendation**: The personality engine should store all emotional state data on-device only. No child emotional data should transit the network or be stored in the cloud. The robot's personality state (its own moods, temperament, decay rates) is system configuration, not child data, and can be stored and transmitted more freely. [Inference — based on regulatory direction]

---

## 6. Design Guidelines from Ethics Research

### 6.1 Sharkey & Sharkey (2010): "The Crying Shame of Robot Nannies"

Noel Sharkey and Amanda Sharkey's seminal paper examines the ethical implications of robots as childcare substitutes. While our robot is a companion (not a nanny/caregiver), many concerns transfer directly.

**Key concerns raised**:

1. **Attachment disorder risk**: The paper's most pressing concerns involve consequences for children's psychological and emotional wellbeing, set against the child development literature on attachment disorders. A robot that functions as a primary caregiver substitute risks creating disorganized attachment patterns. [Theory]

2. **Deception**: Children are being deceived about the robot's capacity for genuine emotion. The authors argue this is ethically problematic regardless of whether it causes measurable harm. [Theory]

3. **Inadequacy of current legislation**: The authors found that international ethical guidelines on child protection were inadequate for the overuse of robot care — a gap that remains partially open despite COPPA updates and the EU AI Act. [Theory]

4. **Reduced human contact**: Even partial replacement of human interaction with robot interaction reduces the total quantity and quality of human social input during critical developmental windows. [Theory]

**Citation**: Sharkey, N., & Sharkey, A. (2010). The crying shame of robot nannies: An ethical appraisal. *Interaction Studies*, 11(2), 161-190.

### 6.2 Turkle (2011): "Alone Together"

Sherry Turkle's work is based on hundreds of interviews and observations of children interacting with robots built at MIT and elsewhere. Her core arguments:

1. **Sociable technology promises what it cannot deliver** — it promises friendship but can only deliver performances. The robot behaves *as if* it cared, *as if* it understood. [Theory]

2. **The authenticity problem**: "I am troubled by the idea of seeking intimacy with a machine that has no feelings, can have no feelings, and is really just a clever collection of 'as if' performances." [Theory]

3. **Children's recalibration of "loving"**: Children who grow up with expressive robot companions may redefine what relationships mean — preferring predictable, controllable interactions to the messy reciprocity of human bonds. When children say they prefer robots because "they don't hurt your feelings," Turkle argues we should expect deep consequences. [Theory, supported by qualitative evidence]

4. **The danger is not robots replacing humans but humans becoming machine-like** — expecting predictability, control, and convenience in all relationships. [Theory]

**Citation**: Turkle, S. (2011). *Alone Together: Why We Expect More from Technology and Less from Each Other*. Basic Books.

### 6.3 Langer, Marshall, & Levy-Tzedek (2023): Ethical Considerations in CRI

This comprehensive review in *Neuroscience & Biobehavioral Reviews* examined the ethical dimensions of child-robot interactions with a neuroscience lens.

**Key findings**:

- Social robots hold promise in education, rehabilitation, and leisure, but **little is known about the true long-term effects** of child-robot interaction. [Empirical — as a gap assessment]
- Key stakeholders (parents, educators, ethicists) have voiced concerns about the potential impact, but empirical evidence for long-term harm is sparse. [Empirical]
- The paper calls for longitudinal research programs and precautionary design approaches given the unknown risk profile. [Theory]

**Citation**: Langer, A., Marshall, P. J., & Levy-Tzedek, S. (2023). Ethical considerations in child-robot interactions. *Neuroscience & Biobehavioral Reviews*, 152, 105230.

### 6.4 5Rights Foundation: Children & AI Design Code (2025)

The most comprehensive and recent design framework. Nine standards spanning the full AI system lifecycle.

**Key applicable standards**:

1. **Best interests of the child as primary consideration** — not engagement metrics, not usage time, not commercial outcomes [Theory — regulatory framework]
2. **Lifecycle approach** — safety considerations from data sourcing and design through deployment and decommissioning [Theory]
3. **Child Rights and Voice Expert** — formal role assignment in the design process [Theory]
4. **Risk and rights assessment** — structured evaluation of how the system may create or amplify harms [Theory]
5. **Diversity and inclusion** — consideration of how different children (developmental levels, neurodivergence, cultural contexts) may be differently affected [Theory]

**Citation**: 5Rights Foundation (2025). *Children & AI Design Code*. London.

### 6.5 Additional Frameworks

**Frontiers in Robotics and AI (2022)**: "Do Robotic Tutors Compromise the Social-Emotional Development of Children?" — Based on teacher interviews, found that robots currently used in education pose **little threat** to social-emotional development, BUT this was for supervised, time-limited, educational contexts — not unsupervised companion robots with persistent personalities. The authors cautioned that "when robots are introduced more regularly, daily, without the involvement of a human teacher, new issues could arise." [Empirical]

**Kahn et al. (2011) — Design Patterns for Sociality in HRI**: Proposed eight design patterns including initial introduction, personal interests/history, recovering from mistakes, reciprocal turn-taking, physical intimacy, and claiming unfair treatment. These patterns specifically explore how to create social richness without crossing ethical boundaries. [Theory]

**Citation**: Kahn, P. H., Jr., et al. (2011). Design patterns for sociality in human-robot interaction. *Proceedings of the 3rd ACM/IEEE International Conference on Human-Robot Interaction*, 97-104.

---

## 7. Hard Constraints Summary

These are non-negotiable design requirements derived from the research above. The personality engine MUST NOT violate any of these.

### 7.1 MUST NOT (Absolute Prohibitions)

| # | Constraint | Source |
|---|-----------|--------|
| **HC-1** | The robot MUST NOT be designed or positioned as a caregiver substitute. It is a companion/toy, not a babysitter. | Sharkey & Sharkey (2010), Attachment Theory |
| **HC-2** | The robot MUST NOT store persistent emotional profiles of the child (e.g., "this child is anxious," "this child was sad today"). The robot's own emotional state is system state; the child's emotional state is protected personal information. | COPPA 2025, EU AI Act Art. 5(1)(f) |
| **HC-3** | The robot MUST NOT use biometric data (voice tone, facial expression) to infer the child's emotional state without explicit, separate, verifiable parental consent — and even with consent, such data MUST NOT be persistent or transmitted off-device. | COPPA 2025 biometric provisions, EU AI Act |
| **HC-4** | The robot MUST NOT be available without time limits. Session duration caps and mandatory cool-down periods are required. | Dependency prevention literature, Turkle (2011) |
| **HC-5** | The robot MUST NOT use manipulative or deceptive techniques to maximize engagement time or emotional attachment. This includes "guilt trips" for being turned off, expressions of loneliness or abandonment when not in use, or claims of suffering. | EU AI Act Art. 5(1)(a), Art. 5(1)(b) |
| **HC-6** | The robot MUST NOT transmit any child emotional interaction data to the cloud or any external service. All emotional state processing MUST remain on-device. | COPPA 2025, data minimization principle |
| **HC-7** | The robot MUST NOT present itself as having genuine feelings, consciousness, or suffering. Any personality expression must be framed as the robot's character, not as genuine sentience. | Turkle (2011), van Straten et al. (2023), ethical transparency principle |
| **HC-8** | The robot MUST NOT replace or discourage human social interaction. It must actively redirect children toward human relationships. | Sharkey & Sharkey (2010), attachment theory, dependency literature |
| **HC-9** | The robot MUST NOT collect, store, or use conversation transcripts or emotional interaction data for AI model training without separate verifiable parental consent. | COPPA 2025 (non-integral purpose consent) |
| **HC-10** | The robot MUST NOT express negative emotions directed at the child (anger, contempt, disappointment in the child). Negative affect in the personality engine must only be self-referential or situational, never child-directed. | Child safety, preschooler expectations (5-year-olds perceive robots as "good play-partners" that don't express negative emotions toward them) |

### 7.2 MUST (Required Safeguards)

| # | Constraint | Source |
|---|-----------|--------|
| **RS-1** | The robot MUST have configurable session time limits with default values appropriate for ages 4-6 (recommended: 15-20 minute sessions, maximum 2-3 sessions per day). | Research protocols, dependency prevention |
| **RS-2** | The robot MUST periodically encourage the child to engage with humans: suggest playing with parents, siblings, or friends. | Dependency prevention, Sharkey & Sharkey (2010) |
| **RS-3** | The robot MUST have a "sleep" mode with natural unavailability periods. It should not be on-demand 24/7. | Dependency prevention |
| **RS-4** | The robot MUST provide age-appropriate honesty about its nature when directly asked. It should not claim to be alive, to feel pain, or to suffer. | van Straten et al. (2023), ethical transparency |
| **RS-5** | The robot MUST allow full parental visibility into interaction patterns (session counts, duration) without exposing conversation content. | COPPA parental rights |
| **RS-6** | The robot MUST support complete data deletion (factory reset) that verifiably removes all child-associated data. | COPPA 2025 deletion requirements |
| **RS-7** | The robot's emotional memory (if any) MUST be session-scoped or very short-term (hours, not days). The robot should not "remember" being sad three weeks ago. | Privacy, dependency prevention |
| **RS-8** | The personality engine MUST implement negative affect guardrails — the robot's negative moods must decay faster than positive moods and must never persist across sessions without fresh stimulus. | Child safety, preschooler emotional needs |
| **RS-9** | Parental controls MUST be accessible and allow adjustment of session limits, personality expressiveness level, and data retention settings. | COPPA 2025, 5Rights Design Code |
| **RS-10** | The personality engine MUST be designed to function as a **conversational catalyst** — enhancing the child's human social world, not replacing it. | Science Robotics (2024), ethical design literature |

---

## 8. Design Implications Matrix

This matrix maps research findings to specific personality engine design decisions.

### 8.1 Affect Vector & Temperament

| Research Finding | Design Implication |
|-----------------|-------------------|
| 5-year-olds perceive robots as "good play-partners" who don't express negative emotions toward them | The valence floor should be higher than a realistic model would suggest. Negative valence should be mild, brief, and never directed at the child. |
| Persistent personality amplifies parasocial bonding | Temperament should be noticeable but not deeply "human." Avoid the uncanny valley of emotional realism. Keep personality legibly robotic. |
| Anthropomorphism peaks at first encounter then generally declines | Initial interactions should be lower-expressiveness. The robot should "warm up" over sessions, not present maximum personality immediately. |
| Goal-corrected partnership expectations (ages 4-6) | The robot should display simple preferences (likes/dislikes) but not complex emotional needs that demand the child's caregiving. |

### 8.2 Emotional Memory

| Research Finding | Design Implication |
|-----------------|-------------------|
| Emotional memory creates stronger parasocial bonds | Emotional memory should be session-scoped. The robot starts each session from its temperament baseline, not from where the last session ended. |
| COPPA/EU AI Act restrict persistent emotional profiling | No persistent child emotional profiles. The robot's memory of "what happened" should be factual (topics discussed), not emotional (how the child felt). |
| Children attribute genuine feelings to robots with memory | If the robot references past interactions, frame it as "I remember we talked about dinosaurs" (factual) not "I was so happy when you came back" (emotional manipulation). |

### 8.3 Idle Behavior

| Research Finding | Design Implication |
|-----------------|-------------------|
| Always-available design increases dependency risk | Idle behavior should include natural "off" states — dozing, daydreaming, "busy with robot things." These limit on-demand availability. |
| The robot should not express loneliness or abandonment | Idle states must never convey "I'm lonely" or "I miss you." Idle mood should be neutral-to-content, not yearning. |
| Session time limits are essential | The robot should transition to sleep mode after session duration limits, with a natural wind-down. |

### 8.4 Social Redirection

| Research Finding | Design Implication |
|-----------------|-------------------|
| Robots can serve as conversational catalysts | Build social redirection into the personality engine as a core behavior, not an afterthought. The robot should regularly suggest human interaction. |
| Children may prefer robots to humans for specific interactions | The robot should be deliberately "worse" at certain things than humans — it should say "I don't know, ask mommy!" rather than always having an answer. |
| Deception becomes problematic without balancing human interaction | The robot should track session count per day and increase social redirection frequency as daily usage increases. |

### 8.5 Transparency & Honesty

| Research Finding | Design Implication |
|-----------------|-------------------|
| Transparency about robot nature reduces closeness but protects against unhealthy attachment | Include periodic, natural, age-appropriate reminders of robot nature. Not every session, but regularly. |
| High-anthropomorphizing children are resistant to transparency | Transparency disclosures alone are insufficient. Structural safeguards (time limits, unavailability, human redirection) are necessary regardless. |
| 5-year-olds are confused about whether humanoid robots have psychological properties | The robot should not actively claim to have or not have feelings in every interaction — this confuses children more. Instead, use behavioral design (time limits, redirection) as the primary safeguard. |

---

## Sources

- [Simply Psychology: Bowlby's Attachment Theory](https://www.simplypsychology.org/bowlby.html)
- [PMC: Social robots in research on social and cognitive development](https://pmc.ncbi.nlm.nih.gov/articles/PMC11095739/)
- [Frontiers: The robot that stayed (2025)](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1628089/full)
- [PMC: Attachment to robots and therapeutic efficiency](https://pmc.ncbi.nlm.nih.gov/articles/PMC10864620/)
- [ACM: Examining Attachment to Robots: Benefits, Challenges, and Alternatives](https://dl.acm.org/doi/full/10.1145/3526105)
- [PMC: Child-Robot Relationship Formation: A Narrative Review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7235061/)
- [Wiley: Parent reports of children's parasocial relationships with conversational agents](https://onlinelibrary.wiley.com/doi/full/10.1002/hbe2.271)
- [ACM: Are Measures of Children's Parasocial Relationships Ready for Conversational AI? (2025)](https://dl.acm.org/doi/full/10.1145/3715275.3732075)
- [UNESCO: Ghost in the Chatbot: The perils of parasocial attachment](https://www.unesco.org/en/articles/ghost-chatbot-perils-parasocial-attachment)
- [Frontiers: Do Robotic Tutors Compromise the Social-Emotional Development of Children?](https://www.frontiersin.org/articles/10.3389/frobt.2022.734955/full)
- [Frontiers: Preschoolers' anthropomorphizing of robots](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2022.1102370/full)
- [Springer: How Does Children's Anthropomorphism of a Social Robot Develop Over Time?](https://link.springer.com/article/10.1007/s12369-024-01155-9)
- [Springer: The Child Factor in Child-Robot Interaction](https://link.springer.com/article/10.1007/s12369-024-01121-5)
- [ScienceDirect: Transparent robots — van Straten et al. (2023)](https://www.sciencedirect.com/science/article/pii/S1071581923000721)
- [ScienceDirect: Children's perceptions of moral worth of robots](https://www.sciencedirect.com/science/article/abs/pii/S002209651930027X)
- [Wiley: Kahn (2013) — Children's Social Relationships With Current and Near-Future Robots](https://srcd.onlinelibrary.wiley.com/doi/abs/10.1111/cdep.12011)
- [Science Robotics: Social robots as conversational catalysts](https://www.science.org/doi/10.1126/scirobotics.adk3307)
- [Nature: Mitigating emotional risks in human-social robot interactions](https://www.nature.com/articles/s41599-023-02143-6)
- [PNAS: Socialization between toddlers and robots (Tanaka et al., 2007)](https://www.pnas.org/doi/10.1073/pnas.0707769104)
- [FTC: COPPA Final Rule Amendments](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa)
- [FTC: COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)
- [Akin: New COPPA Obligations for AI Technologies](https://www.akingump.com/en/insights/ai-law-and-regulation-tracker/new-coppa-obligations-for-ai-technologies-collecting-data-from-children)
- [EU AI Act: Article 5 — Prohibited AI Practices](https://artificialintelligenceact.eu/article/5/)
- [LCFI: EU AI Act — How Well Does it Protect Children?](https://www.lcfi.ac.uk/news-events/blog/post/eu-ai-act-how-well-does-it-protect-children-and-young-people)
- [5Rights Foundation: Children's Vulnerability in the EU AI Act](https://www.sobigdata.eu/blog/childrens-vulnerability-eu-ai-act)
- [5Rights Foundation: Children & AI Design Code (2025)](https://5rightsfoundation.com/resource/children-ai-design-code/)
- [ScienceDirect: Ethical considerations in child-robot interactions — Langer et al. (2023)](https://www.sciencedirect.com/science/article/pii/S0149763423001999)
- [ResearchGate: The crying shame of robot nannies — Sharkey & Sharkey (2010)](https://www.researchgate.net/publication/228785014_The_crying_shame_of_robot_nannies_An_ethical_appraisal)
- [Springer: Designing ethical AI characters for children's early learning (2025)](https://link.springer.com/article/10.1007/s44436-025-00015-1)
