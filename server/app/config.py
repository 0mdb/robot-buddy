"""Server configuration with environment variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    """Planner server settings. Override any field via environment variable."""

    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model_name: str = os.environ.get("MODEL_NAME", "qwen3:14b")
    plan_timeout_s: float = float(os.environ.get("PLAN_TIMEOUT_S", "5.0"))
    warmup_llm: bool = os.environ.get("WARMUP_LLM", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    max_actions: int = int(os.environ.get("MAX_ACTIONS", "5"))
    temperature: float = float(os.environ.get("TEMPERATURE", "0.7"))
    num_ctx: int = int(os.environ.get("NUM_CTX", "4096"))
    converse_keep_alive: str = os.environ.get("CONVERSE_KEEP_ALIVE", "0s")
    orpheus_gpu_memory_utilization: float = float(
        os.environ.get("ORPHEUS_GPU_MEMORY_UTILIZATION", "0.45")
    )
    orpheus_max_model_len: int = int(os.environ.get("ORPHEUS_MAX_MODEL_LEN", "8192"))
    orpheus_max_num_seqs: int = int(os.environ.get("ORPHEUS_MAX_NUM_SEQS", "8"))
    orpheus_max_num_batched_tokens: int = int(
        os.environ.get("ORPHEUS_MAX_NUM_BATCHED_TOKENS", "512")
    )
    orpheus_idle_timeout_s: float = float(
        os.environ.get("ORPHEUS_IDLE_TIMEOUT_S", "8.0")
    )
    orpheus_total_timeout_s: float = float(
        os.environ.get("ORPHEUS_TOTAL_TIMEOUT_S", "60.0")
    )
    host: str = os.environ.get("SERVER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("SERVER_PORT", "8100"))


settings = Settings()
