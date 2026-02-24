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
from app.llm.prompts import SYSTEM_PROMPT, format_user_prompt
from app.llm.schemas import ModelPlan, WorldState

log = logging.getLogger(__name__)

_JSON_REPAIR_SUFFIX = (
    "\n\nThe previous output was invalid. Return ONLY one valid JSON object."
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
        self._loaded = True
        log.info(
            "vLLM Qwen backend loaded (%s, gpu_mem=%.2f, max_len=%d, guided=%s)",
            self._model_name,
            settings.vllm_gpu_memory_utilization,
            settings.vllm_max_model_len,
            GuidedDecodingParams is not None,
        )

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
            prompt = self._build_plan_prompt(state)
            for attempt in (1, 2):
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
                        prompt = f"{prompt}{_JSON_REPAIR_SUFFIX}"
                        continue
                    raise LLMError(f"Failed to parse plan: {exc}") from exc
            raise LLMError("Failed to generate valid plan")
        finally:
            await self._release_generation_slot()

    async def generate_conversation(
        self,
        history: ConversationHistory,
        user_text: str,
    ) -> ConversationResponse:
        history.add_user(user_text)
        await self._acquire_generation_slot()
        try:
            prompt = self._build_conversation_prompt(history)

            # With guided decoding, the output is guaranteed valid JSON matching
            # the V2 schema — no repair loop needed.
            if self._GuidedDecodingParams is not None:
                text = await self._generate_text(
                    prompt,
                    request_tag=f"conv-{history.turn_count}-1",
                    guided_json_schema=_CONVERSATION_V2_JSON_SCHEMA,
                )
                response = parse_conversation_response_content(text)
                history.add_assistant(response.text, emotion=response.emotion)
                return response

            # Fallback: unguided generation with JSON repair loop.
            for attempt in (1, 2):
                text = await self._generate_text(
                    prompt,
                    request_tag=f"conv-{history.turn_count}-{attempt}",
                )
                candidate = _extract_json_object(text)
                try:
                    response = parse_conversation_response_content(candidate)
                    history.add_assistant(response.text, emotion=response.emotion)
                    return response
                except Exception:
                    if attempt == 1:
                        prompt = f"{prompt}{_JSON_REPAIR_SUFFIX}"
                        continue
                    raise
            raise LLMError("Failed to generate valid conversation response")
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Conversation generation failed: {exc}") from exc
        finally:
            await self._release_generation_slot()

    def debug_snapshot(self) -> dict:
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
        }

    async def _generate_text(
        self,
        prompt: str,
        *,
        request_tag: str,
        guided_json_schema: dict[str, Any] | None = None,
    ) -> str:
        if self._engine is None or self._SamplingParams is None:
            raise LLMUnavailableError("vllm backend not initialized")

        sp_kwargs: dict[str, Any] = {
            "temperature": settings.vllm_temperature,
            "max_tokens": settings.vllm_max_output_tokens,
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

    @staticmethod
    def _build_plan_prompt(state: WorldState) -> str:
        user_msg = format_user_prompt(state)
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"{user_msg}\n\n"
            "Return only one valid JSON object that matches the requested schema."
        )

    @staticmethod
    def _build_conversation_prompt(history: ConversationHistory) -> str:
        messages = history.to_ollama_messages()
        lines: list[str] = []
        for msg in messages:
            role = str(msg.get("role", "user")).strip().upper()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        lines.append("ASSISTANT:")
        return "\n\n".join(lines)

    async def _acquire_generation_slot(self) -> None:
        async with self._generation_lock:
            if self._active_generations >= self._max_inflight:
                raise LLMBusyError("llm_busy")
            self._active_generations += 1

    async def _release_generation_slot(self) -> None:
        async with self._generation_lock:
            if self._active_generations > 0:
                self._active_generations -= 1
