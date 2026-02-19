"""Tests for LLM backend factory selection."""

from __future__ import annotations

from app.config import settings
from app.llm.factory import create_llm_backend
from app.llm.ollama_backend import OllamaBackend
from app.llm.vllm_backend import VLLMBackend


def test_factory_selects_ollama(monkeypatch):
    monkeypatch.setattr(settings, "llm_backend", "ollama")
    backend = create_llm_backend()
    assert isinstance(backend, OllamaBackend)


def test_factory_selects_vllm(monkeypatch):
    monkeypatch.setattr(settings, "llm_backend", "vllm")
    backend = create_llm_backend()
    assert isinstance(backend, VLLMBackend)
