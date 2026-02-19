"""Compatibility shim for older Ollama imports.

New code should use:
    - app.llm.base (error + interface types)
    - app.llm.factory (backend selection)
    - app.llm.ollama_backend / app.llm.vllm_backend
"""

from __future__ import annotations

from app.llm.base import LLMError as OllamaError
from app.llm.ollama_backend import OllamaBackend as OllamaClient

__all__ = ["OllamaClient", "OllamaError"]
