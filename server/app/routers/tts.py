"""POST /tts — Direct Text-to-Speech generation."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai_runtime import get_tts
from app.tts.orpheus import TTSBusyError

log = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    emotion: str = "neutral"
    stream: bool = True
    robot_id: str | None = None
    seq: int | None = None
    monotonic_ts_ms: int | None = None


@router.post("/tts")
async def generate_speech(req: TTSRequest) -> StreamingResponse:
    """Generate speech from text immediately (bypassing LLM).

    Returns a stream of raw PCM audio (16kHz, 16-bit mono) or WAV container
    depending on the engine implementation. Orpheus streams raw PCM chunks.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    tts = get_tts()
    try:
        audio = await tts.synthesize(req.text, req.emotion)
    except TTSBusyError:
        raise HTTPException(status_code=503, detail="tts_busy_no_fallback") from None
    except Exception as e:
        log.error("TTS generation failed: %s", e)
        raise HTTPException(status_code=503, detail="tts_unavailable") from e

    async def audio_generator() -> AsyncGenerator[bytes, None]:
        chunk_size = 320
        for off in range(0, len(audio), chunk_size):
            chunk = audio[off : off + chunk_size]
            if chunk:
                yield chunk

    return StreamingResponse(
        audio_generator(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1",
        },
    )
