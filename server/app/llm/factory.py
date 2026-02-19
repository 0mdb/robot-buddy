"""Factory for selecting planner LLM backend implementation."""

from __future__ import annotations

from app.config import settings
from app.llm.base import PlannerLLMBackend
from app.llm.ollama_backend import OllamaBackend
from app.llm.vllm_backend import VLLMBackend


def create_llm_backend() -> PlannerLLMBackend:
    backend = settings.llm_backend
    if backend == "vllm":
        return VLLMBackend()
    return OllamaBackend()
