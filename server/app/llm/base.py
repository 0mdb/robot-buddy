"""Backend abstraction for planner and conversation LLM inference."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.conversation import ConversationHistory, ConversationResponse
    from app.llm.schemas import ModelPlan, WorldState


class LLMError(RuntimeError):
    """Base error for LLM backend failures."""


class LLMTimeoutError(LLMError):
    """Raised when LLM generation exceeds configured timeout."""


class LLMUnavailableError(LLMError):
    """Raised when the configured backend is unavailable."""


class LLMBusyError(LLMError):
    """Raised when backend generation admission is saturated."""


class PlannerLLMBackend(ABC):
    """Unified async interface for plan + conversation generation."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def warm(self, timeout_s: float = 120.0) -> None:
        raise NotImplementedError

    @abstractmethod
    async def generate_plan(self, state: WorldState) -> ModelPlan:
        raise NotImplementedError

    @abstractmethod
    async def generate_conversation(
        self,
        history: ConversationHistory,
        user_text: str,
        *,
        override_temperature: float | None = None,
        override_max_output_tokens: int | None = None,
    ) -> ConversationResponse:
        raise NotImplementedError

    async def stream_conversation(
        self,
        history: ConversationHistory,
        user_text: str,
        *,
        override_temperature: float | None = None,
        override_max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream the raw V2 JSON response as content deltas.

        Backends with native token streaming override this. The default
        fallback calls ``generate_conversation`` and yields the equivalent
        JSON as a single chunk — correctness-preserving but no latency win.

        Implementations MUST add the user message to history before yielding
        anything; callers finalize ``history.add_assistant`` once the full
        text is parsed.
        """
        response = await self.generate_conversation(
            history,
            user_text,
            override_temperature=override_temperature,
            override_max_output_tokens=override_max_output_tokens,
        )
        payload = {
            "emotion": response.emotion,
            "intensity": response.intensity,
            "mood_reason": response.mood_reason,
            "gestures": response.gestures,
            "memory_tags": response.memory_tags,
            "text": response.text,
        }
        yield json.dumps(payload, ensure_ascii=False)

    def debug_snapshot(self) -> dict:
        return {
            "backend": self.backend_name,
            "model": self.model_name,
            "loaded": False,
        }
