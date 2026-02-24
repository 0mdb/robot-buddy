"""Configuration validation tests."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_settings_reject_vllm_gpu_budget_over_cap() -> None:
    with pytest.raises(
        ValueError,
        match="Combined VLLM/ORPHEUS GPU utilization exceeds GPU_UTILIZATION_CAP",
    ):
        Settings(
            llm_backend="vllm",
            vllm_gpu_memory_utilization=0.50,
            orpheus_gpu_memory_utilization=0.40,
            gpu_utilization_cap=0.80,
        )


def test_settings_reject_tts_max_utterance_below_1() -> None:
    with pytest.raises(ValueError, match="TTS_MAX_UTTERANCE_S must be >= 1.0"):
        Settings(tts_max_utterance_s=0.5)


def test_settings_allow_same_budget_when_backend_is_ollama() -> None:
    settings = Settings(
        llm_backend="ollama",
        vllm_gpu_memory_utilization=0.50,
        orpheus_gpu_memory_utilization=0.40,
        gpu_utilization_cap=0.80,
    )
    assert settings.llm_backend == "ollama"
