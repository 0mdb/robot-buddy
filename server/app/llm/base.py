"""Backend abstraction for planner and conversation LLM inference."""

from __future__ import annotations

from abc import ABC, abstractmethod
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

    def debug_snapshot(self) -> dict:
        return {
            "backend": self.backend_name,
            "model": self.model_name,
            "loaded": False,
        }
