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

    Streams raw PCM audio (16kHz, 16-bit mono) as chunks are generated.
    For the orpheus_tts backend, first bytes arrive within ~200–500 ms
    (true streaming); other backends synthesize-then-chunk.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    tts = get_tts()

    # Fail fast if TTS is already known to be unavailable (e.g. disabled via
    # TTS_BACKEND=off, or performance_mode not enabled).  This avoids
    # committing to a 200 response that would immediately send zero bytes.
    snap = tts.debug_snapshot()
    if snap["loaded"] and snap["init_error"]:
        raise HTTPException(status_code=503, detail=snap["init_error"])

    # stream() does the busy check synchronously before returning the iterator,
    # so TTSBusyError is raised here — before the StreamingResponse is created
    # — allowing us to return a proper 503.
    try:
        audio_iter = tts.stream(req.text, req.emotion)
    except TTSBusyError:
        raise HTTPException(status_code=503, detail="tts_busy_no_fallback") from None

    async def audio_stream() -> AsyncGenerator[bytes, None]:
        async for chunk in audio_iter:
            yield chunk

    return StreamingResponse(
        audio_stream(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1",
        },
    )
