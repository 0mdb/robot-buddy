"""Model-specific chat template configuration registry.

Each model family has its own chat template embedded in its tokenizer_config.json.
This registry maps model-name patterns to extra kwargs passed to
``tokenizer.apply_chat_template()``, so switching models only requires
changing the model name — template parameters are resolved automatically.

Orpheus TTS (Llama-3.2 backbone) handles its own template internally via
``OrpheusModel._format_prompt()`` and is not covered here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Registry data
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ModelTemplateConfig:
    """Template parameters for a model family."""

    family: str
    chat_template_kwargs: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


# Ordered by specificity — first match wins in resolve_template_config().
_MODEL_CONFIGS: list[ModelTemplateConfig] = [
    ModelTemplateConfig(
        family="qwen3",
        chat_template_kwargs={"enable_thinking": False},
        notes=(
            "ChatML format (<|im_start|>/<|im_end|>). "
            "enable_thinking=False suppresses <think> blocks, "
            "saving ~100-200 tokens/gen and reducing latency."
        ),
    ),
    ModelTemplateConfig(
        family="qwen2",
        chat_template_kwargs={},
        notes="ChatML format. No thinking mode support.",
    ),
    ModelTemplateConfig(
        family="qwen",
        chat_template_kwargs={},
        notes="ChatML format (generic Qwen fallback).",
    ),
    ModelTemplateConfig(
        family="llama",
        chat_template_kwargs={},
        notes="Llama chat format.",
    ),
]

_DEFAULT_CONFIG = ModelTemplateConfig(family="default")


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_template_config(model_name: str) -> ModelTemplateConfig:
    """Match a HuggingFace model name/path to its template config.

    Matching is case-insensitive against the model name string.
    Returns a default (empty kwargs) config if no family matches.
    """
    name_lower = model_name.lower()
    for cfg in _MODEL_CONFIGS:
        if cfg.family in name_lower:
            return cfg
    return _DEFAULT_CONFIG
