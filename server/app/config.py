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


_NUM_CTX_CAP = 4096
_GPU_UTILIZATION_CAP_DEFAULT = 0.80


@dataclass(slots=True)
class Settings:
    """Planner server settings. Override any field via environment variable."""

    llm_backend: str = os.environ.get("LLM_BACKEND", "vllm").strip().lower()
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model_name: str = os.environ.get("MODEL_NAME", "qwen3:14b")
    vllm_model_name: str = os.environ.get("VLLM_MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
    vllm_dtype: str = os.environ.get("VLLM_DTYPE", "bfloat16")
    vllm_gpu_memory_utilization: float = float(
        os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0.35")
    )
    vllm_max_model_len: int = int(os.environ.get("VLLM_MAX_MODEL_LEN", "4096"))
    vllm_max_num_seqs: int = int(os.environ.get("VLLM_MAX_NUM_SEQS", "2"))
    vllm_max_num_batched_tokens: int = int(
        os.environ.get("VLLM_MAX_NUM_BATCHED_TOKENS", "256")
    )
    vllm_temperature: float = float(os.environ.get("VLLM_TEMPERATURE", "0.7"))
    vllm_timeout_s: float = float(os.environ.get("VLLM_TIMEOUT_S", "20.0"))
    vllm_max_output_tokens: int = int(os.environ.get("VLLM_MAX_OUTPUT_TOKENS", "512"))
    llm_max_inflight: int = int(os.environ.get("LLM_MAX_INFLIGHT", "1"))
    gpu_utilization_cap: float = float(
        os.environ.get(
            "GPU_UTILIZATION_CAP",
            str(_GPU_UTILIZATION_CAP_DEFAULT),
        )
    )
    plan_timeout_s: float = float(os.environ.get("PLAN_TIMEOUT_S", "5.0"))
    warmup_llm: bool = _env_bool("WARMUP_LLM", True)
    auto_pull_ollama_model: bool = _env_bool("AUTO_PULL_OLLAMA_MODEL", True)
    ollama_pull_timeout_s: float = float(
        os.environ.get("OLLAMA_PULL_TIMEOUT_S", "1800.0")
    )
    plan_max_inflight: int = int(os.environ.get("PLAN_MAX_INFLIGHT", "1"))
    plan_keep_alive: str = os.environ.get("PLAN_KEEP_ALIVE", "0s")
    max_actions: int = int(os.environ.get("MAX_ACTIONS", "5"))
    temperature: float = float(os.environ.get("TEMPERATURE", "0.7"))
    num_ctx: int = int(os.environ.get("NUM_CTX", "4096"))
    converse_keep_alive: str = os.environ.get("CONVERSE_KEEP_ALIVE", "0s")
    performance_mode: bool = _env_bool("PERFORMANCE_MODE", False)
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
    orpheus_min_free_vram_gb: float = float(
        os.environ.get("ORPHEUS_MIN_FREE_VRAM_GB", "10.0")
    )
    tts_busy_queue_threshold: int = int(os.environ.get("TTS_BUSY_QUEUE_THRESHOLD", "0"))
    host: str = os.environ.get("SERVER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("SERVER_PORT", "8100"))

    def __post_init__(self) -> None:
        if self.llm_backend not in {"ollama", "vllm"}:
            raise ValueError("LLM_BACKEND must be one of: ollama, vllm")
        if self.llm_max_inflight < 1:
            raise ValueError("LLM_MAX_INFLIGHT must be >= 1")
        if self.plan_max_inflight < 1:
            raise ValueError("PLAN_MAX_INFLIGHT must be >= 1")
        if self.num_ctx < 256 or self.num_ctx > _NUM_CTX_CAP:
            raise ValueError(f"NUM_CTX must be between 256 and {_NUM_CTX_CAP}")
        if self.vllm_max_model_len < 256:
            raise ValueError("VLLM_MAX_MODEL_LEN must be >= 256")
        if self.vllm_max_num_seqs < 1:
            raise ValueError("VLLM_MAX_NUM_SEQS must be >= 1")
        if self.vllm_max_num_batched_tokens < 16:
            raise ValueError("VLLM_MAX_NUM_BATCHED_TOKENS must be >= 16")
        if not (0.0 <= self.vllm_temperature <= 2.0):
            raise ValueError("VLLM_TEMPERATURE must be in [0.0, 2.0]")
        if self.vllm_timeout_s <= 0.0:
            raise ValueError("VLLM_TIMEOUT_S must be > 0")
        if self.vllm_max_output_tokens < 64:
            raise ValueError("VLLM_MAX_OUTPUT_TOKENS must be >= 64")
        if not (0.05 <= self.vllm_gpu_memory_utilization <= 0.95):
            raise ValueError("VLLM_GPU_MEMORY_UTILIZATION must be in [0.05, 0.95]")
        if not (0.05 <= self.orpheus_gpu_memory_utilization <= 0.95):
            raise ValueError("ORPHEUS_GPU_MEMORY_UTILIZATION must be in [0.05, 0.95]")
        if not (0.5 <= self.gpu_utilization_cap <= 0.95):
            raise ValueError("GPU_UTILIZATION_CAP must be in [0.5, 0.95]")
        if self.llm_backend == "vllm":
            combined = self.vllm_gpu_memory_utilization + self.orpheus_gpu_memory_utilization
            if combined > self.gpu_utilization_cap:
                raise ValueError(
                    "Combined VLLM/ORPHEUS GPU utilization exceeds GPU_UTILIZATION_CAP"
                )
        if self.tts_busy_queue_threshold < 0:
            raise ValueError("TTS_BUSY_QUEUE_THRESHOLD must be >= 0")


settings = Settings()
