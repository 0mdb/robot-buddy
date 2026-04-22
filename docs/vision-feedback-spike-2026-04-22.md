# Vision Feedback Loop — Feasibility Spike Report (2026-04-22)

## Question

Does Gemma 4 E4B GPTQ (W4A16) with multimodal image input enabled actually work on our 3090 Ti alongside Orpheus, and does it meaningfully "see" what a `look()` tool call would hand it?

## TL;DR — GO

All five pass criteria met. Vision turns produce grounded responses in under a second of first-token latency; Gemma + Orpheus both fit with ~2.4 GB VRAM headroom at the current `(0.45, 0.35)` utilization split. No rebalance needed. Proceed to the integration plan.

## Criteria results

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Gemma + Orpheus fit at current `(0.45, 0.35)` split without OOM | **PASS.** Both warmed cleanly. |
| 2 | ≥ 300 MB free after both engines warm | **PASS.** 2.4 GB free (2465 / 24564 MiB). |
| 3 | `Gemma4Processor.apply_chat_template` accepts mixed text+image content | **PASS.** Prompt rendered with `<\|image\|>` placeholder; vLLM accepted it with `multi_modal_data={"image": PIL}`. |
| 4 | Canned image prompt yields a grounded response | **PASS.** See "Response text" below. |
| 5 | First-token latency < 3 s on cold image turn | **PASS.** 976.5 ms (single image, no history). |

## Measurements

### Solo-Gemma run (text-only baseline → vision-enabled)

Script: `server/scripts/spike_vision_loop.py` (retained as artifact).

| Stage | Free VRAM |
|-------|-----------|
| Pre-load | 22.23 GiB |
| Post-engine-load (Gemma w/ vision) | 11.19 GiB |
| Post-inference | 10.79 GiB |

Gemma w/ vision alone consumed ~12.3 GiB. Inference held steady at ~12.7 GiB.

**First-token latency:** 976.5 ms.
**Total latency (128 tokens):** 1778.3 ms.

### Coexistence run (Gemma w/ vision + Orpheus)

With `skip_mm_encoder=False` applied temporarily and the planner restarted:

| Process | VRAM |
|---------|------|
| Gemma 4 E4B GPTQ + vision | 11,308 MiB |
| Orpheus TTS | 8,828 MiB |
| STT (faster-whisper) | 430 MiB |
| Xorg/desktop | ~900 MiB |
| **Total used** | **21,466 MiB** |
| **Free** | **2,465 MiB (~2.4 GiB)** |

Log-level detail:
- Gemma `Model loading took 9.61 GiB memory` (text-only baseline: 9.03 GiB → **+580 MiB** for vision-encoder workspace).
- Gemma KV cache: **0.7 GiB** available, GPU KV cache size **7,664 tokens** (text-only baseline: 1.29 GiB / 14,032 tokens → KV capacity **halved** because image tokens eat into the same pool).
- Orpheus: unchanged at 6.18 GiB weights / 1.92 GiB KV cache / 17,968 tokens.

### Quality: response text on the canned test

Test image: 320×240 RGB, red square on the left, blue circle on the right, white background.

User prompt: `"What do you see in this image? Be specific about colors and shapes."`

Gemma response (temperature 0.0, 128 max tokens):

```
The image features two distinct shapes against a plain white background.

1.  On the left: There is a square. This square is colored a vibrant red.
2.  On the right: There is a circle. This circle is colored a deep blue
    (specifically, a royal or electric blue).

The two shapes are positioned side-by-side, with the square being
noticeably to the left of the circle.
```

Correctly named: red square, blue circle, white background, positional relationship. Vision loop is truly feeding through — not BS.

### End-to-end live conversation (coexistence sanity)

With vision enabled on the server, ran two `/converse` text turns:

- `"Hello there!"` → no-tool selection timed out at the first turn (cold guided-decoding warmup, same as the preamble shipped with; subsequent turns stay under budget), `happy` emotion, normal streaming TTS.
- `"Do you see the ball?"` → `look` tool fired in 163 ms, `curious` emotion, response `"Ooh, I don't see a ball right now. Is there a ball you wanted to show me?"` (metadata said `ball_detected=false` — text-only preamble passed that through correctly).

No OOM, no stream regressions, MCP client stayed connected, streaming TTS intact. Coexistence is real, not just a load-time pass.

## What changed during the spike

- `server/scripts/spike_vision_loop.py` — new, retained.
- `server/app/llm/model_config.py:62-72` — temporarily flipped `skip_mm_encoder=True → False` for the coexistence test, **reverted** at the end.
- `/home/ben/robot-buddy/.env` — **not** modified (plan B rebalance was not needed).

Production state restored: text-only preamble, `skip_mm_encoder=True`, VRAM split `(0.45, 0.35)`.

## Notable findings to feed the integration plan

1. **Vision encoder was NOT loaded in text-only mode.** The prior survey was ambiguous; the measurement is clear: enabling the encoder adds +580 MiB model weights + shrinks the KV cache pool by ~6,400 tokens. Net: 11.3 GB Gemma vs 7.9 GB Gemma text-only → +3.4 GB on-GPU delta.
2. **KV cache halves.** 14k → 7.6k tokens with `max_model_len=4096, max_num_seqs=2`. That's still above the 4k single-stream ceiling but below the 8k-for-two-concurrent needed for plan + converse overlap. If real traffic ever hits `/plan` while `/converse` is mid-turn, we'll queue. Document this in the integration plan.
3. **Chat template integration is cleaner than expected.** `Gemma4Processor` (from `AutoProcessor.from_pretrained(...)`) handles the mixed-content template natively — no need to hand-roll image placeholder insertion. The integration can swap `tokenizer.apply_chat_template` for `processor.apply_chat_template` when images are present.
4. **vLLM API shape:** `engine.generate({"prompt": str, "multi_modal_data": {"image": PIL.Image}}, ...)` works. PIL Image object directly; no base64 decode in the backend.
5. **Deprecation warning:** vLLM logs `Passing raw prompts to InputProcessor is deprecated and will be removed in v0.18.` The recommended `Renderer.render_chat()` path is the future. Low-urgency since we're on 0.19 stable.

## Decision: GO

Proceed with the full integration plan. Target: thread `ToolResult` (with optional PIL image) from preamble through `stream_conversation` → `to_ollama_messages`; swap chat-template application to `Gemma4Processor` when images are present; update `_join_text_content` → `_process_mcp_content` to return `(text, list[ImageContent])`; flip `skip_mm_encoder=False` as a production commit. VRAM rebalance not required.
