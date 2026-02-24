"""vLLM-backed implementation for planner + conversation inference."""

from __future__ import annotations

import asyncio
import json
import inspect
import logging
import time
import uuid
from typing import Any, Literal, cast

from app.config import settings
from app.llm.base import (
    LLMBusyError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    PlannerLLMBackend,
)
from app.llm.conversation import (
    ConversationHistory,
    ConversationResponse,
    ConversationResponseV2,
    parse_conversation_response_content,
)
from app.llm.model_config import resolve_template_config
from app.llm.prompts import SYSTEM_PROMPT, format_user_prompt
from app.llm.schemas import ModelPlan, WorldState

log = logging.getLogger(__name__)

_JSON_REPAIR_SUFFIX = (
    "The previous output was invalid. Return ONLY one valid JSON object."
)

_VLLM_DTYPE = Literal["auto", "half", "float16", "bfloat16", "float", "float32"]

# Cached V2 JSON schema for guided decoding (generated once from Pydantic model).
_CONVERSATION_V2_JSON_SCHEMA = ConversationResponseV2.model_json_schema()


def _extract_json_object(text: str) -> str:
    """Best-effort extraction of the first JSON object from free-form text.

    Used for plan generation (which doesn't use guided decoding yet).
    """
    if not isinstance(text, str):
        return ""
    raw = text.strip()
    if not raw:
        return ""
    lo = raw.find("{")
    if lo < 0:
        return raw

    # Parse only the first JSON object and ignore any trailing chatter.
    candidate = raw[lo:]
    try:
        parsed, _ = json.JSONDecoder().raw_decode(candidate)
        return json.dumps(parsed)
    except json.JSONDecodeError:
        # Fallback for malformed output: keep the broadest {...} slice.
        hi = raw.rfind("}")
        if hi > lo:
            return raw[lo : hi + 1]
        return candidate


class VLLMBackend(PlannerLLMBackend):
    """In-process vLLM backend for Qwen plan + conversation generation."""

    def __init__(self) -> None:
        self._model_name = settings.vllm_model_name
        self._engine: Any = None
        self._tokenizer: Any = None
        self._template_kwargs: dict[str, Any] = {}
        self._SamplingParams: Any = None
        self._GuidedDecodingParams: Any = None
        self._loaded = False

        self._max_inflight = max(1, int(settings.llm_max_inflight))
        self._active_generations = 0
        self._generation_lock = asyncio.Lock()

    @property
    def backend_name(self) -> str:
        return "vllm"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def start(self) -> None:
        try:
            from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams
        except ImportError as exc:
            raise LLMUnavailableError(
                "vllm backend requested but vllm is not installed"
            ) from exc

        # GuidedDecodingParams may not exist in older vLLM versions.
        try:
            from vllm.sampling_params import GuidedDecodingParams
        except ImportError:
            GuidedDecodingParams = None
            log.warning(
                "vLLM GuidedDecodingParams not available — falling back to unguided"
            )

        dtype = cast(_VLLM_DTYPE, settings.vllm_dtype)
        engine_args = AsyncEngineArgs(
            model=self._model_name,
            dtype=dtype,
            gpu_memory_utilization=settings.vllm_gpu_memory_utilization,
            max_model_len=settings.vllm_max_model_len,
            max_num_seqs=settings.vllm_max_num_seqs,
            max_num_batched_tokens=settings.vllm_max_num_batched_tokens,
        )
        self._engine = AsyncLLMEngine.from_engine_args(engine_args)
        self._SamplingParams = SamplingParams
        self._GuidedDecodingParams = GuidedDecodingParams

        # Load tokenizer for chat template application.
        self._load_tokenizer()

        self._loaded = True
        log.info(
            "vLLM backend loaded (%s, gpu_mem=%.2f, max_len=%d, guided=%s, "
            "chat_template=%s, model_family=%s)",
            self._model_name,
            settings.vllm_gpu_memory_utilization,
            settings.vllm_max_model_len,
            GuidedDecodingParams is not None,
            self._tokenizer is not None,
            self._template_kwargs.get("_family", "unknown"),
        )

    def _load_tokenizer(self) -> None:
        """Load the model tokenizer and resolve template config."""
        model_cfg = resolve_template_config(self._model_name)
        self._template_kwargs = dict(model_cfg.chat_template_kwargs)

        # Config-level override for enable_thinking.
        if "enable_thinking" in self._template_kwargs:
            self._template_kwargs["enable_thinking"] = settings.vllm_enable_thinking

        # Store family for diagnostics.
        self._template_kwargs["_family"] = model_cfg.family

        try:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            log.info(
                "Loaded tokenizer for %s (family=%s, template_kwargs=%s)",
                self._model_name,
                model_cfg.family,
                {k: v for k, v in self._template_kwargs.items() if k != "_family"},
            )
        except Exception as exc:
            log.warning(
                "Failed to load tokenizer for %s, falling back to flat format: %s",
                self._model_name,
                exc,
            )
            self._tokenizer = None

    async def close(self) -> None:
        if self._engine is None:
            return
        shutdown = getattr(self._engine, "shutdown", None)
        try:
            if callable(shutdown):
                maybe = shutdown()
                if inspect.isawaitable(maybe):
                    await maybe
        except Exception:
            log.warning("vLLM shutdown raised unexpectedly", exc_info=True)
        finally:
            self._engine = None
            self._tokenizer = None
            self._template_kwargs = {}
            self._SamplingParams = None
            self._GuidedDecodingParams = None
            self._loaded = False

    async def health_check(self) -> bool:
        return bool(self._loaded and self._engine is not None)

    async def warm(self, timeout_s: float = 120.0) -> None:
        if not self._loaded:
            return
        try:
            dummy = WorldState(
                robot_id="warmup",
                seq=0,
                monotonic_ts_ms=0,
                mode="IDLE",
                battery_mv=8000,
                range_mm=1000,
                trigger="warmup",
            )
            await asyncio.wait_for(self.generate_plan(dummy), timeout=timeout_s)
            log.info("vLLM model warm-up complete.")
        except Exception as exc:
            log.warning("vLLM model warm-up failed: %s", exc)

    async def generate_plan(self, state: WorldState) -> ModelPlan:
        await self._acquire_generation_slot()
        try:
            messages = self._build_plan_messages(state)
            for attempt in (1, 2):
                prompt = self._apply_chat_template(messages)
                text = await self._generate_text(
                    prompt, request_tag=f"plan-{state.seq}-{attempt}"
                )
                candidate = _extract_json_object(text)
                try:
                    plan = ModelPlan.model_validate_json(candidate)
                    plan.actions = plan.actions[: settings.max_actions]
                    return plan
                except Exception as exc:
                    if attempt == 1:
                        messages.append(
                            {"role": "user", "content": _JSON_REPAIR_SUFFIX}
                        )
                        continue
                    raise LLMError(f"Failed to parse plan: {exc}") from exc
            raise LLMError("Failed to generate valid plan")
        finally:
            await self._release_generation_slot()

    async def generate_conversation(
        self,
        history: ConversationHistory,
        user_text: str,
        *,
        override_temperature: float | None = None,
        override_max_output_tokens: int | None = None,
    ) -> ConversationResponse:
        history.add_user(user_text)
        await self._acquire_generation_slot()
        try:
            messages = history.to_ollama_messages()
            prompt = self._apply_chat_template(messages)

            # With guided decoding, the output is guaranteed valid JSON matching
            # the V2 schema — no repair loop needed.
            if self._GuidedDecodingParams is not None:
                text = await self._generate_text(
                    prompt,
                    request_tag=f"conv-{history.turn_count}-1",
                    guided_json_schema=_CONVERSATION_V2_JSON_SCHEMA,
                    override_temperature=override_temperature,
                    override_max_output_tokens=override_max_output_tokens,
                )
                response = parse_conversation_response_content(text)
                history.add_assistant(response.text, emotion=response.emotion)
                return response

            # Fallback: unguided generation with JSON repair loop.
            for attempt in (1, 2):
                text = await self._generate_text(
                    prompt,
                    request_tag=f"conv-{history.turn_count}-{attempt}",
                    override_temperature=override_temperature,
                    override_max_output_tokens=override_max_output_tokens,
                )
                candidate = _extract_json_object(text)
                try:
                    response = parse_conversation_response_content(candidate)
                    history.add_assistant(response.text, emotion=response.emotion)
                    return response
                except Exception:
                    if attempt == 1:
                        messages.append(
                            {"role": "user", "content": _JSON_REPAIR_SUFFIX}
                        )
                        prompt = self._apply_chat_template(messages)
                        continue
                    raise
            raise LLMError("Failed to generate valid conversation response")
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Conversation generation failed: {exc}") from exc
        finally:
            await self._release_generation_slot()

    def engine_metrics(self) -> dict[str, Any]:
        """Best-effort snapshot of vLLM engine internals (scheduler, KV cache).

        vLLM internal APIs vary across versions, so every access uses
        defensive getattr() chains and degrades gracefully to {}.
        """
        if not self._loaded or self._engine is None:
            return {}

        metrics: dict[str, Any] = {}
        try:
            engine = getattr(self._engine, "engine", None)
            if engine is None:
                return metrics

            scheduler = getattr(engine, "scheduler", None)
            if scheduler is None:
                # vLLM v0.8+ uses scheduler[0] list
                schedulers = getattr(engine, "scheduler", None)
                if isinstance(schedulers, list) and schedulers:
                    scheduler = schedulers[0]

            if scheduler is not None:
                running = getattr(scheduler, "running", [])
                waiting = getattr(scheduler, "waiting", [])
                swapped = getattr(scheduler, "swapped", [])
                metrics["scheduler_running"] = len(running)
                metrics["scheduler_waiting"] = len(waiting)
                metrics["scheduler_swapped"] = len(swapped)

                # KV cache block allocator
                block_manager = getattr(scheduler, "block_manager", None)
                if block_manager is not None:
                    gpu_alloc = getattr(block_manager, "gpu_allocator", None)
                    if gpu_alloc is not None:
                        free_fn = getattr(gpu_alloc, "get_num_free_blocks", None)
                        total_fn = getattr(gpu_alloc, "get_num_total_blocks", None)
                        if callable(free_fn) and callable(total_fn):
                            free = free_fn()
                            total = total_fn()
                            if isinstance(total, int) and total > 0:
                                metrics["kv_cache_free_blocks"] = free
                                metrics["kv_cache_total_blocks"] = total
                                metrics["kv_cache_usage_pct"] = round(
                                    (1.0 - free / total) * 100, 1
                                )
        except Exception:
            log.debug("Failed to read vLLM engine metrics", exc_info=True)

        return metrics

    def debug_snapshot(self) -> dict:
        family = self._template_kwargs.get("_family", "unknown")

        # Resolve template config for visibility
        template_cfg = resolve_template_config(self._model_name)

        return {
            "backend": self.backend_name,
            "model": self.model_name,
            "loaded": self._loaded,
            "max_inflight": self._max_inflight,
            "active_generations": self._active_generations,
            "gpu_memory_utilization": settings.vllm_gpu_memory_utilization,
            "max_model_len": settings.vllm_max_model_len,
            "max_num_seqs": settings.vllm_max_num_seqs,
            "max_num_batched_tokens": settings.vllm_max_num_batched_tokens,
            "guided_decoding": self._GuidedDecodingParams is not None,
            "chat_template": self._tokenizer is not None,
            "model_family": family,
            "template_config": {
                "family": template_cfg.family,
                "chat_template_kwargs": dict(template_cfg.chat_template_kwargs),
                "notes": template_cfg.notes,
            },
            "generation_defaults": {
                "temperature": settings.vllm_temperature,
                "max_output_tokens": settings.vllm_max_output_tokens,
                "timeout_s": settings.vllm_timeout_s,
                "enable_thinking": settings.vllm_enable_thinking,
            },
            "engine_metrics": self.engine_metrics(),
        }

    # -- Chat template formatting -------------------------------------------

    def _apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        add_generation_prompt: bool = True,
    ) -> str:
        """Format messages using the model's built-in chat template.

        Falls back to a flat ``ROLE: content`` format if no tokenizer was
        loaded (e.g. in unit tests or if transformers is unavailable).
        """
        if self._tokenizer is None:
            return self._flat_format_messages(messages, add_generation_prompt)

        # Build kwargs for apply_chat_template, excluding internal keys.
        template_kwargs = {
            k: v for k, v in self._template_kwargs.items() if not k.startswith("_")
        }

        try:
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=add_generation_prompt,
                **template_kwargs,
            )
        except TypeError as exc:
            # Model template may not support all kwargs (e.g. enable_thinking
            # is Qwen3-specific). Retry without extra kwargs.
            log.warning(
                "apply_chat_template failed with kwargs %s: %s; retrying without",
                template_kwargs,
                exc,
            )
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=add_generation_prompt,
            )

    @staticmethod
    def _flat_format_messages(
        messages: list[dict[str, str]],
        add_generation_prompt: bool,
    ) -> str:
        """Legacy flat format for environments without a tokenizer."""
        lines: list[str] = []
        for msg in messages:
            role = str(msg.get("role", "user")).strip().upper()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        if add_generation_prompt:
            lines.append("ASSISTANT:")
        return "\n\n".join(lines)

    # -- Message builders ---------------------------------------------------

    @staticmethod
    def _build_plan_messages(state: WorldState) -> list[dict[str, str]]:
        """Build the messages list for a plan generation request."""
        user_msg = format_user_prompt(state)
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{user_msg}\n\n"
                    "Return only one valid JSON object that matches the requested schema."
                ),
            },
        ]

    # -- Internal -----------------------------------------------------------

    async def _generate_text(
        self,
        prompt: str,
        *,
        request_tag: str,
        guided_json_schema: dict[str, Any] | None = None,
        override_temperature: float | None = None,
        override_max_output_tokens: int | None = None,
    ) -> str:
        if self._engine is None or self._SamplingParams is None:
            raise LLMUnavailableError("vllm backend not initialized")

        temperature = settings.vllm_temperature
        max_tokens = settings.vllm_max_output_tokens
        if override_temperature is not None:
            temperature = max(0.0, min(2.0, override_temperature))
        if override_max_output_tokens is not None:
            max_tokens = max(64, min(2048, override_max_output_tokens))

        sp_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Attach guided decoding if schema provided and vLLM supports it.
        if guided_json_schema is not None and self._GuidedDecodingParams is not None:
            sp_kwargs["guided_decoding"] = self._GuidedDecodingParams(
                json_object=guided_json_schema,
            )

        sampling_params = self._SamplingParams(**sp_kwargs)
        request_id = f"{request_tag}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        agen = self._engine.generate(prompt, sampling_params, request_id=request_id)

        try:
            final_output = await asyncio.wait_for(
                self._consume_generation(agen),
                timeout=settings.vllm_timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError("llm_timeout") from exc

        outputs = getattr(final_output, "outputs", None) or []
        if not outputs:
            raise LLMError("vllm returned no outputs")
        text = getattr(outputs[0], "text", "")
        if not isinstance(text, str) or not text.strip():
            raise LLMError("vllm returned empty text")
        return text.strip()

    @staticmethod
    async def _consume_generation(agen: Any) -> Any:
        last = None
        async for out in agen:
            last = out
        return last

    async def _acquire_generation_slot(self) -> None:
        async with self._generation_lock:
            if self._active_generations >= self._max_inflight:
                raise LLMBusyError("llm_busy")
            self._active_generations += 1

    async def _release_generation_slot(self) -> None:
        async with self._generation_lock:
            if self._active_generations > 0:
                self._active_generations -= 1
