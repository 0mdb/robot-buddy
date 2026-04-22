"""Vision feedback loop feasibility spike (task follow-up plan, 2026-04-22).

Loads Gemma 4 E4B GPTQ with multimodal image input enabled and runs a
canned image+text prompt to answer: does this model actually see images
on our hardware (3090 Ti, Ampere, 24 GB)?

Measures:
  - Peak VRAM during model load and inference
  - First-token latency on a cold image turn
  - Response text (does it reference the image's actual content?)

This is a DE-RISK step. It intentionally:
  - Does not touch server/app/ code.
  - Does not touch the production .env (read-only config lookup).
  - Does not load Orpheus — coexistence is checked separately by
    restarting the planner afterward with skip_mm_encoder=False.

Run with:
    cd server && .venv/bin/python scripts/spike_vision_loop.py

The planner server MUST be stopped before running — we need the whole
24 GB to ourselves to get a clean VRAM measurement.
"""

from __future__ import annotations

import asyncio
import os
import time

import torch
from PIL import Image, ImageDraw
from transformers import AutoProcessor, AutoTokenizer
from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams


MODEL = os.environ.get(
    "VLLM_MODEL_NAME", "Vishva007/gemma-4-E4B-it-W4A16-AutoRound-GPTQ"
)
DTYPE = os.environ.get("VLLM_DTYPE", "float16")
QUANT = os.environ.get("VLLM_QUANTIZATION", "gptq")
GPU_UTIL = float(os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0.45"))
MAX_MODEL_LEN = int(os.environ.get("VLLM_MAX_MODEL_LEN", "4096"))


def _build_test_image() -> Image.Image:
    """320x240 synthetic image: red square on white, with a blue circle.

    Designed so a working vision model CAN'T easily BS the answer — it has
    to name concrete colors (red, blue, white) and shapes to pass the
    grounded-response criterion. Matches the supervisor's default JPEG size.
    """
    img = Image.new("RGB", (320, 240), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 60, 140, 180], fill="red")
    d.ellipse([180, 80, 280, 180], fill="blue")
    return img


def _vram_snapshot(label: str) -> None:
    if not torch.cuda.is_available():
        print(f"[{label}] CUDA unavailable")
        return
    torch.cuda.synchronize()
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    free, total = torch.cuda.mem_get_info()
    free_gb = free / 1024**3
    total_gb = total / 1024**3
    print(
        f"[{label}] allocated={allocated:.2f} GiB  reserved={reserved:.2f} GiB  "
        f"free={free_gb:.2f}/{total_gb:.1f} GiB"
    )


async def main() -> int:
    print(
        f"spike_vision_loop: model={MODEL} dtype={DTYPE} quant={QUANT} "
        f"gpu_util={GPU_UTIL} max_len={MAX_MODEL_LEN}"
    )
    _vram_snapshot("pre-load")

    # The critical engine arg for this spike: allow one image per prompt
    # instead of forcing image=0 (which is production's text-only behavior).
    engine_args = AsyncEngineArgs(
        model=MODEL,
        dtype=DTYPE,
        quantization=QUANT,
        gpu_memory_utilization=GPU_UTIL,
        max_model_len=MAX_MODEL_LEN,
        max_num_seqs=2,
        max_num_batched_tokens=256,
        limit_mm_per_prompt={"image": 1, "audio": 0},
    )
    print("building engine...")
    engine = AsyncLLMEngine.from_engine_args(engine_args)
    _vram_snapshot("post-engine-load")

    # Tokenizer + processor — multimodal prompts need the processor to
    # render image placeholders into the chat template string.
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    processor = None
    try:
        processor = AutoProcessor.from_pretrained(MODEL)
    except Exception as exc:
        print(f"AutoProcessor unavailable for {MODEL}: {exc}")

    img = _build_test_image()
    print(f"test image: {img.size} mode={img.mode}")

    # Mixed-content user message. The vLLM Gemma 4 recipe shape:
    #   [{"type": "text", ...}, {"type": "image", "image": ...}]
    user_content = [
        {
            "type": "text",
            "text": "What do you see in this image? Be specific about colors and shapes.",
        },
        {"type": "image"},  # placeholder; actual image passed via multi_modal_data
    ]
    messages = [
        {"role": "user", "content": user_content},
    ]

    # Prefer processor.apply_chat_template (multimodal-aware) over tokenizer.
    template_source = processor if processor is not None else tokenizer
    print(f"template source: {type(template_source).__name__}")
    try:
        prompt = template_source.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception as exc:
        print(f"apply_chat_template FAILED: {exc}")
        return 1
    print(f"prompt length: {len(prompt)} chars")
    print(f"prompt preview: {prompt[:300]!r}...")

    sampling = SamplingParams(temperature=0.0, max_tokens=128)
    request_id = "spike-vision-1"

    # vLLM API: pass the actual image via multi_modal_data
    mm_data = {"image": img}

    t0 = time.monotonic()
    first_token_time: float | None = None
    final_text = ""

    agen = engine.generate(
        {"prompt": prompt, "multi_modal_data": mm_data},
        sampling,
        request_id=request_id,
    )

    async for out in agen:
        outputs = getattr(out, "outputs", None) or []
        if not outputs:
            continue
        text = outputs[0].text
        if first_token_time is None and text:
            first_token_time = time.monotonic() - t0
            print(f"first token @ {first_token_time * 1000:.1f} ms")
        final_text = text

    total_time = time.monotonic() - t0
    _vram_snapshot("post-inference")

    print("\n=== RESULT ===")
    print(f"first_token_ms: {(first_token_time or -1) * 1000:.1f}")
    print(f"total_ms:       {total_time * 1000:.1f}")
    print(f"response:\n{final_text}")
    print("=== end ===\n")

    # Shut down cleanly so the spike doesn't leave the engine resident.
    shutdown = getattr(engine, "shutdown", None)
    if callable(shutdown):
        try:
            maybe = shutdown()
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as exc:
            print(f"engine shutdown raised: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
