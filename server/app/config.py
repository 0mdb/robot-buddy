"""Server configuration with environment variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:
    # Optional dependency; env vars still work without .env loading.
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(slots=True)
class Settings:
    """Planner server settings. Override any field via environment variable."""

    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model_name: str = os.environ.get("MODEL_NAME", "qwen3:14b")
    plan_timeout_s: float = float(os.environ.get("PLAN_TIMEOUT_S", "5.0"))
    warmup_llm: bool = _env_bool("WARMUP_LLM", True)
    auto_pull_ollama_model: bool = _env_bool("AUTO_PULL_OLLAMA_MODEL", True)
    ollama_pull_timeout_s: float = float(
        os.environ.get("OLLAMA_PULL_TIMEOUT_S", "1800.0")
    )
    max_actions: int = int(os.environ.get("MAX_ACTIONS", "5"))
    temperature: float = float(os.environ.get("TEMPERATURE", "0.7"))
    num_ctx: int = int(os.environ.get("NUM_CTX", "4096"))
    converse_keep_alive: str = os.environ.get("CONVERSE_KEEP_ALIVE", "0s")
    stt_model_size: str = os.environ.get("STT_MODEL_SIZE", "base.en")
    stt_device: str = os.environ.get("STT_DEVICE", "cpu")
    stt_compute_type: str = os.environ.get("STT_COMPUTE_TYPE", "int8")
    tts_backend: str = os.environ.get("TTS_BACKEND", "auto").lower()
    tts_model_name: str = os.environ.get(
        "TTS_MODEL_NAME", "canopylabs/orpheus-3b-0.1-ft"
    )
    tts_voice: str = os.environ.get("TTS_VOICE", "en-us")
    tts_rate_wpm: int = int(os.environ.get("TTS_RATE_WPM", "165"))
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
