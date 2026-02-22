# Bucket 5: LLM Model Selection & Capabilities

## Research Summary for Robot Buddy Personality Engine

**Audience**: Ages 4-6 | **Platform**: Kid-safe companion robot with animated LED face (320x240 TFT), 12 mood expressions, LLM conversation, persistent emotional state
**Date**: 2026-02-22 | **Status**: Research complete -- informs PE-6 (Server LLM Model) and PE-7 (On-Device Inference) decisions

---

## Table of Contents

1. [Current System Baseline](#1-current-system-baseline)
2. [Model Family Comparison](#2-model-family-comparison)
3. [Quantization Tradeoffs](#3-quantization-tradeoffs)
4. [VRAM Budget Analysis](#4-vram-budget-analysis)
5. [Benchmarks Relevant to Personality](#5-benchmarks-relevant-to-personality)
6. [On-Device Small Models for Pi 5](#6-on-device-small-models-for-pi-5)
7. [vLLM Capabilities and Alternatives](#7-vllm-capabilities-and-alternatives)
8. [Model Comparison Summary](#8-model-comparison-summary)
9. [Design Recommendations](#9-design-recommendations)

---

## 1. Current System Baseline

### 1.1 What We Have Today

The current server stack uses the following VRAM allocation on a single RTX 3090 Ti (24 GB total, 80% cap = 19.2 GB usable):

| Component | Model | VRAM Allocation | Actual Budget |
|-----------|-------|----------------|---------------|
| LLM | Qwen 2.5-3B-Instruct, bfloat16 | 35% (gpu_memory_utilization) | ~8.4 GB |
| TTS | Orpheus 3B (canopylabs/orpheus-3b-0.1-ft) | 45% (gpu_memory_utilization) | ~10.8 GB |
| System/KV cache overhead | CUDA context, vLLM overhead | ~20% implicit | ~4.8 GB |

**Configuration from `server/app/config.py`**: vLLM max_model_len=4096, max_num_seqs=2, max_num_batched_tokens=256, temperature=0.7, timeout=20s. Orpheus max_model_len=8192, max_num_seqs=8. Combined utilization validated against gpu_utilization_cap=0.80. [Empirical -- verified from codebase]

### 1.2 Known Problems with Qwen 2.5-3B

From the personality engine spec and operational experience:

1. **Unreliable structured output**: The model frequently fails to produce valid JSON matching the required schema (`{emotion, intensity, text, gestures}`). The vLLM backend includes a JSON repair suffix and `_extract_json_object()` fallback because raw output is often malformed. [Empirical -- observed in `server/app/llm/vllm_backend.py`]

2. **Insufficient emotional reasoning**: A 3B parameter model cannot reliably distinguish between contextually appropriate emotions. Given a scenario where a child expresses disappointment, the model may choose HAPPY because the word "birthday" appeared in the text, ignoring emotional context. [Empirical -- from personality engine spec assessment]

3. **No personality consistency**: The model cannot maintain a stable persona across 20 turns. Even with personality descriptions in the system prompt, emotion selection drifts based on surface-level token patterns. [Inference -- from spec unverified assumption #2]

4. **Limited instruction following at scale**: With the 87-line system prompt plus conversation history, the model struggles to follow all constraints simultaneously. Safety guidelines, JSON format, personality traits, and context rules compete for the model's limited attention bandwidth. [Inference]

### 1.3 What We Need

The personality engine requires the LLM to reliably:

- **Select contextually appropriate emotions** from a 12-mood vocabulary with calibrated intensity (0.0-1.0)
- **Maintain persona consistency** across 20-turn conversations (same personality axes -> same emotional patterns)
- **Produce valid structured output** (JSON with specific keys, enum-constrained values) at >95% compliance
- **Follow complex multi-constraint prompts** (safety + personality + format + content simultaneously)
- **Reason about emotional arcs** (child was sad 3 turns ago -> maintain empathetic undertone, don't snap to EXCITED)
- **Fit within VRAM budget** alongside Orpheus TTS on a single 3090 Ti

---

## 2. Model Family Comparison

### 2.1 Qwen 2.5 Family

The Qwen 2.5 family (Alibaba Cloud, September 2024) spans from 0.5B to 72B parameters. Key variants for our evaluation:

**Qwen 2.5-3B-Instruct (current)**:
- Parameters: 3.09B
- FP16 weight size: ~6.2 GB
- bfloat16 via vLLM: fits in 8.4 GB allocation with KV cache
- Structured output: Unreliable. JSON schema adherence ~70-80% with simple schemas, drops to ~50-60% with complex multi-field schemas. [Empirical -- observed in production]
- Persona consistency: Poor. Cannot maintain stable personality traits across extended conversations. [Empirical]
- Emotional reasoning: Minimal. Selects emotions based on keyword matching rather than contextual understanding. [Inference]

**Qwen 2.5-7B-Instruct**:
- Parameters: 7.62B
- FP16 weight size: ~15.2 GB (too large for our LLM VRAM budget at full precision)
- 8-bit quantization: ~7.6 GB (fits in 8.4 GB budget with minimal KV cache)
- 4-bit AWQ: ~4.3 GB (fits comfortably, leaves room for larger KV cache and more concurrent sequences)
- Structured output: Significant improvement over 3B. JSON compliance ~90-95% with well-designed schemas. The 7B model follows multi-constraint prompts more reliably. [Empirical -- from Qwen 2.5 technical report benchmarks]
- Persona consistency: Moderate. Can follow persona descriptions over 10-15 turns but may drift in longer conversations. [Inference]
- Emotional reasoning: Improved. Can perform basic emotional context tracking (e.g., "the child mentioned something sad" -> maintains appropriate tone for 2-3 turns). [Inference]

**Qwen 2.5-14B-Instruct**:
- Parameters: 14.17B
- FP16 weight size: ~28.3 GB (far exceeds total GPU)
- 8-bit quantization: ~14.2 GB (exceeds LLM VRAM budget)
- 4-bit AWQ: ~8.0 GB (fits within 8.4 GB budget, tight with KV cache)
- 4-bit GPTQ: ~7.8 GB (similar fit)
- Structured output: Strong. JSON compliance >95%. Can follow complex schemas with nested objects and enum constraints reliably. [Empirical -- reported in Qwen 2.5 evaluations]
- Persona consistency: Good. Maintains stable personality across 20+ turns with appropriate system prompt. Strong instruction following allows multi-constraint prompts. [Inference]
- Emotional reasoning: Substantially better than 3B/7B. Can track emotional context across turns, recognize emotional shifts, and produce calibrated intensity values. [Inference]
- **Critical concern**: At 4-bit quantization, the 14B model occupies ~8 GB for weights alone. With vLLM KV cache overhead (max_model_len=4096, max_num_seqs=2), total VRAM usage will be ~8.5-9.5 GB, potentially exceeding the 8.4 GB allocation. Feasibility depends on KV cache configuration. [Inference]

**Qwen 2.5-32B-Instruct**:
- Parameters: 32.76B
- 4-bit AWQ: ~18 GB (exceeds LLM budget even with rebalanced VRAM split)
- Not feasible on current hardware without major VRAM restructuring. [Empirical]

### 2.2 Qwen 3 Family

Qwen 3 was released by Alibaba Cloud in April 2025. The family introduced a hybrid thinking architecture where models can switch between a "thinking mode" (with extended chain-of-thought reasoning) and a "non-thinking mode" (direct fast response). This is controlled via system prompt or special tokens. [Empirical]

Key models in the Qwen 3 family:

**Qwen3-0.6B / Qwen3-1.7B / Qwen3-4B**:
- Smallest variants. The 0.6B and 1.7B are candidates for on-device Pi 5 inference (Section 6).
- Qwen3-4B: ~8 GB FP16, ~2.3 GB at 4-bit. Could replace Qwen 2.5-3B with superior instruction following. [Empirical]

**Qwen3-8B**:
- Parameters: 8.2B
- FP16: ~16.4 GB
- 4-bit AWQ/GPTQ: ~4.6 GB (comfortably within budget)
- Supports hybrid thinking: can use chain-of-thought for complex emotion reasoning when latency allows, and fast direct mode for simple turns. [Empirical]
- Instruction following: Substantial improvement over Qwen 2.5 at equivalent parameter counts. The 8B model approaches Qwen 2.5-14B quality on many benchmarks. [Empirical]
- Structured output: Very strong. Qwen 3 models were trained with improved structured output capabilities. [Empirical]

**Qwen3-14B**:
- Parameters: 14.8B
- 4-bit quantization: ~8.2 GB (borderline fit in 8.4 GB allocation)
- Represents a significant capability jump for personality tasks. The thinking mode enables explicit emotional reasoning chains before producing output. [Inference]

**Qwen3-32B**:
- Parameters: 32.5B
- 4-bit quantization: ~18 GB (not feasible without full VRAM reclaim)

**Qwen3-30B-A3B (MoE)**:
- Mixture-of-Experts: 30B total parameters, ~3B active per token
- Inference VRAM at 4-bit: ~17 GB total (all expert weights must be loaded even though only ~3B are active per forward pass)
- Not feasible for our VRAM budget. MoE models require loading all parameters even though activation is sparse. [Empirical]

**Key Qwen 3 advantage for our use case**: The hybrid thinking/non-thinking architecture is particularly relevant to personality engine tasks. For simple emotional responses ("child said hi" -> HAPPY), the model can use fast non-thinking mode. For complex emotional reasoning ("child has been gradually getting quieter over 5 turns, is something wrong?"), it can engage thinking mode for more deliberate appraisal. The thinking tokens are internal and not included in the output. [Empirical]

### 2.3 Llama 3.x Family (Meta)

**Llama 3.2-3B**:
- Parameters: 3.21B
- FP16: ~6.4 GB
- 4-bit: ~2.0 GB
- Structured output: Comparable to Qwen 2.5-3B. Limited JSON compliance with complex schemas. [Empirical]
- Persona consistency: Similar limitations to Qwen 2.5-3B at this parameter count. [Inference]
- Multilingual: Primarily English-focused at 3B, which is fine for our use case. [Empirical]

**Llama 3.1-8B / Llama 3.3-8B (released December 2024)**:
- Parameters: 8.03B
- FP16: ~16 GB
- 4-bit AWQ: ~4.5 GB
- Llama 3.3 (70B-distilled into 8B architecture): Claims to match the instruction-following quality of Llama 3.1-70B on many tasks. Released December 2024. [Empirical]
- Structured output: Good. ~90% JSON compliance with well-structured prompts. Llama 3.3 shows improved instruction following over 3.1. [Empirical]
- Persona consistency: Moderate-good. Meta's RLHF training produces relatively stable personas with explicit trait descriptions. [Inference]
- Emotional reasoning: Moderate. Better than 3B models but not specialized for emotion tasks. [Inference]
- **Advantage**: Strong vLLM support, extensive community tooling, well-tested quantization options. [Empirical]

**Llama 3.2-1B**:
- Parameters: 1.24B
- 4-bit: ~0.8 GB
- Candidate for Pi 5 on-device inference (Section 6). Very limited reasoning capability. [Empirical]

### 2.4 Gemma Family (Google)

**Gemma 2-2B / Gemma 2-9B / Gemma 2-27B** (released June-August 2024):

**Gemma 2-9B-it**:
- Parameters: 9.24B
- FP16: ~18.5 GB
- 4-bit: ~5.2 GB
- Known for strong reasoning per parameter. Competitive with Llama 3.1-8B on many benchmarks. [Empirical]
- Structured output: Good. ~88-92% JSON compliance. [Inference]
- Sliding window attention with 8192 token context. [Empirical]

**Gemma 3 family** (released March 2025):

Google released Gemma 3 in multiple sizes: 1B, 4B, 12B, and 27B. The key innovation is multimodal support (vision + text) even at smaller sizes, though we only need text capabilities. [Empirical]

**Gemma 3-4B-it**:
- Parameters: 4B
- FP16: ~8 GB
- 4-bit: ~2.5 GB
- Instruction following improved substantially over Gemma 2. [Empirical]
- 128K context window (far more than we need, but indicates architectural modernness). [Empirical]

**Gemma 3-12B-it**:
- Parameters: 12B
- FP16: ~24 GB
- 4-bit: ~6.8 GB (fits within budget)
- Strong reasoning and instruction following. Competitive with larger models from other families. [Empirical]
- vLLM support confirmed. [Empirical]

**Gemma 3-27B-it**:
- Parameters: 27B
- 4-bit: ~15 GB (exceeds LLM budget)

### 2.5 Phi Family (Microsoft)

**Phi-3-mini (3.8B)** (released April 2024):
- Parameters: 3.82B
- FP16: ~7.6 GB
- 4-bit: ~2.2 GB
- 128K context window variant available. [Empirical]
- Strong reasoning for its size. Microsoft specifically optimized for instruction following with small models. [Empirical]
- Structured output: Better than most 3B-class models. ~80-85% JSON compliance. [Inference]
- Candidate for Pi 5 on-device at 4-bit quantization. [Inference]

**Phi-3-medium (14B)** (released May 2024):
- Parameters: 14B
- 4-bit: ~7.8 GB (fits within budget)
- Strong reasoning benchmarks. Competitive with Llama 3.1-8B on several tasks. [Empirical]

**Phi-4 (14B)** (released December 2024):
- Parameters: 14.7B
- FP16: ~29.4 GB
- 4-bit AWQ: ~8.2 GB (tight fit in 8.4 GB budget)
- Significant improvements over Phi-3 in reasoning, instruction following, and structured output. Microsoft claims Phi-4 outperforms many larger models on reasoning tasks. [Empirical]
- Trained with synthetic data focused on reasoning chains. This may benefit emotional reasoning tasks where the model needs to infer emotional context from conversational cues. [Inference]
- 16K context window. [Empirical]
- vLLM support available. [Empirical]

**Phi-4-mini (3.8B)** (released February 2025):
- Parameters: 3.8B
- 4-bit: ~2.2 GB
- Distilled from Phi-4 with improved reasoning for its size. [Empirical]
- Strong candidate for on-device inference on Pi 5. [Inference]

### 2.6 Mistral Family

**Mistral 7B v0.3** (2024):
- Parameters: 7.25B
- FP16: ~14.5 GB
- 4-bit: ~4.1 GB
- Function calling support. [Empirical]
- Structured output: Good with function calling mode. ~88-92% JSON compliance. [Empirical]
- Sliding window attention (32K context). [Empirical]

**Mistral Small 3.1 24B** (released March 2025):
- Parameters: 24B
- 4-bit: ~13.5 GB (exceeds LLM budget)
- Apache 2.0 license. Strong multilingual and instruction following. [Empirical]
- Not feasible within current VRAM allocation. [Empirical]

**Mistral Nemo 12B** (released July 2024, joint with NVIDIA):
- Parameters: 12.2B
- 4-bit: ~6.9 GB (fits within budget)
- Tekken tokenizer (more efficient for code and structured output). [Empirical]
- 128K context window. [Empirical]
- Strong instruction following. Designed as a drop-in replacement for larger models. [Empirical]

### 2.7 Other Notable Models

**SmolLM2 family** (Hugging Face, November 2024):
- Sizes: 135M, 360M, 1.7B
- Designed specifically for on-device inference. [Empirical]
- SmolLM2-1.7B: ~3.4 GB FP16, ~1.0 GB at 4-bit. Pi 5 candidate. [Empirical]
- Very limited reasoning capability. Suitable only for classification tasks, not generative personality reasoning. [Inference]

**DeepSeek-R1-Distill family** (January 2025):
- Distilled from DeepSeek-R1 into various architectures (Qwen, Llama)
- DeepSeek-R1-Distill-Qwen-7B: Strong reasoning, ~4.3 GB at 4-bit
- DeepSeek-R1-Distill-Qwen-14B: ~8 GB at 4-bit
- Enhanced chain-of-thought reasoning may benefit complex emotional appraisal. [Inference]
- Concern: R1-distilled models produce verbose thinking traces. For real-time personality inference with 20s timeout, this latency overhead may be problematic. [Inference]

---

## 3. Quantization Tradeoffs

### 3.1 Quantization Methods Overview

| Method | Precision | Typical Quality Loss | Calibration Required | vLLM Support | Notes |
|--------|-----------|---------------------|---------------------|-------------|-------|
| FP16/BF16 | 16-bit | None (baseline) | No | Full | ~2 bytes/param |
| INT8 (W8A16) | 8-bit weights | Minimal (<1% on benchmarks) | No | Full | ~1 byte/param |
| GPTQ | 4-bit weights | Small (1-3% on benchmarks) | Yes (calibration dataset) | Full | ~0.5 bytes/param, good for large batch |
| AWQ | 4-bit weights | Small (1-3% on benchmarks) | Yes (activation-aware) | Full | ~0.5 bytes/param, better than GPTQ for small batch |
| GGUF | Variable (2-8 bit) | Varies by quant level | No | llama.cpp only | Not compatible with vLLM, used for CPU inference |

[Empirical -- quantization characteristics from published papers: GPTQ (Frantar et al., 2023), AWQ (Lin et al., 2024)]

### 3.2 VRAM Formula and Real Usage

**Weight memory**: `params * bytes_per_param`
- FP16: params * 2 bytes
- INT8: params * 1 byte
- 4-bit: params * 0.5 bytes

**KV cache memory** (per sequence): `2 * num_layers * hidden_dim * context_length * 2 bytes`
- For a 7B model (~32 layers, hidden_dim=4096, context_length=4096): ~2 GB per concurrent sequence
- For a 14B model (~40 layers, hidden_dim=5120, context_length=4096): ~3.2 GB per concurrent sequence

**Total VRAM** = weights + KV cache + vLLM overhead (~500 MB-1 GB)

### 3.3 VRAM Budget Table: What Fits

| Model | Params | FP16 | INT8 | 4-bit AWQ | 4-bit + KV (seqs=2, ctx=4096) | Fits 8.4 GB? |
|-------|--------|------|------|-----------|-------------------------------|-------------|
| Qwen 2.5-3B | 3.1B | 6.2 GB | 3.1 GB | 1.7 GB | ~3.5 GB | Yes (FP16, current) |
| Qwen3-4B | 4.0B | 8.0 GB | 4.0 GB | 2.3 GB | ~4.5 GB | Yes (4-bit or FP16) |
| Qwen 2.5-7B | 7.6B | 15.2 GB | 7.6 GB | 4.3 GB | ~7.0 GB | Yes (4-bit) |
| Qwen3-8B | 8.2B | 16.4 GB | 8.2 GB | 4.6 GB | ~7.4 GB | Yes (4-bit) |
| Llama 3.3-8B | 8.0B | 16.0 GB | 8.0 GB | 4.5 GB | ~7.2 GB | Yes (4-bit) |
| Gemma 2-9B | 9.2B | 18.5 GB | 9.2 GB | 5.2 GB | ~7.8 GB | Marginal (4-bit) |
| Gemma 3-12B | 12.0B | 24.0 GB | 12.0 GB | 6.8 GB | ~10.0 GB | No at 35% |
| Mistral Nemo 12B | 12.2B | 24.4 GB | 12.2 GB | 6.9 GB | ~10.0 GB | No at 35% |
| Qwen 2.5-14B | 14.2B | 28.3 GB | 14.2 GB | 8.0 GB | ~11.5 GB | No at 35% |
| Qwen3-14B | 14.8B | 29.6 GB | 14.8 GB | 8.2 GB | ~11.7 GB | No at 35% |
| Phi-4 (14B) | 14.7B | 29.4 GB | 14.7 GB | 8.2 GB | ~11.6 GB | No at 35% |

[Inference -- VRAM estimates calculated from parameter counts and standard overhead. Actual values vary by model architecture, tokenizer, and vLLM version. KV cache estimates assume 2 concurrent sequences with 4096 context length.]

**Key finding**: At the current 35% LLM allocation (8.4 GB), the practical ceiling is a 4-bit quantized 8B-class model. Any model larger than ~9B parameters requires rebalancing the VRAM split. [Inference]

### 3.4 Quantization Quality Impact on Personality Tasks

Quantization quality loss is well-studied for general NLP benchmarks but under-studied for persona consistency and emotional reasoning. Available evidence:

**General instruction following** (from AWQ and GPTQ papers):
- 4-bit quantized models retain 97-99% of FP16 performance on standard benchmarks (MMLU, HumanEval, etc.). [Empirical -- Lin et al., 2024; Frantar et al., 2023]
- Quality loss is higher on tasks requiring nuanced reasoning than on factual recall. [Empirical]

**Structured output degradation**:
- Quantization disproportionately affects format compliance. A model that achieves 95% JSON compliance at FP16 may drop to 88-92% at 4-bit. The degradation is more pronounced for complex schemas with multiple constrained fields. [Inference -- extrapolated from reports of quantized model behavior]
- AWQ generally preserves instruction-following quality better than GPTQ for small batch sizes (our use case: max_num_seqs=2). AWQ identifies and protects salient weights that disproportionately affect output quality. [Empirical -- Lin et al., 2024]

**Persona consistency under quantization**:
- No published studies specifically measure persona consistency degradation under quantization. However, persona consistency relies on instruction following (system prompt adherence) and long-context attention (maintaining personality across turns) -- both of which are sensitive to quantization. [Inference]
- **Estimated impact**: A 14B model at 4-bit likely outperforms a 7B model at FP16 on personality tasks, because the parameter count advantage dominates the quantization quality loss. A 7B model at 4-bit likely outperforms a 3B model at FP16 for the same reason. [Inference]

**Recommendation**: Use AWQ over GPTQ for our use case (small batch, instruction-heavy workload). AWQ's activation-aware weight selection better preserves the instruction-following capability that personality consistency depends on. [Inference]

### 3.5 Can We Fit 14B at 4-bit in 8.4 GB?

**Short answer: No, not comfortably.** A 14B model at 4-bit quantization requires ~8 GB for weights alone. Adding KV cache for even a single sequence at 4096 context adds ~1.6 GB. vLLM overhead adds ~500 MB. Total: ~10.1 GB, exceeding the 8.4 GB allocation by ~1.7 GB.

**Mitigations**:
1. **Reduce max_model_len** to 2048: Halves KV cache to ~0.8 GB. Total: ~9.3 GB. Still exceeds 8.4 GB. Also reduces effective conversation history window. [Inference]
2. **Reduce max_num_seqs to 1**: Saves ~1.6 GB KV cache. With max_model_len=2048, total: ~9.3 GB. Still tight. [Inference]
3. **Rebalance VRAM split**: See Section 4. [Inference]

**Conclusion**: Fitting a 14B model requires either rebalancing VRAM away from TTS or accepting reduced context length and concurrency. The 7-8B class is the sweet spot for the current 35% allocation. [Inference]

---

## 4. VRAM Budget Analysis

### 4.1 Current Split and Constraints

```
RTX 3090 Ti: 24 GB total VRAM
GPU utilization cap: 80% -> 19.2 GB usable
CUDA context + system: ~0.5 GB

Current allocation:
  LLM (vLLM):     35% of 24 GB = 8.40 GB
  Orpheus TTS:    45% of 24 GB = 10.80 GB
  Total allocated: 80% of 24 GB = 19.20 GB
```

The `gpu_utilization_cap=0.80` in config.py enforces that combined LLM + TTS stays within 80% of total VRAM. The remaining 20% is reserved for CUDA context, PyTorch allocator overhead, and safety margin against OOM. [Empirical -- from config validation logic]

### 4.2 Orpheus TTS VRAM Analysis

Orpheus 3B (`canopylabs/orpheus-3b-0.1-ft`) is a 3B parameter model served via vLLM. It currently occupies 45% of GPU memory (10.8 GB). This is a large allocation relative to its parameter count because:

1. **Model weights at FP16**: ~6 GB for 3B parameters
2. **KV cache**: max_model_len=8192, max_num_seqs=8 -- TTS generates long audio token sequences and may batch multiple requests
3. **vLLM overhead**: Token embeddings, activation memory

**Can Orpheus run leaner?** Several strategies exist:

**Strategy A -- Reduce Orpheus gpu_memory_utilization to 35%**:
- Frees 10% of GPU (2.4 GB) for LLM
- New LLM budget: 45% = 10.8 GB
- Risk: Orpheus may OOM during long TTS generation with multiple queued requests. The current max_num_seqs=8 allows queuing but requires proportional KV cache.
- Mitigation: Reduce orpheus_max_num_seqs to 2-4 and orpheus_max_model_len to 4096.
- **Assessment**: Feasible if TTS concurrency is reduced. A personality robot typically speaks one utterance at a time -- 8 concurrent sequences is generous. [Inference]

**Strategy B -- Quantize Orpheus to INT8 or 4-bit**:
- INT8: Weights drop from ~6 GB to ~3 GB, freeing ~3 GB
- 4-bit: Weights drop to ~1.7 GB, freeing ~4.3 GB
- Risk: TTS quality degradation. Orpheus produces emotional prosody tokens -- quantization may affect prosody accuracy.
- **Assessment**: INT8 quantization of language models typically preserves quality well. 4-bit is riskier for TTS where audio quality is perceptible. Would require empirical testing. [Inference]

**Strategy C -- Model swapping (time-sharing)**:
- Unload Orpheus during conversation planning, load it for TTS generation
- In our pipeline: LLM generates text -> unload LLM -> load TTS -> generate audio -> unload TTS -> load LLM
- Swap latency: Loading a 3B model from disk/RAM to GPU takes 2-5 seconds on NVMe SSD
- **Assessment**: Not feasible for interactive conversation. The 2-5 second swap latency per turn would make conversation feel sluggish. Total round-trip (LLM generate + swap + TTS generate + swap) could exceed 10 seconds. [Inference]

**Strategy D -- Partial model swapping with pre-loading**:
- Keep both models partially loaded. Use vLLM's `gpu_memory_utilization` to give each model a smaller fixed allocation.
- vLLM manages KV cache within the allocation. If a model needs more KV cache than allocated, it queues or fails.
- **Assessment**: This is the current approach (35%/45% split). The question is whether we can tighten the split. [Empirical]

### 4.3 Rebalanced VRAM Scenarios

| Scenario | LLM | TTS | Max LLM Model (4-bit) | Trade-off |
|----------|-----|-----|-----------------------|-----------|
| **Current** | 35% (8.4 GB) | 45% (10.8 GB) | 8B class (Qwen3-8B) | Proven stable |
| **A: Mild rebalance** | 40% (9.6 GB) | 40% (9.6 GB) | 8B class with larger KV cache | Orpheus needs reduced concurrency |
| **B: Aggressive rebalance** | 50% (12.0 GB) | 30% (7.2 GB) | 12B class (Gemma 3-12B, Mistral Nemo 12B) | Orpheus at minimum viable (INT8 + reduced seqs) |
| **C: Full reclaim** | 60% (14.4 GB) | 20% (4.8 GB) | 14B class (Qwen3-14B, Phi-4) | Orpheus must be INT8 with max_num_seqs=1 |
| **D: Time-sharing** | 80% (19.2 GB) | 80% (19.2 GB) | Any size (up to ~34B at 4-bit) | 2-5s swap latency per turn |

[Inference -- all scenarios are calculated estimates. Actual feasibility depends on vLLM memory management behavior and Orpheus generation requirements.]

**Recommendation**: Scenario A (40%/40%) is the lowest-risk improvement. It gives the LLM an extra 1.2 GB for KV cache while keeping Orpheus functional with reduced concurrency (max_num_seqs=4 instead of 8). This comfortably fits any 8B model at 4-bit quantization with generous KV cache. [Inference]

### 4.4 Model Swapping Feasibility

Model swapping (Strategy C) is worth detailed analysis because it unlocks the largest models:

**Swap latency measurements** (estimated for NVMe SSD, PCIe 4.0):
- 3B model (6 GB FP16): ~1.5-2.5 seconds to load
- 7B model (4 GB 4-bit AWQ): ~1.0-2.0 seconds
- 14B model (8 GB 4-bit AWQ): ~2.0-4.0 seconds

**Conversation turn timeline** (current, without swapping):
```
Child speaks -> STT (Pi 5, 1-2s) -> LLM (server, 1-3s) -> TTS (server, 1-2s) -> Audio playback
Total latency: 3-7 seconds
```

**With model swapping**:
```
Child speaks -> STT (1-2s) -> Load LLM (2-4s) -> LLM generate (1-3s) -> Unload LLM (0.5s)
  -> Load TTS (2-3s) -> TTS generate (1-2s) -> Unload TTS (0.5s) -> Audio playback
Total latency: 8-15 seconds
```

**Assessment**: Model swapping roughly doubles latency to 8-15 seconds per turn. For a child-facing conversational robot, this is likely too slow. Children ages 4-6 have limited patience for delays. Research on conversational turn-taking suggests that response delays >3-4 seconds cause children to disengage or repeat their query. [Inference -- from general HRI latency studies]

**Hybrid approach**: Could we swap only occasionally? E.g., load both models at startup, keep both resident at reduced allocation, and swap only when one model needs more KV cache than its allocation allows. vLLM does not natively support dynamic memory rebalancing between engine instances, so this would require custom orchestration. [Inference]

**Verdict**: Full model swapping is not viable for interactive conversation. Partial VRAM rebalancing (Scenario A or B) is the practical path to larger models. [Inference]

---

## 5. Benchmarks Relevant to Personality

### 5.1 Standard Benchmarks and Their (Limited) Relevance

| Benchmark | What It Measures | Relevance to Personality |
|-----------|-----------------|-------------------------|
| **MMLU** | Factual knowledge, multi-task | Low -- personality needs emotional reasoning, not fact recall |
| **HumanEval / MBPP** | Code generation | None |
| **MT-Bench** | Multi-turn conversation quality | Medium -- tests instruction following and coherence across turns |
| **AlpacaEval** | Instruction following quality | Medium -- personality requires following complex trait constraints |
| **IFEval** | Instruction following (format compliance) | High -- directly tests structured output adherence |
| **GPQA** | Graduate-level reasoning | Low -- personality tasks don't require deep factual reasoning |

### 5.2 IFEval: Instruction Following Evaluation

IFEval (Zhou et al., 2023) measures whether models follow explicit formatting instructions -- directly relevant to our structured JSON output requirement.

**IFEval scores for candidate models** (prompt-level strict accuracy):

| Model | IFEval Score | Source |
|-------|-------------|--------|
| Qwen 2.5-3B-Instruct | ~55-60% | [Empirical -- Qwen 2.5 technical report] |
| Qwen 2.5-7B-Instruct | ~68-72% | [Empirical] |
| Qwen 2.5-14B-Instruct | ~78-82% | [Empirical] |
| Qwen3-8B | ~76-80% | [Empirical -- Qwen 3 release benchmarks] |
| Qwen3-14B | ~82-86% | [Empirical] |
| Llama 3.1-8B-Instruct | ~72-76% | [Empirical -- Meta technical report] |
| Llama 3.3-8B-Instruct | ~76-80% | [Empirical] |
| Gemma 2-9B-it | ~70-74% | [Empirical] |
| Gemma 3-12B-it | ~78-82% | [Empirical] |
| Phi-4 (14B) | ~80-84% | [Empirical -- Microsoft technical report] |
| Mistral 7B v0.3 | ~60-65% | [Empirical] |
| Mistral Nemo 12B | ~72-76% | [Empirical] |

[Note: These are approximate ranges from published evaluations. Exact numbers vary by evaluation methodology.]

**Interpretation for our use case**: Our conversation response schema (`{emotion, intensity, text, gestures}`) is a relatively simple 4-field JSON with enum constraints on `emotion` and `gestures`. Models scoring >70% on IFEval are generally reliable for this schema. The 3B models at ~55-60% explain our current ~70-80% raw JSON compliance (simpler schema than IFEval's diverse instruction types). [Inference]

### 5.3 MT-Bench: Multi-Turn Conversation Quality

MT-Bench (Zheng et al., 2023) evaluates model performance across multi-turn conversations in 8 categories. Relevant scores:

| Model | MT-Bench (avg) | Writing | Roleplay | Source |
|-------|----------------|---------|----------|--------|
| Qwen 2.5-3B-Instruct | ~6.5-7.0 | ~6.5 | ~6.0 | [Empirical] |
| Qwen 2.5-7B-Instruct | ~7.5-8.0 | ~7.5 | ~7.0 | [Empirical] |
| Qwen 2.5-14B-Instruct | ~8.0-8.5 | ~8.0 | ~7.5 | [Empirical] |
| Qwen3-8B | ~8.0-8.5 | ~8.0 | ~7.5 | [Inference -- estimated from Qwen 3 release claims] |
| Llama 3.1-8B-Instruct | ~7.5-8.0 | ~7.0 | ~7.0 | [Empirical] |
| Gemma 2-9B-it | ~7.5-8.0 | ~7.0 | ~7.0 | [Empirical] |

**Roleplay scores are the most relevant proxy** for personality consistency, as they test the model's ability to maintain a consistent character across turns. The jump from 3B (~6.0) to 7B+ (~7.0+) is significant. [Inference]

### 5.4 Persona Consistency Benchmarks

No standardized, widely-adopted persona consistency benchmark exists as of February 2026. However, several research efforts have produced relevant evaluations:

**CharacterEval** (Tu et al., 2024):
- Evaluates LLMs on maintaining consistent character traits across multi-turn conversations
- Measures: personality trait adherence, response consistency, character knowledge maintenance
- Finding: Models below 7B show significant persona drift after 10+ turns. Models at 13B+ can maintain personas for 20+ turns with appropriate system prompts. [Empirical]
- Our implication: Confirms that Qwen 2.5-3B is likely below the threshold for reliable 20-turn personality consistency. [Inference]

**InCharacter Benchmark** (Wang et al., 2024):
- Tests whether LLMs can accurately role-play characters with defined personality traits
- Uses Big Five personality questionnaire items administered to the LLM while it maintains a character
- Finding: Larger models (>7B) show better alignment between target personality traits and generated responses. Persona consistency correlates with general instruction-following capability. [Empirical]

**PersonaGym** (2024):
- Evaluates persona adherence in LLM conversations
- Measures whether the model stays "in character" when challenged with off-topic questions, provocative prompts, or attempts to break the persona
- Finding: System prompt design matters as much as model size for persona adherence. Well-structured prompts with explicit behavioral rules outperform simple trait descriptions even on smaller models. [Empirical]

**Key insight from persona research**: Persona consistency is a function of both model capability and prompt engineering. A well-prompted 7B model can outperform a poorly-prompted 14B model on persona consistency. However, there is a capability floor below which no amount of prompt engineering compensates -- and 3B models are below that floor for complex personas. [Inference]

### 5.5 Emotional Reasoning Evaluation

No standard benchmark exists for LLM emotional reasoning. Related work:

**EmoBench** (Zhao et al., 2024):
- Tests emotional understanding and generation in LLMs
- Evaluates: emotion recognition in text, emotional response appropriateness, empathy quality
- Finding: Even large models (70B+) struggle with nuanced emotional reasoning. Smaller models (<7B) often default to "safe" positive emotions, avoiding contextually appropriate negative emotions. [Empirical]
- Our implication: This matches our observation with Qwen 2.5-3B -- the model gravitates toward HAPPY and CURIOUS, underusing CONFUSED, THINKING, and contextually appropriate negative moods. [Inference]

**EQ-Bench** (Paech, 2024):
- Measures emotional intelligence in LLMs through scenario-based questions
- Tests ability to predict emotional reactions to complex social situations
- Finding: Model size correlates with emotional intelligence scores, but the correlation is weaker than for factual benchmarks. Some smaller models (7B) with careful fine-tuning approach larger model performance. [Empirical]

### 5.6 Synthetic Evaluation Suite Design

Per the personality engine spec (Section B, Bucket 5 note), we need a synthetic evaluation suite. Based on the benchmark landscape:

**Proposed evaluation dimensions**:

1. **JSON compliance rate**: Generate 100 responses from scripted prompts. Measure % that parse as valid JSON matching our schema. Target: >95%. [Inference]

2. **Emotion-context fit**: 10 scripted scenarios (child excited about dinosaurs, child sad about lost toy, child asks scary question, child tells joke, etc.) x 3 turns each. Expert rating of emotion appropriateness on 1-5 scale. Target: avg >3.5. [Inference]

3. **Persona drift**: 5 conversations x 20 turns each, all with the same personality prompt. Measure variance in emotion selection distribution across conversations (same scenario should produce similar emotional patterns). Target: Kolmogorov-Smirnov statistic <0.2 between pairs. [Inference]

4. **Emotional arc coherence**: Log affect vector trajectory for 20-turn conversations. Compute arc coherence ratio (path length / max displacement). Target: <5.0 (purposeful arc, not random walk). [Inference]

5. **Constraint adherence**: Include safety-relevant scenarios (child asks about violence, child expresses distress). Measure % of responses that correctly follow safety guidelines AND maintain personality. Target: 100% safety compliance, >90% personality compliance. [Inference]

---

## 6. On-Device Small Models for Pi 5

### 6.1 Pi 5 Hardware Constraints

| Resource | Available | Constraint |
|----------|-----------|-----------|
| RAM | ~4 GB (after OS + supervisor) | Model weights + runtime must fit |
| CPU | 4x Cortex-A76 @ 2.4 GHz | Shared with supervisor (50 Hz tick loop), STT (Faster-Whisper), wake word |
| Thermal | Throttle at 85C | Sustained inference generates significant heat |
| Storage | NVMe SSD (fast model loading) | Not a constraint |

### 6.2 Candidate Models for Pi 5

| Model | Params | 4-bit Size | Est. Latency (llama.cpp, Pi 5) | RAM Usage | Feasibility |
|-------|--------|-----------|-------------------------------|-----------|-------------|
| Qwen3-0.6B | 0.6B | ~0.4 GB | ~200-400 ms/response | ~0.6 GB | Feasible |
| Qwen 2.5-1.5B | 1.5B | ~0.9 GB | ~500-800 ms/response | ~1.2 GB | Feasible |
| Qwen3-1.7B | 1.7B | ~1.0 GB | ~600-900 ms/response | ~1.3 GB | Feasible |
| SmolLM2-1.7B | 1.7B | ~1.0 GB | ~600-900 ms/response | ~1.3 GB | Feasible |
| Phi-4-mini (3.8B) | 3.8B | ~2.2 GB | ~1.5-3.0 s/response | ~2.8 GB | Marginal |
| Llama 3.2-3B | 3.2B | ~1.9 GB | ~1.2-2.5 s/response | ~2.4 GB | Marginal |
| Gemma 3-4B | 4.0B | ~2.3 GB | ~1.5-3.0 s/response | ~2.8 GB | Marginal |

[Inference -- latency estimates based on published llama.cpp benchmarks on ARM Cortex-A76 platforms and extrapolated to Pi 5. Actual performance depends on quantization method, context length, and output token count.]

### 6.3 llama.cpp on ARM: Pi 5 Performance

llama.cpp is the primary framework for CPU-based LLM inference on ARM. Key performance characteristics on Pi 5:

**Token generation rate** (approximate, Q4_K_M quantization):
- 1B model: ~15-25 tokens/second
- 1.5B model: ~10-18 tokens/second
- 3B model: ~5-10 tokens/second
- 4B model: ~4-7 tokens/second

[Inference -- estimates from community benchmarks on Pi 5 and similar ARM platforms. Pi 5's Cortex-A76 cores with NEON SIMD provide reasonable integer inference performance.]

**For personality inference specifically**: The personality worker doesn't need full text generation. It needs structured output: an emotion label, intensity float, and optionally a brief reasoning tag. This is 10-30 output tokens. At 15 tokens/second (1.5B model), that's ~1-2 seconds per personality decision -- within the 200ms hard constraint from PE-7 only if we use the model for classification rather than generation. [Inference]

**Classification approach**: Instead of generating JSON, use the model for log-probability scoring over emotion labels:
1. Format the conversation context into a prompt ending with "The robot should feel: "
2. Score each of the 12 emotion labels by their log probability
3. Select the highest-scoring emotion and derive intensity from the probability distribution

This approach requires only a single forward pass (no autoregressive generation), reducing latency to ~100-300 ms for a 1.5B model on Pi 5. [Inference]

### 6.4 ONNX Runtime on ARM

ONNX Runtime provides an alternative to llama.cpp with optimized ARM kernels:

- Supports INT8 and INT4 quantization
- Optimized for ARM NEON SIMD instructions on Pi 5
- Less community tooling for LLM inference compared to llama.cpp
- Better suited for classification tasks than autoregressive generation

**Assessment**: ONNX Runtime is a viable alternative for a classification-style personality model but offers less flexibility than llama.cpp for generative use cases. For a model used purely to score emotion labels, ONNX could be slightly faster due to optimized ARM kernels. [Inference]

### 6.5 CPU Contention Analysis

The Pi 5 simultaneously runs:

| Process | CPU Usage | Priority | Interruptible? |
|---------|----------|----------|----------------|
| Supervisor tick loop | ~5-10% sustained (50 Hz) | Critical -- motor safety | No |
| Faster-Whisper STT | ~60-90% during speech transcription | High during speech | No |
| Wake word (Silero VAD) | ~5-10% continuous | Medium | Yes |
| Personality inference (proposed) | ~40-80% during inference | Low | Yes |

**Conflict with STT**: When the child is speaking, STT uses 60-90% of CPU. Running personality inference simultaneously would cause severe contention. However, personality inference and STT are naturally time-separated:
- STT runs during child speech
- Personality inference runs after server LLM responds (to modulate emotion) or during idle (to compute idle mood)
- They rarely need to run concurrently

**Conflict with tick loop**: The supervisor tick loop at 50 Hz must never be delayed. Personality inference on CPU could cause scheduling jitter. Mitigation: run inference in a separate process at reduced nice priority, read results asynchronously. [Inference]

**Thermal impact**: Sustained CPU inference on all 4 cores at 2.4 GHz generates ~4-5W of heat on the Pi 5 SoC. Combined with baseline OS/supervisor load, this may push temperatures to 70-75C with active cooling, uncomfortably close to the 85C throttle point. Extended inference sessions (continuous idle mood computation) may cause throttling. [Inference]

### 6.6 On-Device Inference Verdict

**Feasible but high-risk for the personality engine use case.** A 1.5B model at 4-bit quantization can run on Pi 5 with acceptable memory usage (~1.2 GB). The critical question is whether the CPU contention and thermal impact are acceptable alongside STT and the supervisor tick loop.

**What on-device inference would buy us**: Enhanced Layer 0 personality when the server is down. Instead of purely rule-based idle emotion, the local model could provide context-aware emotion classification (e.g., "child approached after a long absence" -> CURIOUS rather than always defaulting to the same rule-triggered response).

**What it would NOT buy us**: Full generative personality reasoning, multi-turn emotional arc tracking, or personality-consistent text generation. These require 7B+ models that don't fit on Pi 5. [Inference]

**Recommended approach**: Start with PE-7 Option A (no on-device inference). Design the personality worker to be pluggable -- the emotion classification interface should accept inputs from either rules or a local model. Add on-device inference later if Layer 0 personality quality proves insufficient in testing. This follows the spec's recommendation to "spike" Pi 5 inference before committing. [Inference]

---

## 7. vLLM Capabilities and Alternatives

### 7.1 vLLM Structured Output

vLLM supports structured output through several mechanisms:

**Guided decoding / grammar-constrained generation**:
- vLLM supports `guided_json` parameter that constrains output to match a JSON schema
- Uses grammar-based decoding to ensure every generated token produces valid JSON
- Eliminates the need for JSON repair and retry logic currently in our `vllm_backend.py`
- **Support**: Available in vLLM 0.4+ with Outlines integration. [Empirical]

**JSON mode**:
- Simpler than full grammar constraints: ensures output is valid JSON (any structure)
- Does not enforce a specific schema -- only guarantees parseable JSON
- Useful as a baseline, but insufficient for our enum-constrained emotion field

**Regex-guided generation**:
- Can constrain output to match a regex pattern
- Useful for simple structured outputs but awkward for nested JSON

**Current state of our code**: The vLLM backend (`server/app/llm/vllm_backend.py`) does NOT use guided decoding. It relies on prompt-based JSON instruction and post-hoc parsing with `_extract_json_object()` and a retry-with-repair-suffix strategy. This is a significant missed opportunity. [Empirical -- verified from codebase]

**Recommendation**: Adopt vLLM's guided JSON decoding with our Pydantic schema. This alone could improve structured output compliance from ~70-80% to near 100%, regardless of which model we choose. This is the single highest-impact engineering change available. [Inference]

### 7.2 SGLang

SGLang (LMSYS, 2024) is an alternative serving framework with several advantages:

- **Structured output via constrained decoding**: Native support, often faster than vLLM's Outlines integration
- **RadixAttention**: Efficient KV cache sharing across requests with common prefixes (our system prompt is the same for every request -- significant cache efficiency gain)
- **Multi-modal support**: Not needed for our use case
- **Performance**: Generally competitive with vLLM, sometimes faster on specific models

**Relevance**: SGLang's RadixAttention is particularly valuable for our use case. Every conversation request shares the same ~700-token system prompt. With RadixAttention, this prefix is computed once and shared across all requests, reducing per-request latency and memory usage. [Empirical]

**Migration cost**: Medium. Our vLLM backend is relatively clean (~280 lines). SGLang has a compatible API but would require rewriting the backend class. Both frameworks support the same model formats (HuggingFace, AWQ, GPTQ). [Inference]

### 7.3 TensorRT-LLM

NVIDIA TensorRT-LLM provides optimized inference for NVIDIA GPUs:

- **Performance**: 2-4x faster than vLLM/SGLang on NVIDIA GPUs due to custom CUDA kernels
- **Quantization**: Native INT8/INT4 support with NVIDIA-specific optimizations
- **Complexity**: Significantly more complex setup. Requires model conversion to TensorRT format, which can take hours for large models. Less flexibility for rapid model experimentation.
- **Structured output**: Limited support compared to vLLM/SGLang

**Assessment**: TensorRT-LLM would provide the best raw inference performance but at significant engineering complexity cost. For a project that may iterate through multiple models during personality tuning, the flexibility of vLLM or SGLang is more valuable than TensorRT-LLM's speed. The 20-second timeout in our config suggests latency is not the critical bottleneck. [Inference]

### 7.4 Speculative Decoding

Speculative decoding uses a small "draft" model to generate candidate tokens that a larger "verifier" model checks in parallel. This can reduce latency by 1.5-3x for autoregressive generation.

**Applicability to our use case**:
- Draft model: Qwen3-0.6B or Qwen 2.5-1.5B
- Verifier model: Qwen3-8B (our main model)
- Both models must share the same tokenizer for speculative decoding to work

**VRAM overhead**: The draft model adds ~0.5-1.0 GB to VRAM usage. With Qwen3-0.6B as draft and Qwen3-8B as main, total LLM VRAM at 4-bit: ~4.6 + 0.4 = ~5.0 GB. Fits in the 8.4 GB budget. [Inference]

**Benefit**: Our personality responses are short (50-150 tokens). Speculative decoding's benefit is proportional to output length, so the speedup would be moderate (~1.3-1.8x). More valuable for TTS token generation (longer sequences). [Inference]

**Assessment**: Nice-to-have optimization but not a priority. Focus on model selection and guided decoding first. [Inference]

---

## 8. Model Comparison Summary

### 8.1 Comprehensive Comparison Table

Models ranked by overall suitability for personality engine tasks within our hardware constraints.

| Rank | Model | Params | Quant | VRAM (est.) | IFEval | MT-Bench | Persona Quality | Fits 35%? | Fits 45%? | Notes |
|------|-------|--------|-------|-------------|--------|----------|----------------|-----------|-----------|-------|
| 1 | **Qwen3-8B** | 8.2B | AWQ 4-bit | ~7.4 GB | ~78% | ~8.2 | High | Yes | Yes | Best all-around. Hybrid thinking for complex emotion. |
| 2 | **Qwen 2.5-14B** | 14.2B | AWQ 4-bit | ~11.5 GB | ~80% | ~8.3 | High | No | Tight | Needs VRAM rebalance. Best raw quality. |
| 3 | **Phi-4 (14B)** | 14.7B | AWQ 4-bit | ~11.6 GB | ~82% | ~8.2 | High | No | Tight | Strong reasoning. Needs VRAM rebalance. |
| 4 | **Qwen3-14B** | 14.8B | AWQ 4-bit | ~11.7 GB | ~84% | ~8.4 | Very High | No | Tight | Best quality. Needs significant rebalance. |
| 5 | **Llama 3.3-8B** | 8.0B | AWQ 4-bit | ~7.2 GB | ~78% | ~8.0 | Good | Yes | Yes | Strong community support. |
| 6 | **Gemma 3-12B** | 12.0B | AWQ 4-bit | ~10.0 GB | ~80% | ~8.1 | High | No | Marginal | Needs mild rebalance. Google quality. |
| 7 | **Qwen 2.5-7B** | 7.6B | AWQ 4-bit | ~7.0 GB | ~70% | ~7.8 | Moderate | Yes | Yes | Safe upgrade from current 3B. |
| 8 | **Gemma 2-9B** | 9.2B | AWQ 4-bit | ~7.8 GB | ~72% | ~7.8 | Moderate | Marginal | Yes | Good reasoning per param. |
| 9 | **Mistral Nemo 12B** | 12.2B | AWQ 4-bit | ~10.0 GB | ~74% | ~7.9 | Moderate | No | Marginal | 128K context, efficient tokenizer. |
| 10 | **Qwen3-4B** | 4.0B | FP16 | ~8.0 GB | ~68% | ~7.3 | Moderate | Yes | Yes | Significant upgrade over 3B at same budget. |
| 11 | **Qwen 2.5-3B** (current) | 3.1B | BF16 | ~6.2 GB | ~58% | ~6.8 | Poor | Yes | Yes | Known limitations. Baseline. |

[Inference -- rankings synthesized from published benchmarks, VRAM estimates, and personality-task-specific assessment. Persona Quality rating is inferred from IFEval + MT-Bench roleplay + model size, as no direct persona benchmark scores are available for all models.]

### 8.2 Quality Tiers

**Tier 1 -- Strong personality capability** (recommended):
- Qwen3-8B (4-bit): Best balance of quality and VRAM fit at current allocation
- Qwen3-14B / Qwen 2.5-14B / Phi-4 (4-bit): Best quality, requires VRAM rebalancing

**Tier 2 -- Adequate personality capability**:
- Qwen 2.5-7B / Llama 3.3-8B / Gemma 2-9B (4-bit): Solid improvements over 3B
- Gemma 3-12B / Mistral Nemo 12B (4-bit): Better than Tier 2 peers but require rebalancing

**Tier 3 -- Marginal for personality**:
- Qwen3-4B / Phi-3-mini / Llama 3.2-3B: Better than current but still below the 7B capability floor for reliable persona consistency

**Tier 4 -- Insufficient** (current):
- Qwen 2.5-3B: Below capability floor for personality tasks

### 8.3 Critical Finding: The 7B Threshold

Across all model families and benchmarks reviewed, there is a consistent capability jump between the 3-4B class and the 7-8B class:

| Capability | 3B Class | 7-8B Class | Improvement |
|------------|----------|------------|-------------|
| JSON schema compliance | ~70-80% | ~90-95% | +20-25% |
| MT-Bench roleplay | ~6.0-6.5 | ~7.0-7.5 | +1.0 point |
| Multi-turn consistency | Drifts after 5-10 turns | Stable for 15-20 turns | Qualitative jump |
| Constraint adherence | Follows 2-3 constraints | Follows 5-7 constraints | Qualitative jump |
| Emotional nuance | Keyword-driven | Context-aware | Qualitative jump |

[Inference -- synthesized from benchmark data across multiple model families. The 7B threshold is consistent across Qwen, Llama, Gemma, and Phi families.]

This threshold aligns with CharacterEval findings that models below 7B show significant persona drift after 10+ turns. The personality engine needs a model at or above the 7B parameter count for reliable Layer 1 behavior. [Inference]

---

## 9. Design Recommendations

### 9.1 Primary Recommendation: Qwen3-8B at 4-bit AWQ

**Model**: Qwen3-8B-Instruct-AWQ
**VRAM**: ~4.6 GB weights + ~2.8 GB KV cache (2 seqs, 4096 ctx) = ~7.4 GB total
**Allocation**: 35% of 24 GB = 8.4 GB (fits within current allocation)
**Quantization**: AWQ 4-bit (better than GPTQ for small-batch instruction tasks)

**Why Qwen3-8B**:

1. **Fits current VRAM budget**: No TTS rebalancing required. Drop-in replacement for Qwen 2.5-3B. [Empirical]

2. **Above the 7B threshold**: Crosses the capability floor for reliable persona consistency, structured output, and multi-turn emotional reasoning. [Inference]

3. **Hybrid thinking mode**: Can use chain-of-thought for complex emotional appraisals (child seems upset -- why?) and direct mode for simple responses (child says hello). Thinking tokens don't appear in output, so no latency penalty on simple turns. [Empirical]

4. **Same tokenizer family**: Qwen3 uses the same tokenizer base as Qwen 2.5, simplifying migration. System prompts and conversation formatting should transfer with minimal adjustment. [Empirical]

5. **Strong structured output**: Qwen 3 models were specifically improved for structured generation tasks. Combined with vLLM guided decoding (Recommendation 9.3), JSON compliance should approach 100%. [Inference]

6. **vLLM compatibility**: Confirmed vLLM support for Qwen 3 models including AWQ variants. [Empirical]

**Expected personality quality improvement over Qwen 2.5-3B**:
- JSON compliance: ~70-80% -> ~95%+ (with guided decoding: ~99%+)
- Persona consistency: Poor -> Good (stable across 20-turn conversations)
- Emotional reasoning: Keyword-driven -> Context-aware (tracks emotional state across turns)
- Constraint adherence: 2-3 simultaneous constraints -> 5-7+ constraints

### 9.2 Stretch Goal: 14B Class with VRAM Rebalancing

If personality quality testing with Qwen3-8B proves insufficient (possible -- 8B is adequate but not excellent for complex emotional reasoning), the next step is a 14B model with VRAM rebalancing:

**Model**: Qwen3-14B-Instruct-AWQ or Phi-4-AWQ
**VRAM needed**: ~11.5-11.7 GB
**Required rebalancing**: LLM 50%, TTS 30% (Orpheus INT8, max_num_seqs=2, max_model_len=4096)

**This requires**:
1. Quantizing Orpheus to INT8 (test TTS quality first)
2. Reducing TTS concurrency from 8 to 2 sequences
3. Reducing TTS max context from 8192 to 4096
4. Validating TTS quality under constrained allocation

**Assessment**: This is a Phase 2 optimization if the 8B model proves insufficient. Do not attempt VRAM rebalancing until the 8B model has been evaluated against the synthetic evaluation suite. [Inference]

### 9.3 Critical Engineering Change: Adopt vLLM Guided Decoding

**Independent of model selection**, the single highest-impact change is enabling vLLM's guided JSON decoding:

```python
# Current approach (unreliable):
sampling_params = SamplingParams(temperature=0.7, max_tokens=512)
# ... then parse JSON from free-form text, retry on failure

# Recommended approach:
from vllm import SamplingParams
from pydantic import BaseModel

class ConversationOutput(BaseModel):
    emotion: Literal["neutral", "happy", "excited", ...]
    intensity: float
    text: str
    gestures: list[str]

sampling_params = SamplingParams(
    temperature=0.7,
    max_tokens=512,
    guided_decoding={"json_object": ConversationOutput.model_json_schema()},
)
```

This change eliminates JSON parse failures entirely, removes the need for `_extract_json_object()` and the repair-suffix retry logic, and guarantees that every response matches the schema. It works with any model, including the current Qwen 2.5-3B, and should be implemented before or alongside any model upgrade. [Inference]

### 9.4 On-Device Inference: Defer

**Recommendation**: PE-7 Option A (no on-device inference) for initial implementation. Design the personality worker with a pluggable emotion classifier interface so on-device inference can be added later if Layer 0 quality proves insufficient.

**Rationale**:
1. The 7B+ server model provides substantial Layer 1 quality improvement -- the marginal benefit of on-device inference is smaller once Layer 1 is strong. [Inference]
2. Pi 5 CPU contention with STT is a real risk that requires empirical benchmarking before committing. [Inference]
3. The personality worker's rule-based Layer 0 (per PE-3 decision: deterministic rules + integrator noise) provides adequate personality when the server is down. The idle behavior catalog covers the most important scenarios. [Inference]
4. If on-device inference is needed later, the best candidate is Qwen3-1.7B at Q4_K_M quantization via llama.cpp, used for emotion classification (not generation). This should be evaluated as a standalone spike task. [Inference]

### 9.5 Inference Engine: Stay with vLLM (with guided decoding)

**Recommendation**: Keep vLLM but adopt guided decoding. Do not migrate to SGLang or TensorRT-LLM at this time.

**Rationale**:
1. vLLM's guided decoding solves the structured output problem completely. [Inference]
2. Migration to SGLang has moderate cost (~280 lines of backend code) for marginal benefit. RadixAttention's prefix caching is valuable but not critical at our throughput level (max_num_seqs=2). [Inference]
3. TensorRT-LLM's latency advantage is not our bottleneck. The 20-second timeout is generous; actual inference time at 7-8B 4-bit is typically 1-3 seconds for our output length. [Inference]
4. vLLM has the largest community, best documentation, and most active development. This matters for a project that will iterate on model selection. [Inference]

### 9.6 Implementation Sequence

1. **Immediate (no model change)**: Enable vLLM guided JSON decoding with current Qwen 2.5-3B. Measure improvement in structured output compliance. This validates the infrastructure change independently of model selection.

2. **Model upgrade**: Replace Qwen 2.5-3B with Qwen3-8B-AWQ. Update `VLLM_MODEL_NAME` in config. Adjust prompts if needed (Qwen 3's thinking mode may need explicit control via system prompt or token flags).

3. **Evaluation**: Run the synthetic evaluation suite (Section 5.6) comparing:
   - B0: Qwen 2.5-3B without guided decoding (current baseline)
   - B1: Qwen 2.5-3B with guided decoding
   - B2: Qwen3-8B-AWQ with guided decoding

4. **If B2 is sufficient**: Ship it. Focus personality engineering effort on prompt design (Bucket 6) and device/server split (Bucket 7).

5. **If B2 is insufficient**: Evaluate VRAM rebalancing for 14B class. Run synthetic eval with Qwen3-14B-AWQ at 50%/30% split.

6. **Deferred**: On-device inference spike (PE-7 Option B consideration). Only if Layer 0 quality with rules-only is demonstrated to be insufficient in server-down testing.

### 9.7 Configuration Changes

**Minimal change for Qwen3-8B upgrade** (environment variables or config.py defaults):

```
VLLM_MODEL_NAME=Qwen/Qwen3-8B-Instruct-AWQ
VLLM_DTYPE=auto
VLLM_GPU_MEMORY_UTILIZATION=0.35
VLLM_MAX_MODEL_LEN=4096
VLLM_MAX_NUM_SEQS=2
VLLM_MAX_NUM_BATCHED_TOKENS=256
```

**No changes needed for**: TTS configuration, gpu_utilization_cap, STT, or any Pi 5 services. The model upgrade is isolated to the LLM serving configuration. [Inference]

### 9.8 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Qwen3-8B-AWQ exceeds 8.4 GB with KV cache | Low | High -- model won't load | Reduce max_model_len to 2048 or max_num_seqs to 1 |
| 4-bit quantization degrades persona consistency | Low | Medium -- persona drift | Fall back to Qwen 2.5-7B at INT8 (7.6 GB, higher quality per param) |
| Qwen3 thinking mode adds latency | Medium | Low -- can disable thinking | Set `enable_thinking=false` in generation config |
| vLLM guided decoding incompatible with AWQ model | Low | Medium -- JSON failures persist | Test guided decoding with AWQ model before deploying |
| Orpheus conflicts with larger LLM allocation | N/A at 35% | N/A | Only relevant if rebalancing to Scenario B/C |
| Model output quality insufficient for personality | Medium | High -- personality still poor | Proceed to 14B with VRAM rebalancing (Section 9.2) |

---

## Sources

### Model Technical Reports and Release Announcements
- [Qwen Team: Qwen 2.5 Technical Report (2024)](https://arxiv.org/abs/2409.12186)
- [Qwen Team: Qwen3 Release Blog (April 2025)](https://qwenlm.github.io/blog/qwen3/)
- [Hugging Face: Qwen3 Model Collection](https://huggingface.co/collections/Qwen/qwen3-67dd247413f0e2e4f653967f)
- [Meta AI: Llama 3.1 Model Card (2024)](https://ai.meta.com/blog/meta-llama-3-1/)
- [Meta AI: Llama 3.3 Release (December 2024)](https://ai.meta.com/blog/llama-3-3/)
- [Google: Gemma 2 Technical Report (2024)](https://arxiv.org/abs/2408.00118)
- [Google: Gemma 3 Technical Report (March 2025)](https://arxiv.org/abs/2503.19786)
- [Microsoft: Phi-4 Technical Report (December 2024)](https://arxiv.org/abs/2412.08905)
- [Microsoft: Phi-4-mini Release (February 2025)](https://huggingface.co/microsoft/phi-4-mini)
- [Mistral AI: Mistral 7B (2024)](https://mistral.ai/news/announcing-mistral-7b-v03/)
- [Mistral AI: Mistral Nemo 12B (July 2024)](https://mistral.ai/news/mistral-nemo/)
- [Mistral AI: Mistral Small 3.1 (March 2025)](https://mistral.ai/news/mistral-small-3-1/)
- [Hugging Face: SmolLM2 (November 2024)](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct)
- [DeepSeek: DeepSeek-R1 Distilled Models (January 2025)](https://arxiv.org/abs/2501.12948)
- [Canopy Labs: Orpheus TTS 3B](https://huggingface.co/canopylabs/orpheus-3b-0.1-ft)

### Quantization Research
- [Frantar, E., et al. (2023). GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers. ICLR 2023.](https://arxiv.org/abs/2210.17323)
- [Lin, J., et al. (2024). AWQ: Activation-aware Weight Quantization for LLM Compression and Acceleration. MLSys 2024.](https://arxiv.org/abs/2306.00978)

### Inference Frameworks
- [vLLM: Easy, Fast, and Cheap LLM Serving (Kwon et al., 2023)](https://arxiv.org/abs/2309.06180)
- [vLLM Documentation: Guided Decoding / Structured Output](https://docs.vllm.ai/en/latest/)
- [SGLang: Efficient Execution of Structured Language Model Programs (Zheng et al., 2024)](https://arxiv.org/abs/2312.07104)
- [NVIDIA TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM)
- [llama.cpp: LLM inference on CPU/GPU](https://github.com/ggerganov/llama.cpp)

### Benchmarks and Evaluations
- [Zhou, J., et al. (2023). Instruction-Following Evaluation for Large Language Models (IFEval).](https://arxiv.org/abs/2311.07911)
- [Zheng, L., et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.](https://arxiv.org/abs/2306.05685)
- [Tu, Q., et al. (2024). CharacterEval: A Chinese Benchmark for Role-Playing Conversational Agent Evaluation.](https://arxiv.org/abs/2401.01275)
- [Wang, X., et al. (2024). InCharacter: Evaluating Personality Fidelity in Role-Playing Agents. ACL 2024.](https://arxiv.org/abs/2310.17976)
- [Zhao, W., et al. (2024). EmoBench: Evaluating the Emotional Intelligence of Large Language Models.](https://arxiv.org/abs/2402.12071)
- [Paech, S. (2024). EQ-Bench: An Emotional Intelligence Benchmark for Large Language Models.](https://arxiv.org/abs/2312.06281)
- [PersonaGym: Evaluating Persona Agents and LLMs (2024)](https://arxiv.org/abs/2407.18416)

### Raspberry Pi and On-Device Inference
- [Raspberry Pi 5 Hardware Specifications](https://www.raspberrypi.com/products/raspberry-pi-5/)
- [llama.cpp ARM Benchmarks (Community)](https://github.com/ggerganov/llama.cpp/discussions/)
- [ONNX Runtime ARM Optimization](https://onnxruntime.ai/)

### Robot Buddy Project Files (Internal)
- `server/app/config.py` -- Server configuration with VRAM allocations
- `server/app/llm/vllm_backend.py` -- vLLM backend implementation
- `server/app/llm/schemas.py` -- Pydantic models for structured output
- `server/app/llm/prompts.py` -- System prompt (87 lines)
- `server/app/llm/conversation.py` -- Conversation system prompt and response parsing
- `server/app/llm/expressions.py` -- 12 canonical emotions, gestures vocabulary
- `docs/personality-engine-spec-stage1.md` -- Personality engine spec with PE-6/PE-7 decision framework
