"""POST /tts — Direct Text-to-Speech generation."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai_runtime import get_tts

log = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    emotion: str = "neutral"
    stream: bool = True


@router.post("/tts")
async def generate_speech(req: TTSRequest) -> StreamingResponse:
    """Generate speech from text immediately (bypassing LLM).

    Returns a stream of raw PCM audio (16kHz, 16-bit mono) or WAV container
    depending on the engine implementation. Orpheus streams raw PCM chunks.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    tts = get_tts()

    async def audio_generator() -> AsyncGenerator[bytes, None]:
        try:
            # Stream chunks from the TTS engine
            async for chunk in tts.stream(req.text, req.emotion):
                if chunk:
                    yield chunk
        except Exception as e:
            log.error(f"TTS generation failed: {e}")
            # We cannot raise HTTP exception here once stream starts,
            # but we can log it.
            return

    return StreamingResponse(
        audio_generator(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1",
        },
    )
