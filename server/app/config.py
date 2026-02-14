"""Server configuration with environment variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    """Personality server settings. Override any field via environment variable."""

    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model_name: str = os.environ.get("MODEL_NAME", "qwen3:14b")
    plan_timeout_s: float = float(os.environ.get("PLAN_TIMEOUT_S", "5.0"))
    max_actions: int = int(os.environ.get("MAX_ACTIONS", "5"))
    temperature: float = float(os.environ.get("TEMPERATURE", "0.7"))
    num_ctx: int = int(os.environ.get("NUM_CTX", "4096"))
    host: str = os.environ.get("SERVER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("SERVER_PORT", "8100"))


settings = Settings()
