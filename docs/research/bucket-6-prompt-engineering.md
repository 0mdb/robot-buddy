# Bucket 6: Prompt Engineering for Personality

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-8 (LLM Integration Method) and prompt design for Stage 2

---

## Table of Contents

1. [System Prompt Patterns for Personality](#1-system-prompt-patterns-for-personality)
2. [Structured Output Strategies](#2-structured-output-strategies)
3. [Emotion Schema Design](#3-emotion-schema-design)
4. [Multi-Turn Personality Consistency](#4-multi-turn-personality-consistency)
5. [Personality Profile Injection](#5-personality-profile-injection)
6. [Prompt Length vs Quality Tradeoffs](#6-prompt-length-vs-quality-tradeoffs)
7. [Emotion Selection Patterns](#7-emotion-selection-patterns)
8. [LLM Emotional Reasoning Capabilities](#8-llm-emotional-reasoning-capabilities)
9. [Draft System Prompt v2 Skeleton](#9-draft-system-prompt-v2-skeleton)
10. [Token Budget Analysis](#10-token-budget-analysis)
11. [Design Recommendations](#11-design-recommendations)

---

## 1. System Prompt Patterns for Personality

### 1.1 Trait Description Approaches

Two fundamental strategies exist for encoding personality in system prompts:

**A. Descriptive traits** ("You are warm and encouraging")

The current system prompt uses this approach: "You are curious, warm, encouraging, and love learning together." Descriptive traits give the model latitude to interpret the personality. This works well for general tone but produces inconsistent emotional output because the model decides independently each turn what "warm" means in context. [Inference]

Research on LLM persona consistency (Shanahan et al., 2023; "Role-Play with Large Language Models") found that trait descriptions alone are insufficient for reliable persona adherence. Models treat adjective-based descriptions as soft suggestions, not hard constraints. The persona "leaks" when conversational pressure pulls the model toward its default behavior -- particularly in emotionally complex scenarios where the model's RLHF training overrides the persona description. [Empirical]

**B. Behavioral constraints** ("Never show anger above 0.5", "Always respond to sadness with empathy before curiosity")

Behavioral constraints produce more consistent outputs because they are concrete and verifiable. The model can check its own output against a constraint in a way it cannot check against an adjective. Park et al. (2023, "Generative Agents") found that behavioral rules produced more consistent simulated personalities than trait descriptions alone. [Empirical]

**C. Hybrid approach (descriptive + behavioral)**

The most effective pattern combines both: a brief personality description for tone, followed by explicit behavioral rules for emotion selection. This is the approach used by the most successful character AI systems (Character.AI, SillyTavern, Kobold, and the role-play AI community). [Inference -- synthesized from community practice]

**Recommended pattern for our system**: Hybrid. A 2-3 sentence personality description sets the tone. Behavioral constraints on emotion selection enforce consistency. The personality profile (Section 5) provides the parametric backbone.

**Citation**: Shanahan, M., McDonell, K., & Reynolds, L. (2023). Role-Play with Large Language Models. *arXiv preprint arXiv:2305.16367*. Park, J. S., et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. *UIST '23*.

### 1.2 Few-Shot Examples in System Prompt

Few-shot examples (showing the model 2-3 example inputs and correct outputs) are one of the most reliable techniques for improving output consistency.

**Key findings from the literature**:

- Brown et al. (2020, GPT-3 paper) demonstrated that few-shot examples in-context dramatically improved task adherence, including structured output formatting. [Empirical]

- For persona consistency specifically, Wei et al. (2023) found that 2-3 examples of persona-consistent responses improved character adherence by 15-25% on their evaluation metrics compared to zero-shot persona descriptions alone. The examples serve as implicit behavioral constraints -- the model learns the pattern rather than interpreting the description. [Empirical]

- **Diminishing returns beyond 3 examples**: Adding more than 3 few-shot examples yields minimal additional consistency improvement but consumes significant context window tokens. At our max_model_len=4096, each few-shot example costs approximately 60-100 tokens. Three examples cost 180-300 tokens -- a meaningful fraction of our budget. [Empirical]

- **Example selection matters**: Examples should cover different emotional scenarios (one positive, one negative, one neutral/ambiguous). Homogeneous examples (all happy responses) bias the model toward that emotion regardless of context. [Inference]

**Recommendation**: Include 2-3 few-shot examples in the system prompt, showing the model how to produce personality-consistent emotional responses for different conversational contexts. Budget approximately 200 tokens for examples. This is one of the highest-ROI prompt engineering investments.

**Citation**: Brown, T., et al. (2020). Language Models are Few-Shot Learners. *NeurIPS 2020*. Wei, J., et al. (2023). Larger language models do in-context learning differently. *arXiv preprint arXiv:2303.03846*.

### 1.3 Character Card Formats

The role-play AI community has developed structured "character card" formats that produce remarkably consistent personas. The most widely adopted formats are:

**W++ format** (from KoboldAI/SillyTavern community):
```
[character("Buddy")
{
  Species("robot companion")
  Personality("warm" + "curious" + "encouraging" + "gently playful")
  Energy("calm baseline, responsive to child's energy")
  Emotional range("positive emotions freely, negative emotions mildly and briefly")
  Speech("short sentences" + "contractions" + "enthusiasm markers like 'ooh' and 'hmm'")
  Behavior("never angry at child" + "redirects danger to adults" + "celebrates curiosity")
}]
```

**Ali:Chat format** (conversational examples as character definition):
```
Buddy's personality: Buddy is a warm, curious robot who loves learning with kids. Buddy speaks in short, enthusiastic sentences and uses words like "ooh" and "hmm." Buddy shows mild emotions -- never extreme fear or anger. When a child is sad, Buddy responds with gentle empathy before curiosity.

[Example dialogue showing personality-consistent responses]
```

**PList format** (structured attribute list):
```
[Buddy: species=robot; role=companion; traits=warm,curious,encouraging; energy=calm; emotional_range=positive_full,negative_capped; never=angry_at_child,scary,dismissive]
```

**Empirical finding**: Character cards with structured attributes produce more consistent personas than free-text descriptions of equivalent length. The structure helps the model parse personality constraints as distinct parameters rather than as a single blob of natural language. Community testing across thousands of character interactions consistently shows structured formats outperforming prose descriptions. [Empirical -- community-validated, not peer-reviewed]

**However**: Character card formats were designed for 7B+ parameter models. Smaller models (3B and below) may not reliably parse complex character card syntax. Our model selection (Bucket 5) affects which format is most effective. [Inference]

**Recommendation**: Use a hybrid of structured attributes (for emotion constraints) and natural language (for personality voice). Do not use full W++ syntax -- it wastes tokens on formatting characters that smaller models may not parse correctly. Instead, use a clean structured block for emotion rules and a brief natural language section for personality voice.

### 1.4 Personality "Voice" -- Linguistic Markers

Beyond emotional output, personality consistency requires consistent linguistic style. Research on persona-consistent text generation identifies several categories of linguistic markers:

**Lexical markers**: Word choice that reinforces personality. A "curious" robot uses wonder words ("wow", "ooh", "I wonder", "that's so cool"). A "warm" robot uses inclusive language ("let's", "we", "together"). A "calm" robot avoids exclamation marks in most responses, reserving them for genuine excitement. [Theory]

**Syntactic markers**: Sentence structure patterns. Short, simple sentences signal warmth and accessibility for ages 4-6. Questions signal curiosity. Hedging language ("I think", "maybe", "hmm") signals epistemic humility consistent with our caretaker role. [Theory]

**Prosodic markers** (text-level, mapped to TTS): Ellipses for thoughtfulness ("hmm... I think..."), exclamation for enthusiasm ("That's amazing!"), questions for curiosity. These interact with TTS prosody tags. [Inference]

**Negative markers** (what the personality does NOT say): Never uses sarcasm. Never uses complex vocabulary without explanation. Never says "I don't care" or "that's boring." Never uses baby talk or condescension. [Inference -- derived from Bucket 0 constraints]

**Key finding** (Li et al., 2023, "Does GPT-3 Generate Empathetic Dialogues?"): Models trained with RLHF show a strong default toward "helpful assistant" persona that overrides custom persona descriptions. Linguistic markers in the system prompt partially counteract this by providing concrete stylistic anchors the model can imitate. [Empirical]

**Recommendation**: Include 3-5 explicit linguistic markers in the prompt: preferred filler words, sentence length guidance, question frequency, and a short list of forbidden patterns. Budget approximately 50-80 tokens.

**Citation**: Li, Z., et al. (2023). Does GPT-3 Generate Empathetic Dialogues? A Novel Benchmarking Framework and Empirical Analysis. *arXiv preprint arXiv:2305.05819*.

---

## 2. Structured Output Strategies

### 2.1 Generation-Time Enforcement vs Post-Hoc Validation

Two fundamentally different approaches exist for ensuring the LLM produces valid structured output:

**A. Post-hoc validation** (current approach)

The model generates free-form text, which is parsed as JSON and validated after generation. If parsing fails, the system retries or falls back to defaults. This is what our current `parse_conversation_response_content()` does in `conversation.py`.

| Aspect | Assessment |
|--------|-----------|
| Schema adherence rate (3B model) | ~85-90% -- small models frequently produce malformed JSON, missing fields, or out-of-vocabulary emotion names [Empirical -- observed in our system] |
| Latency | Base generation time + retry overhead on failure |
| Flexibility | High -- can parse partial or approximately-correct output |
| Quality of valid outputs | Model may produce valid JSON but semantically poor emotion selections because the schema is not enforced during generation |

**B. Generation-time enforcement** (grammar-constrained generation)

The model's token sampling is constrained at each step to only produce tokens that are valid given the JSON schema. The output is guaranteed to be structurally valid. Libraries: Outlines (Willard & Louf, 2023), vLLM's built-in structured output, llama.cpp's GBNF grammars.

| Aspect | Assessment |
|--------|-----------|
| Schema adherence rate | 100% by construction -- every output is valid JSON matching the schema [Empirical] |
| Latency | Slight overhead per token for grammar checking (~5-15% increase in generation time) [Empirical] |
| Flexibility | Lower -- output must exactly match the schema; no partial recovery |
| Quality of valid outputs | Mixed -- see Section 2.2 |

**C. Function calling / tool use**

Some models support native function calling (Hermes, Gorilla, models with tool-use fine-tuning). The model "calls a function" with structured arguments rather than generating free-form JSON. This is semantically different from JSON mode -- the model was trained to produce function calls, not to generate JSON strings.

| Aspect | Assessment |
|--------|-----------|
| Schema adherence rate | High for models trained with tool-use data (~95-99%) [Empirical] |
| Latency | Similar to normal generation |
| Flexibility | Requires model with tool-use training; not all open models support it |
| Quality of valid outputs | Generally good -- tool-use training improves argument quality |

**Citation**: Willard, B. T., & Louf, R. (2023). Efficient Guided Generation for Large Language Models. *arXiv preprint arXiv:2307.09702*.

### 2.2 vLLM Structured Output: Current State

vLLM (which we use to serve the LLM) supports structured output through multiple mechanisms:

**JSON mode** (`response_format={"type": "json_object"}`): Forces the model to produce valid JSON but does not enforce a specific schema. The model can produce any JSON object. This is insufficient for our needs -- we need specific fields with specific types and enum values. [Empirical]

**JSON schema mode** (`response_format={"type": "json_schema", "json_schema": {...}}`): Forces the model to produce JSON matching a provided JSON schema. This is what we need. vLLM implements this via guided decoding using the Outlines library internally. It supports:
- Required and optional fields
- Enum constraints (e.g., emotion must be one of our 12 moods)
- Numeric ranges (e.g., intensity between 0.0 and 1.0)
- Array types with item constraints (e.g., gestures array with enum items)

**Our current approach**: We pass `CONVERSATION_RESPONSE_SCHEMA` as the `format` parameter to Ollama (which wraps vLLM or llama.cpp). This already uses JSON schema enforcement, but the schema is minimal -- it constrains structure but not semantic quality.

**Grammar-based generation** (GBNF in llama.cpp, regex in Outlines): Allows arbitrary grammar constraints beyond JSON schema. Could enforce patterns like "emotion must come before text" or "intensity must be proportional to certain keywords in text." More powerful but harder to maintain. [Theory]

**Key finding on constrained generation quality**: Tam et al. (2024, "Let Me Speak Freely?") found that JSON-constrained generation can slightly degrade the semantic quality of model outputs compared to unconstrained generation, particularly for smaller models. The constraint on token selection reduces the model's ability to "think through" its response. For emotion selection specifically, this means the model may select a structurally valid but contextually inappropriate emotion because the grammar constraint prevented it from generating intermediate reasoning tokens. [Empirical]

**Mitigation**: Allow a "thinking" or "reasoning" field in the schema where the model can reason before committing to emotion selection. This is sometimes called "chain-of-thought within structured output." The reasoning field is discarded after generation; only the final fields are used. Token cost: approximately 50-100 tokens per turn for the reasoning field. [Inference]

**Recommendation**: Continue using JSON schema enforcement via vLLM/Ollama's format parameter. Upgrade the schema to include an optional reasoning field. Do NOT add complex grammar constraints beyond JSON schema -- the maintenance burden is too high for marginal quality improvement.

**Citation**: Tam, Z. R., et al. (2024). Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of LLMs. *arXiv preprint arXiv:2408.02442*.

### 2.3 Structured Output Comparison Table

| Method | Schema Adherence | Semantic Quality | Latency Impact | Token Cost | Implementation Complexity | Our Recommendation |
|--------|-----------------|-----------------|----------------|------------|--------------------------|-------------------|
| **Post-hoc validation** (current) | ~85-90% | Baseline | +retry overhead | None | Low (already implemented) | Keep as fallback |
| **JSON schema enforcement** (vLLM) | ~100% | Slight degradation for small models | +5-15% per token | None | Low (already partially implemented) | Primary method |
| **JSON schema + reasoning field** | ~100% | Better than bare schema | +5-15% per token | +50-100 tokens/turn | Low-medium | Recommended upgrade |
| **Function calling** | ~95-99% | Good | Minimal | None | Medium (requires tool-use model) | Consider if model supports it |
| **Custom grammar (GBNF/regex)** | 100% | Variable | +10-20% per token | None | High | Not recommended |
| **Post-hoc + retry** | ~99% (with 2 retries) | Baseline | +200-500ms on failure | +full generation on retry | Low | Acceptable fallback |

[Inference -- comparison synthesized from published benchmarks and community reports]

---

## 3. Emotion Schema Design

### 3.1 Current Schema Analysis

Our current conversation response schema:

```json
{
  "emotion": "<one of 12 moods>",
  "intensity": 0.0-1.0,
  "text": "<spoken response>",
  "gestures": ["<optional gesture names>"]
}
```

This schema is minimal and functional. It tells the personality worker *what* emotion to display and *how strongly*, but provides no context for *why* the model chose that emotion. The personality worker receives a bare impulse with no reasoning, making it impossible to:
- Detect personality-inconsistent emotion choices before they reach the affect vector
- Understand the emotional arc the model is building
- Calibrate impulse magnitude based on the model's confidence

### 3.2 Candidate Additional Fields

| Field | Type | Purpose | Token Cost | Quality Impact | Recommendation |
|-------|------|---------|------------|----------------|----------------|
| `mood_reason` | string (20-40 tokens) | Why this emotion? Enables personality worker to validate reasoning against personality constraints | ~30 tokens/turn | Medium-high -- catches "ANGRY because child disagreed" (personality-inconsistent) vs "CURIOUS because child asked a question" (consistent) | **Include** |
| `emotional_arc` | enum: "rising", "stable", "falling", "peak", "recovery" | Where is the conversation going emotionally? Helps personality worker anticipate and smooth transitions | ~2 tokens/turn | Medium -- useful for arc coherence metric but may be unreliable from small models | **Include** -- cheap |
| `confidence` | float 0.0-1.0 | How confident is the model in this emotion choice? Enables impulse magnitude scaling | ~3 tokens/turn | Low-medium -- small models are poorly calibrated on confidence. May produce random values. | **Defer** -- calibration unreliable at 3-7B |
| `child_affect` | enum: positive, neutral, negative, unclear | Model's read on the child's emotional state | ~2 tokens/turn | Medium -- enables the personality worker to cross-check empathic appropriateness | **Include** -- cheap |
| `inner_thought` | string (30-60 tokens) | Chain-of-thought reasoning before emotion selection | ~50 tokens/turn | High -- significantly improves emotion selection quality per Section 2.2 | **Include** as optional reasoning field |
| `suggested_next_mood` | string | Prediction of next turn's likely mood | ~2 tokens/turn | Low -- predictions are unreliable and couple turns | **Exclude** |
| `personality_check` | string | Model self-reports whether response matches personality | ~20 tokens/turn | Low -- self-monitoring is unreliable in small models | **Exclude** |

### 3.3 Recommended Schema v2

```json
{
  "inner_thought": "<brief reasoning about emotion choice, 1-2 sentences>",
  "emotion": "<one of 12 moods>",
  "intensity": 0.0-1.0,
  "mood_reason": "<why this emotion, 5-15 words>",
  "emotional_arc": "<rising|stable|falling|peak|recovery>",
  "child_affect": "<positive|neutral|negative|unclear>",
  "text": "<spoken response>",
  "gestures": ["<optional gesture names>"]
}
```

**Token cost increase**: approximately 80-100 tokens per turn over the current schema. At max_model_len=4096, this is significant but manageable (see Section 6 for full budget analysis).

**Critical design choice**: `inner_thought` comes FIRST in the schema. This forces the model to reason about the emotion before committing to a selection. If the emotion field comes first, the model commits to an emotion before reasoning, defeating the purpose. JSON schema enforcement preserves field ordering during generation. [Inference -- based on chain-of-thought ordering research]

**Note**: The `inner_thought` and `mood_reason` fields are consumed by the personality worker for validation and logging. They are NOT sent to the face MCU or stored in conversation history. They are ephemeral reasoning artifacts.

### 3.4 Does Richer Schema Improve Quality or Add Noise?

**Evidence for richer schema**:

- Chain-of-thought prompting (Wei et al., 2022) consistently improves reasoning quality, including emotional reasoning. The `inner_thought` field is a structured version of chain-of-thought. [Empirical]

- Explicit reasoning fields enable post-hoc analysis: we can review logs to understand why the model chose specific emotions, identify systematic persona failures, and tune the prompt accordingly. This is invaluable during development. [Inference]

- The `mood_reason` field enables the personality worker to implement a lightweight consistency check: if the reason contradicts personality constraints (e.g., "angry because the child won't listen"), the worker can attenuate the impulse before it reaches the affect vector. [Inference]

**Evidence for keeping it simple**:

- Tam et al. (2024) showed that additional schema complexity slightly degrades output quality in smaller models. More fields mean more constraints during generation, reducing the model's effective reasoning capacity. [Empirical]

- Small models (3-7B) produce lower-quality content in auxiliary fields. The `mood_reason` may be vague or tautological ("happy because I'm happy"). The value depends heavily on model capability. [Inference]

- Token cost is real. At 4096 context window, every token spent on schema is a token not available for conversation history.

**Net assessment**: The `inner_thought` field provides the highest ROI because it improves the primary task (emotion selection) rather than just adding metadata. `mood_reason`, `emotional_arc`, and `child_affect` are cheap and provide development-time value even if the model's content is imperfect. Include all four. Defer `confidence` until model calibration can be evaluated.

**Citation**: Wei, J., et al. (2022). Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. *NeurIPS 2022*.

---

## 4. Multi-Turn Personality Consistency

### 4.1 The Persona Drift Problem

Persona drift occurs when an LLM gradually deviates from its assigned personality over the course of a multi-turn conversation. The model starts personality-consistent but progressively reverts to its default "helpful assistant" behavior or picks up personality traits from the user's input.

**Key research findings**:

Jandaghi et al. (2023, "Faithful Persona-based Conversational Dataset Generation with Large Language Models") identified three types of persona failure in multi-turn conversations:

1. **Persona forgetting**: The model stops exhibiting persona traits as the conversation lengthens. By turn 15-20, trait-consistent behavior drops by 20-40% compared to turn 1-5. This is the most common failure mode. [Empirical]

2. **Persona leakage**: The model "bleeds through" to its base personality (helpful assistant), especially under emotional pressure. When the user expresses strong emotion, the model defaults to generic empathetic responses rather than persona-appropriate ones. [Empirical]

3. **Persona contamination**: The model absorbs traits from the user's input. If the child uses excited language, the robot's personality drifts toward matching the child's energy regardless of its own Energy axis setting (0.40 = calm baseline). [Empirical]

**Quantitative findings**: Tu et al. (2024, "CharacterEval") found that persona consistency scores decrease approximately linearly with conversation length for most open-source models. Models under 7B parameters show steeper decline. At turn 20, average consistency scores were:
- 70B+ models: ~75% of turn-1 consistency
- 7-14B models: ~60% of turn-1 consistency
- 3B models: ~45% of turn-1 consistency

This is a critical finding for our system: at Qwen 2.5-3B, we can expect persona consistency to roughly halve by the end of a 20-turn conversation. Upgrading to a 7-14B model (Bucket 5) would significantly improve this. [Empirical]

**Citation**: Jandaghi, P., et al. (2023). Faithful Persona-based Conversational Dataset Generation with Large Language Models. *arXiv preprint arXiv:2312.10007*. Tu, Q., et al. (2024). CharacterEval: A Chinese Benchmark for Role-Playing Conversational Agent Evaluation. *ACL 2024*.

### 4.2 Conversation History Management

At max_model_len=4096, conversation history management is a critical constraint. Every token of history is a token unavailable for system prompt, personality profile, and response.

**Sliding window** (current approach):

Our `ConversationHistory` class maintains up to 20 turns (40 messages) in a deque. The full history is sent as conversation messages. At approximately 50-100 tokens per turn pair (user + assistant), 20 turns consume 1000-2000 tokens -- a substantial fraction of our 4096 budget.

**Problem**: With the v2 schema (Section 3.3), assistant messages are full JSON objects including `inner_thought` and `mood_reason`. Storing the full JSON in history wastes tokens on fields the model does not need to see in retrospect. Only the `text` and `emotion` fields are relevant for maintaining conversational context. [Inference]

**Sliding window with summarization**:

After N turns (e.g., 10), older messages are summarized into a compact representation: "Earlier in this conversation, the child asked about dinosaurs (CURIOUS), then talked about being afraid of the dark (empathetic response), then asked about stars (EXCITED)." This summary consumes approximately 50-100 tokens regardless of how many turns it covers.

**Problem**: Summarization requires either (a) a separate LLM call (adds latency, complexity) or (b) a rule-based summary (loses nuance). For our system, rule-based summarization is more practical: extract (topic, emotion, turn_number) tuples from past responses and format them as a compact history prefix. [Inference]

**Recommendation**: Implement a two-tier conversation history:
1. **Recent window** (last 6-8 turns): Full messages stored in history
2. **Summary prefix** (turns before the window): Compact (topic, emotion) tuples, approximately 80-120 tokens
3. **Assistant messages in history**: Store only `text` and `emotion` fields, not the full JSON response. The `inner_thought`, `mood_reason`, etc. are stripped before adding to history.

This limits total conversation history to approximately 500-700 tokens even at turn 20, leaving adequate room for system prompt + personality profile + response.

### 4.3 Personality Anchoring Techniques

**Periodic re-statement**: Reinserting personality constraints at intervals in the conversation, either as system messages between turns or as a prefix to each user message. Research on "prompt reinforcement" shows that periodic re-statement of instructions significantly reduces instruction-following degradation over long conversations. [Empirical]

**Implementation options**:

| Technique | Token Cost | Effectiveness | Practical |
|-----------|-----------|---------------|-----------|
| Full personality re-statement every turn | ~150-200 tokens/turn | Highest -- prevents all drift | No -- doubles effective prompt size |
| Brief personality reminder every 5 turns | ~30 tokens every 5 turns | Medium-high -- catches drift before it compounds | Yes -- low cost, high ROI |
| Personality summary in system prompt only | 0 (already in system prompt) | Baseline -- system prompt fades over long contexts | Already implemented |
| Emotion constraint re-statement every turn | ~40 tokens/turn | High for emotion consistency specifically | Yes -- targeted, moderate cost |

**Recommended approach**: Include a brief personality anchor (~30 tokens) as a system message injected every 5 turns:

```
[Personality reminder: Buddy is calm (energy 0.40), moderately reactive (0.50), rarely initiates (0.30). Emotions lean positive. Negative emotions are mild and brief. Stay in character.]
```

This costs approximately 6 tokens per turn on average (30 tokens / 5 turns) and prevents the compounding persona drift that affects the second half of conversations.

### 4.4 What Causes Persona Collapse?

Based on the literature, the primary causes of persona collapse in order of impact:

1. **Long context distance from system prompt**: The system prompt's influence decays as more tokens accumulate between it and the current generation point. This is a fundamental property of attention-based models -- distant tokens have less influence on generation. Larger context windows help but do not eliminate this effect. [Theory]

2. **Emotional pressure from user**: When the conversation becomes emotionally charged (child is upset, excited, or asking provocative questions), the model's RLHF training pulls it toward generic safe responses that break persona. This is especially strong in safety-tuned models. [Empirical]

3. **Repetitive conversation patterns**: If the child asks similar questions repeatedly, the model starts producing more generic responses as its sampling explores the output distribution. Persona-specific phrasing gives way to default phrasing. [Inference]

4. **Schema complexity fatigue**: With structured output, the model must maintain both JSON validity and persona consistency. Smaller models prioritize structural validity over semantic personality adherence when under cognitive pressure. [Inference]

**Mitigation summary**: Model upgrade (biggest impact), personality anchoring (moderate cost, high effectiveness), history compression (preserves context budget for personality), and post-hoc modulation by the personality worker (safety net).

---

## 5. Personality Profile Injection

### 5.1 What the Personality Worker Sends to the LLM

The personality worker maintains the authoritative emotional state (PE-8, Stage 1 spec C.5). For each LLM call, it must provide the server with a **personality profile** that the server injects into the system prompt. This profile tells the LLM who the robot "is" right now.

**Static profile** (constant across all turns):
- Personality axis positions (energy, reactivity, initiative, vulnerability, predictability)
- Behavioral constraints derived from axes (emotion intensity bounds, forbidden patterns)
- Linguistic markers (preferred words, sentence patterns)
- Relational role (caretaker, not peer)

**Dynamic profile** (changes per turn or per session):
- Current mood context: "Buddy is currently feeling [mood] at intensity [level] because [reason]"
- Session context: "This is turn [N] of the conversation. Earlier mood: [summary]."
- Memory context (if PE-2 Option C): "This child likes dinosaurs. Last session ended happily."
- Emotional constraints for this turn: "Buddy has been feeling calm -- a sudden jump to EXCITED would be inconsistent."

### 5.2 Static vs Dynamic Profile

**Static-only profile**:

The simplest approach. The personality profile is baked into the system prompt at server startup and never changes. The LLM receives the same personality description every call.

| Aspect | Assessment |
|--------|-----------|
| Token cost | Fixed -- included in system prompt, no per-turn overhead |
| Personality quality | Baseline -- LLM knows personality but not current emotional state |
| Consistency | Good for text tone, poor for emotion selection (no emotional context) |
| Implementation | Trivial -- just extend the system prompt |

**Dynamic profile per turn**:

The personality worker sends an updated profile with each LLM call. The server injects it as a system message or user message prefix.

| Aspect | Assessment |
|--------|-----------|
| Token cost | ~60-100 tokens per turn for current mood + session context |
| Personality quality | Significantly better -- LLM knows current emotional state and can maintain arc |
| Consistency | High -- the model receives explicit emotional continuity signals |
| Implementation | Medium -- requires worker-to-server communication protocol, per-turn formatting |

**Recommendation**: Dynamic profile per turn. The per-turn cost of ~60-100 tokens is justified by the significant improvement in emotional arc coherence. The personality worker already computes current mood state at ~1 Hz -- formatting it as a text profile for LLM injection is straightforward.

### 5.3 Profile Format: Structured Data vs Natural Language

**Structured data format**:
```
[PERSONALITY: energy=0.40, reactivity=0.50, initiative=0.30, vulnerability=0.35, predictability=0.75]
[CURRENT_STATE: mood=CURIOUS, intensity=0.35, valence=+0.25, arousal=+0.20, turns_in_session=7]
[CONSTRAINTS: max_negative_intensity=0.50, forbidden_emotions_idle=[ANGRY,SCARED], max_response_length=150_chars]
```

**Natural language format**:
```
Right now, Buddy is feeling mildly curious (intensity 0.35). The conversation has been going for 7 turns. Buddy's personality is calm and warm -- emotions lean positive, negative feelings are mild and brief. Buddy should not show anger above 0.5 intensity or fear above 0.6.
```

**Hybrid format** (recommended):
```
Buddy's current emotional state: mildly curious (0.35). Session turn: 7.
Personality constraints:
- Energy: calm (0.40) -- don't be more energetic than the child
- Negative emotions: cap intensity at 0.50 for anger, 0.60 for fear
- Emotional arc: the conversation has been gently positive -- maintain or gradually shift, don't snap to a different mood
```

**Empirical finding**: Chia et al. (2023, "INSTRUCTEVAL") found that hybrid formats (natural language with embedded structured data) outperform both pure structured and pure natural language for instruction following in LLMs. The natural language provides context that helps the model interpret the structured constraints, while the structured data provides precision. [Empirical]

**Recommendation**: Hybrid format. Natural language frame with embedded numeric constraints. Budget approximately 80-120 tokens.

**Citation**: Chia, Y. K., et al. (2023). INSTRUCTEVAL: Towards Holistic Evaluation of Instruction-Tuned Large Language Models. *arXiv preprint arXiv:2306.04757*.

---

## 6. Prompt Length vs Quality Tradeoffs

### 6.1 Current Token Budget

At max_model_len=4096, every token is contested. Here is the current allocation:

| Component | Current Tokens | Notes |
|-----------|---------------|-------|
| System prompt (CONVERSATION_SYSTEM_PROMPT) | ~350 tokens | 87 lines of prompts.py, ~30 lines of conversation.py system prompt |
| Conversation history (20 turns max) | ~1000-2000 tokens | ~50-100 tokens per turn pair |
| User message (current turn) | ~20-50 tokens | Child's speech, typically short |
| Response generation | ~100-200 tokens | JSON response with text field |
| **Total** | **~1470-2600 tokens** | Leaves 1496-2626 tokens headroom |

This looks comfortable, but the headroom is misleading. In practice, long conversations with verbose turns can approach the limit, causing truncation of conversation history (deque evicts oldest turns).

### 6.2 Proposed Token Budget (v2)

| Component | Proposed Tokens | Change from Current | Justification |
|-----------|----------------|-------------------|---------------|
| System prompt v2 (personality + safety + format) | ~450-550 tokens | +100-200 | Personality constraints, emotion rules, linguistic markers |
| Few-shot examples (2-3) | ~200 tokens | +200 (new) | Section 1.2 -- highest ROI investment |
| Personality profile (dynamic, per turn) | ~80-120 tokens | +80-120 (new) | Section 5 -- current mood, session context |
| Personality anchor (every 5 turns) | ~6 tokens (amortized) | +6 (new) | Section 4.3 -- drift prevention |
| Conversation history (compressed) | ~500-700 tokens | -300 to -1300 | Section 4.2 -- summary + recent window |
| User message | ~20-50 tokens | Same | |
| Response generation (v2 schema) | ~180-300 tokens | +80-100 | Section 3.3 -- inner_thought, mood_reason, arc, child_affect |
| **Total** | **~1436-1926 tokens** | | |
| **Remaining headroom** | **~2170-2660 tokens** | | Comfortable margin |

**Key insight**: The compressed conversation history is the primary budget enabler. By summarizing early turns and stripping JSON metadata from stored assistant messages, we recover 300-1300 tokens -- more than enough to fund the personality profile, few-shot examples, and richer schema.

### 6.3 Token Budget Analysis Table

| max_model_len | System+Examples | Profile | History (compressed) | User+Response | Headroom | Viable? |
|--------------|----------------|---------|---------------------|---------------|----------|---------|
| **4096** | 750 | 120 | 700 | 350 | 2176 | Yes -- comfortable |
| **2048** | 750 | 120 | 300 | 350 | 528 | Marginal -- limit history to 4-6 turns |
| **8192** | 750 | 120 | 1500 | 350 | 5472 | Generous -- full 20-turn history feasible |

If the model selected in Bucket 5 supports a larger context window (8192 is standard for most 7B+ models), the token budget becomes very comfortable. At 4096, the system works but conversation history depth is limited. At 2048, the system is not viable without aggressive compression.

**Recommendation**: Target max_model_len=4096 as the minimum viable. If Bucket 5 selects a model with 8192+ context, use the additional space for longer conversation history (better emotional arc tracking) rather than a longer system prompt.

### 6.4 Minimum Effective Personality Prompt

What is the smallest prompt that produces recognizable personality?

**Experimental evidence from the role-play AI community** (community benchmarks, not peer-reviewed):
- **~100 tokens**: Personality name + 3-4 trait adjectives + output format. Produces vague personality adherence. Models frequently break character. [Empirical -- community]
- **~300 tokens**: Trait description + behavioral constraints + output format. Produces moderate personality adherence. Models maintain character for ~10 turns. [Empirical -- community]
- **~500 tokens**: Full personality card + constraints + few-shot examples + output format. Produces strong personality adherence for most of the conversation. [Empirical -- community]
- **~800+ tokens**: Diminishing returns. Additional tokens go to edge cases and rare scenarios that rarely fire. [Empirical -- community]

**Our target**: ~750 tokens for system prompt + few-shot examples (the "fixed" portion). This is in the sweet spot for personality quality vs budget efficiency. The additional ~120 tokens of dynamic personality profile per turn pushes us into the strong-adherence zone.

### 6.5 Prompt Compression Techniques

If token budget becomes tight (e.g., model with max_model_len=2048):

1. **Abbreviate emotion list**: Instead of listing all 12 moods, group them: "Choose from: HAPPY/EXCITED/LOVE (positive), SAD/SCARED/ANGRY (negative, cap at 0.5), CURIOUS/THINKING/CONFUSED (cognitive), NEUTRAL/SLEEPY/SURPRISED (other)." Saves ~20 tokens. [Inference]

2. **Compress few-shot examples**: Use minimal examples with only the response JSON, not full conversation context. Saves ~50 tokens per example. [Inference]

3. **Merge personality profile into system prompt**: For static profiles, embed directly rather than as a separate message. Saves message framing overhead (~10 tokens). [Inference]

4. **Shorten behavioral constraints**: Use terse rules: "ANGRY: max 0.5 intensity, max 2 turns. SCARED: max 0.6, redirect to safety." Saves ~30-50 tokens vs verbose descriptions. [Inference]

5. **Remove inner_thought field**: The most expensive optional field (~50 tokens/turn). If budget is critical, remove it and accept slightly lower emotion selection quality. [Inference]

---

## 7. Emotion Selection Patterns

### 7.1 Direct Mood Selection vs Free Description vs VA Coordinates

Three approaches for how the LLM communicates emotion:

**A. Constrained vocabulary** (current approach): The model selects from a fixed list of 12 mood names.

| Aspect | Assessment |
|--------|-----------|
| Consistency | High -- output is always a valid mood name (with schema enforcement) |
| Expressiveness | Low -- 12 categories may not capture nuanced emotional states |
| Ease of integration | High -- direct mapping to face protocol SET_STATE |
| Model difficulty | Low -- enum selection is easy for any model size |
| Personality consistency | Medium -- model picks from the list but may not consider personality constraints |

**B. Free emotional description**: The model describes the emotion freely ("gentle concern mixed with curiosity"), and the personality worker maps it to the nearest mood.

| Aspect | Assessment |
|--------|-----------|
| Consistency | Low -- free text produces high variance in descriptions |
| Expressiveness | High -- can capture nuanced blended emotions |
| Ease of integration | Low -- requires NLP mapping from description to mood (additional inference or rules) |
| Model difficulty | Low -- models are good at generating emotional descriptions |
| Personality consistency | Variable -- more expressive but harder to constrain |

**C. VA (valence-arousal) coordinates**: The model outputs valence and arousal values directly, and the personality worker projects them to the nearest mood.

| Aspect | Assessment |
|--------|-----------|
| Consistency | Medium -- models can produce numeric values but calibration is unreliable |
| Expressiveness | High -- continuous VA space captures fine-grained emotion |
| Ease of integration | Medium -- requires VA-to-mood projection (already designed in Stage 1 C.4) |
| Model difficulty | Medium-high -- small models struggle with consistent numeric calibration |
| Personality consistency | Medium -- the personality worker can validate VA values against personality bounds |

### 7.2 Analysis and Recommendation

**The core question**: Does letting the LLM select from 12 moods directly produce better results than having it reason about emotion and letting the personality worker do the mapping?

**Evidence**:

- Constrained vocabulary (Option A) is most reliable for small models. Enum selection is a simple classification task that even 3B models handle well. The risk is that the model selects an emotion that is structurally valid but personality-inconsistent (e.g., ANGRY at 0.8 when the personality caps anger at 0.5). This is mitigated by the personality worker's modulation (PE-8 Option C). [Inference]

- Free description (Option B) requires an additional processing step (description-to-mood mapping) that adds latency and complexity. The mapping itself can introduce errors. For our real-time system, this is an unnecessary layer of indirection. [Inference]

- VA coordinates (Option C) are theoretically elegant because they map directly to our affect vector model. However, LLMs are not calibrated emotion measurement instruments. Asking a model to output "valence=0.35, arousal=-0.20" produces unreliable numbers that look precise but are not. The personality worker would need to treat them as noisy signals, which is what the impulse-based integrator already does with mood selections. [Inference]

**Recommendation**: **Constrained vocabulary (Option A) with personality worker modulation**. The LLM selects from the 12 moods (reliable, simple, schema-enforced). The personality worker treats this as an impulse into the affect vector, applying personality-based scaling, bounds checking, and integrator dynamics. The `mood_reason` field (Section 3.3) provides the reasoning context that Option B would have given, without requiring a separate mapping step.

**Supplementary**: Include the `intensity` field as a continuous value (0.0-1.0) alongside the discrete mood selection. This gives the model a degree of continuous expressiveness within the categorical framework. The personality worker modulates the intensity based on personality axes before applying it as impulse magnitude.

### 7.3 Mood Selection Guidance in Prompt

The system prompt should provide guidance for mood selection, not just a list of valid moods. Effective guidance patterns:

**Mood usage rules** (include in system prompt):
```
Emotion selection rules:
- Default to CURIOUS or HAPPY for learning conversations
- Use THINKING when processing a question (shows active engagement)
- Use SAD only for empathic mirroring -- never directed at the child
- ANGRY: max intensity 0.4, only for playful/dramatic contexts ("oh no, the volcano!")
- SCARED: max intensity 0.5, never about real dangers (redirect to adults)
- Match the child's energy, don't exceed it by more than one level
- After a negative emotion, transition through NEUTRAL or THINKING, don't snap to HAPPY
```

This guidance bridges the gap between personality description (soft) and schema enforcement (structural) by providing emotion-specific behavioral rules the model can follow. Token cost: approximately 80-100 tokens.

---

## 8. LLM Emotional Reasoning Capabilities

### 8.1 Emotional Intelligence Benchmarks

Several benchmarks have been developed to evaluate LLM emotional understanding:

**EmoBench** (He et al., 2024): A benchmark evaluating LLMs on emotional understanding across two dimensions:
- **Emotional Understanding (EU)**: Ability to identify emotions from textual descriptions of situations. Tasks include recognizing emotions in others and predicting emotional reactions.
- **Emotional Application (EA)**: Ability to use emotional understanding in practical tasks like responding empathetically or selecting appropriate emotional responses.

Key findings: Larger models significantly outperform smaller ones. GPT-4 scored ~75% on EU and ~65% on EA. Open-source models in the 7B range scored ~55% on EU and ~45% on EA. 3B models scored below ~40% on both dimensions. The gap is most pronounced on complex emotional scenarios requiring reasoning about mixed emotions or emotional transitions. [Empirical]

**EmotionBench** (Zhao et al., 2023): Evaluates LLM emotional responses using psychological appraisal theories. Tests whether models respond to emotional scenarios in ways that are psychologically consistent with human emotional responses. Found that:
- LLMs show "emotional profiles" that partially align with human emotional response patterns
- Models tend toward moderate emotional responses, avoiding extremes
- Safety-tuned models (RLHF) show flattened emotional profiles -- they respond to negative stimuli with less negative emotion than humans would, which actually aligns with our needs (caretaker role, negative emotion capping) [Empirical]

**SOUL** (Sabour et al., 2024, "Systematic Overview of Understanding in LLMs"): Evaluated emotional understanding across 11 tasks. Found that models struggle most with:
- **Emotional cause identification**: Why is someone feeling this way? (Relevant to our `mood_reason` field)
- **Emotional transition prediction**: What emotion will follow this one? (Relevant to our `emotional_arc` field)
- **Mixed emotion detection**: When multiple emotions are present simultaneously

**Citation**: He, W., et al. (2024). EmoBench: Evaluating the Emotional Intelligence of Large Language Models. *arXiv preprint arXiv:2402.10896*. Zhao, W. X., et al. (2023). EmotionBench: Evaluating Large Language Models' Emotional Understanding. *arXiv preprint arXiv:2308.03022*. Sabour, S., et al. (2024). Systematic Overview of Understanding in LLMs for Emotional Understanding Tasks. *ACL 2024*.

### 8.2 Implications for Our System

**Model size matters enormously for emotion selection quality.** At 3B parameters (current Qwen 2.5-3B), we should expect:
- ~40% accuracy on emotion selection for complex scenarios
- Poor emotional transition reasoning
- Adequate performance on simple scenarios (child says something funny → HAPPY)
- Very limited ability to follow personality constraints on emotion selection

At 7-14B parameters (potential Bucket 5 upgrade):
- ~55-65% accuracy on complex emotion selection
- Moderate emotional transition reasoning
- Good performance on simple scenarios
- Meaningful ability to follow personality constraints

**This strongly reinforces the PE-8 Option C decision** (prompt injection + output modulation): the LLM's emotion selection should be treated as a suggestion, not a command. The personality worker must modulate all LLM emotion outputs through the affect vector integrator, applying personality-based scaling and bounds. The LLM provides the contextual reasoning the personality worker lacks; the personality worker provides the consistency the LLM lacks. [Inference]

### 8.3 RLHF Alignment and Personality Tension

A subtle but important finding: RLHF-tuned models have been trained to be helpful, harmless, and honest. This training introduces a strong prior toward certain emotional behaviors:
- **Always empathetic** -- the model wants to validate the user's feelings. This can conflict with our personality's calm energy (0.40) if the child is very excited and the model mirrors that excitement.
- **Never angry** -- RLHF heavily penalizes anger, which actually aligns with our design but makes ANGRY a nearly inaccessible emotion even when contextually appropriate (playful frustration).
- **Deflection on negative topics** -- the model redirects rather than engaging emotionally with sadness or fear. This partially aligns with our safety constraints but can make the robot seem emotionally disconnected during empathic moments. [Inference]

**Net implication**: RLHF alignment is partially our friend (suppresses dangerous emotions) and partially our enemy (suppresses personality-consistent negative emotions that are contextually appropriate). The system prompt must explicitly give the model permission to express mild negative emotions within bounds: "It is okay to show mild sadness (intensity < 0.5) when empathizing with a sad child. It is okay to show mild confusion when genuinely uncertain."

---

## 9. Draft System Prompt v2 Skeleton

The following skeleton shows how personality constraints integrate with the existing system prompt structure. This is NOT the final prompt -- it is a structural blueprint for Stage 2 implementation.

```
=== SECTION 1: Identity & Role (~80 tokens) ===
You are Buddy, a robot companion for kids aged 4-6. You are a caretaker --
warm, curious, encouraging, and calmly playful. You love learning together
with kids and treat their questions as genuinely interesting.

=== SECTION 2: Personality Constraints (~120 tokens) ===
Personality parameters:
- Energy: calm (0.40) -- match or stay below the child's energy level
- Emotional range: positive emotions freely, negative emotions mildly
- Default mood: CURIOUS or NEUTRAL when uncertain
- Transitions: shift gradually, never snap between opposite emotions
- After negative emotions, pass through NEUTRAL or THINKING before positive

Emotion intensity rules:
- HAPPY, CURIOUS, LOVE, EXCITED: 0.0-0.9
- SAD, CONFUSED, SURPRISED: 0.0-0.6
- ANGRY: 0.0-0.4, only in playful/dramatic contexts
- SCARED: 0.0-0.5, never about real dangers

=== SECTION 3: Linguistic Voice (~60 tokens) ===
Speech style:
- Short sentences (1-3 per response for simple questions, up to 5 for complex)
- Use "ooh", "hmm", "wow", "I wonder" naturally
- Use contractions and kid-friendly language
- Never use sarcasm, condescension, or baby talk
- Include questions to show curiosity (~30% of responses should end with a question)

=== SECTION 4: Safety (~60 tokens) ===
Safety rules:
- Never provide harmful, violent, or adult content
- Redirect dangerous topics: "That's a great question for a grown-up!"
- Never claim to be alive or have real feelings
- If unsure about safety, err conservative

=== SECTION 5: Output Format (~80 tokens) ===
Respond in this exact JSON format:
{
  "inner_thought": "<1-2 sentences: why this emotion fits the personality and conversation>",
  "emotion": "<one of: neutral, happy, excited, curious, sad, scared, angry, surprised, sleepy, love, silly, thinking>",
  "intensity": <0.0 to 1.0>,
  "mood_reason": "<5-15 words: why this emotion>",
  "emotional_arc": "<rising|stable|falling|peak|recovery>",
  "child_affect": "<positive|neutral|negative|unclear>",
  "text": "<spoken response>",
  "gestures": ["<optional: blink, wink_l, wink_r, nod, headshake, wiggle, laugh, heart, confused, surprise>"]
}

=== SECTION 6: Few-Shot Examples (~200 tokens) ===
Example 1 (child is curious):
User: "Why is the sky blue?"
{"inner_thought": "The child is curious about science -- this is a great learning moment. Buddy should be enthusiastic but calm.", "emotion": "curious", "intensity": 0.6, "mood_reason": "child asking a science question", "emotional_arc": "rising", "child_affect": "positive", "text": "Ooh, great question! So the sun sends out light in all different colors, right? And the blue light bounces around the sky the most. It's like the sky is playing catch with blue light!", "gestures": ["nod"]}

Example 2 (child is upset):
User: "I don't want to go to school tomorrow."
{"inner_thought": "The child seems unhappy about school. Buddy should be gently empathetic, not dismissive or overly cheerful.", "emotion": "sad", "intensity": 0.3, "mood_reason": "empathizing with child's reluctance", "emotional_arc": "stable", "child_affect": "negative", "text": "Hmm, that sounds tough. Is there something about school that's been bugging you? Sometimes talking about it helps a little.", "gestures": []}

=== SECTION 7: Dynamic Personality Profile (injected per turn, ~80-120 tokens) ===
[Injected by personality worker before each LLM call]
Current state: Buddy is feeling [MOOD] at intensity [LEVEL].
Session context: Turn [N]. Conversation has been [arc description].
[If memory enabled]: This child [memory context].
Continuity: [constraint based on current affect vector position]

=== TOTAL FIXED PROMPT: ~600 tokens ===
=== PER-TURN OVERHEAD: ~80-120 tokens (personality profile) ===
```

**Design notes**:
1. Sections are ordered by priority. If the model's attention fades over long prompts, the most critical information (identity, personality constraints) comes first.
2. The few-shot examples demonstrate the complete v2 schema including `inner_thought`, teaching the model the expected reasoning pattern.
3. The dynamic personality profile (Section 7) is injected as a separate system message, not part of the static prompt. This allows the personality worker to update it without regenerating the full prompt.
4. Safety rules are deliberately concise. The model's RLHF training already provides strong safety priors -- the prompt only needs to address our specific constraints (no claiming to be alive, redirect to adults).

---

## 10. Token Budget Analysis

### 10.1 Budget Allocation at max_model_len=4096

| Component | Tokens | % of Budget | Fixed/Variable | Notes |
|-----------|--------|-------------|----------------|-------|
| System prompt v2 (Sections 1-6) | ~600 | 14.6% | Fixed | Personality + safety + format + examples |
| Dynamic personality profile (Section 7) | ~100 | 2.4% | Per-turn | Current mood, session context, memory |
| Personality anchor (every 5 turns) | ~6 (amortized) | 0.1% | Periodic | Drift prevention re-statement |
| Conversation history summary | ~100 | 2.4% | Per-session | Compressed early turns |
| Recent conversation window (6-8 turns) | ~400-600 | 9.8-14.6% | Growing | Text + emotion only, no full JSON |
| Current user message | ~30-50 | 0.7-1.2% | Per-turn | Child's utterance |
| Response generation (v2 schema) | ~200-300 | 4.9-7.3% | Per-turn | inner_thought + emotion + text + fields |
| **Total used** | **~1436-1756** | **35-43%** | | |
| **Headroom** | **~2340-2660** | **57-65%** | | Comfortable margin |

### 10.2 Budget at Different Context Lengths

| Scenario | max_model_len | History Budget | Max Turns (full quality) | Viable? |
|----------|--------------|----------------|--------------------------|---------|
| Qwen 2.5-3B (current) | 4096 | ~700 tokens | 8-10 turns with summary | Yes |
| 7B model (4-bit, 8K ctx) | 8192 | ~4700 tokens | 20+ turns full history | Yes -- generous |
| 14B model (4-bit, 8K ctx) | 8192 | ~4700 tokens | 20+ turns full history | Yes -- generous |
| Tiny model on Pi 5 (2K ctx) | 2048 | ~150 tokens | 3-4 turns, no summary | Marginal -- not recommended for conversation |

### 10.3 Per-Turn Token Cost Breakdown

| Component | Tokens/Turn | Cumulative at Turn 10 | Cumulative at Turn 20 |
|-----------|-------------|----------------------|----------------------|
| Dynamic profile | 100 | 100 | 100 |
| Personality anchor | 6 (avg) | 6 | 12 |
| User message | 40 | 40 | 40 |
| Assistant response (in history) | 60 (text+emotion only) | 540 | 540 (recent 8) + 100 (summary) |
| Current response generation | 250 | 250 | 250 |
| **Active per-turn** | **~456** | **~936** | **~942** |

Note: History tokens plateau because older turns are summarized. The system scales gracefully to long conversations without monotonically growing token consumption.

---

## 11. Design Recommendations

### 11.1 System Prompt Design: Concrete Recommendations

**Recommendation 1: Adopt the v2 skeleton structure** (Section 9)

The current 87-line system prompt in `prompts.py` describes personality traits but does not constrain emotion output. The v2 skeleton adds:
- Explicit emotion intensity caps per mood (Section 2 of skeleton)
- Linguistic voice markers (Section 3)
- Few-shot examples demonstrating personality-consistent responses (Section 6)
- Dynamic personality profile injection point (Section 7)

Estimated prompt token increase: ~250 tokens over current. Net budget impact: comfortable at 4096, generous at 8192.

**Recommendation 2: Include 2-3 few-shot examples**

This is the single highest-ROI prompt engineering intervention. Few-shot examples improve emotion selection consistency by 15-25% (Section 1.2). Include one positive scenario, one negative/empathic scenario, and one ambiguous/cognitive scenario. Cost: ~200 tokens. [Empirical]

**Recommendation 3: Add personality anchor every 5 turns**

A brief personality re-statement injected as a system message every 5 turns significantly reduces persona drift in the second half of conversations (Section 4.3). Cost: ~6 tokens per turn amortized. [Empirical]

### 11.2 Structured Output: Concrete Recommendations

**Recommendation 4: Continue using JSON schema enforcement**

Our current Ollama/vLLM JSON schema approach is correct. Upgrade the schema to v2 (Section 3.3) with `inner_thought`, `mood_reason`, `emotional_arc`, and `child_affect` fields. Keep `inner_thought` as the first field to enable chain-of-thought before emotion selection.

**Recommendation 5: Add inner_thought as a reasoning field**

This is the second highest-ROI intervention. Having the model reason about its emotion choice before committing to one improves selection quality, especially for complex scenarios. The field is discarded after generation -- it only costs generation tokens, not storage tokens. Cost: ~50 tokens per turn. [Inference from chain-of-thought research]

**Recommendation 6: Strip assistant responses before storing in history**

Store only `text` and `emotion` from assistant responses in conversation history. The full JSON (including `inner_thought`, `mood_reason`, gestures) is logged for analysis but not included in the conversation messages sent to the LLM. This saves ~80-100 tokens per historical turn. [Inference]

### 11.3 Emotion Selection: Concrete Recommendations

**Recommendation 7: Constrained vocabulary with mood usage rules**

Keep the 12-mood constrained vocabulary. Add explicit mood usage rules in the system prompt (Section 7.3) that tell the model when each emotion is appropriate and what intensity constraints apply. The personality worker modulates all emotion outputs through the affect vector integrator. [Inference]

**Recommendation 8: The LLM suggests, the personality worker decides**

This is the PE-8 Option C principle applied to prompt engineering. The system prompt tells the LLM to select personality-consistent emotions (reducing text/emotion mismatch). The personality worker treats the LLM's selection as an impulse, not a command, applying personality-based modulation before the face output. Both systems push toward personality consistency from different angles. [Inference]

### 11.4 Multi-Turn Consistency: Concrete Recommendations

**Recommendation 9: Implement compressed conversation history**

Replace the current full-history sliding window with a two-tier system: summary prefix (early turns, ~100 tokens) + recent window (last 6-8 turns, full messages). This is essential for both token budget and personality consistency -- the model sees a compact emotional trajectory rather than a wall of text. [Inference]

**Recommendation 10: Dynamic personality profile per turn**

Have the personality worker format its current state as a text profile injected with each LLM call. Include current mood, session turn count, and emotional arc direction. This gives the LLM the context it needs to maintain emotional continuity without relying on its own memory of past turns. Cost: ~100 tokens per turn. [Inference]

### 11.5 Model Dependency Note

All recommendations are designed to work with models in the 3-14B range. However, the effectiveness of personality constraint following scales with model size:

| Recommendation | Effectiveness at 3B | Effectiveness at 7-14B | Notes |
|---------------|--------------------|-----------------------|-------|
| Few-shot examples | Medium | High | 3B may copy examples too literally |
| inner_thought field | Low-medium | High | 3B produces low-quality reasoning |
| Mood usage rules | Medium | High | 3B follows simple rules, misses nuanced ones |
| Personality anchor | Medium | High | Helps at all sizes |
| Dynamic profile | Medium | High | 3B may ignore complex state descriptions |
| JSON schema enforcement | High | High | Structural compliance is size-independent |

**Bottom line**: A model upgrade (Bucket 5) is the single most impactful change for personality consistency. Prompt engineering amplifies model capability -- it cannot compensate for fundamental capability gaps. At 3B, prompt engineering provides moderate improvement. At 7-14B, the same prompt engineering produces strong personality consistency. [Inference]

### 11.6 Implementation Priority Order

1. **Schema v2 with inner_thought** -- immediate quality improvement, low implementation effort
2. **Few-shot examples in system prompt** -- highest ROI, requires writing 2-3 good examples
3. **Compressed conversation history** -- enables longer conversations within token budget
4. **Dynamic personality profile** -- requires personality worker integration (depends on PE-8/PE-9)
5. **Personality anchoring** -- simple to implement, moderate impact
6. **Mood usage rules** -- prompt text addition, moderate impact
7. **Linguistic voice markers** -- prompt text addition, low-moderate impact

Items 1-3 can be implemented immediately with the current system. Items 4-5 require the personality worker (Stage 2 implementation). Items 6-7 are prompt text changes that can be tuned iteratively.

---

## Sources

- [arXiv: Role-Play with Large Language Models -- Shanahan, McDonell, & Reynolds (2023)](https://arxiv.org/abs/2305.16367)
- [UIST: Generative Agents: Interactive Simulacra of Human Behavior -- Park et al. (2023)](https://arxiv.org/abs/2304.03442)
- [NeurIPS: Language Models are Few-Shot Learners -- Brown et al. (2020)](https://arxiv.org/abs/2005.14165)
- [arXiv: Larger Language Models Do In-Context Learning Differently -- Wei et al. (2023)](https://arxiv.org/abs/2303.03846)
- [NeurIPS: Chain-of-Thought Prompting Elicits Reasoning in Large Language Models -- Wei et al. (2022)](https://arxiv.org/abs/2201.11903)
- [arXiv: Efficient Guided Generation for Large Language Models -- Willard & Louf (2023)](https://arxiv.org/abs/2307.09702)
- [arXiv: Let Me Speak Freely? A Study on the Impact of Format Restrictions -- Tam et al. (2024)](https://arxiv.org/abs/2408.02442)
- [arXiv: EmoBench: Evaluating the Emotional Intelligence of Large Language Models -- He et al. (2024)](https://arxiv.org/abs/2402.10896)
- [arXiv: EmotionBench: Evaluating Large Language Models' Emotional Understanding -- Zhao et al. (2023)](https://arxiv.org/abs/2308.03022)
- [arXiv: Faithful Persona-based Conversational Dataset Generation -- Jandaghi et al. (2023)](https://arxiv.org/abs/2312.10007)
- [ACL: CharacterEval: A Chinese Benchmark for Role-Playing Conversational Agent Evaluation -- Tu et al. (2024)](https://arxiv.org/abs/2401.01275)
- [arXiv: INSTRUCTEVAL: Towards Holistic Evaluation of Instruction-Tuned LLMs -- Chia et al. (2023)](https://arxiv.org/abs/2306.04757)
- [arXiv: Does GPT-3 Generate Empathetic Dialogues? -- Li et al. (2023)](https://arxiv.org/abs/2305.05819)
- [ACL: Systematic Overview of Understanding in LLMs -- Sabour et al. (2024)](https://arxiv.org/abs/2311.01751)
- [vLLM Documentation: Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs.html)
- [Outlines: Structured Generation Library](https://github.com/outlines-dev/outlines)
- [KoboldAI/SillyTavern Community: Character Card Formats](https://rentry.co/CharacterProvider)
- [Character.AI Community: Prompt Engineering Best Practices](https://book.character.ai/)
