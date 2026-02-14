"""Request/response models for the TTS endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TtsRequest(BaseModel):
    """Text-to-speech synthesis request."""

    text: str = Field(max_length=200)
    emotion: str = Field(default="neutral")
    intensity: float = Field(ge=0.0, le=1.0, default=0.5)


class TtsResult(BaseModel):
    """Metadata returned alongside the audio bytes (in response headers)."""

    duration_ms: int = Field(ge=0, description="Audio duration in milliseconds")
    sample_rate: int
    format: str
    emotion: str
    cached: bool = False
