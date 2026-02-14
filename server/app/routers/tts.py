"""POST /tts — synthesise speech from text with emotion prosody."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.tts.schemas import TtsRequest

log = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/tts",
    responses={
        200: {"content": {"audio/wav": {}}, "description": "Synthesised audio"},
        503: {"description": "TTS backend unavailable"},
    },
)
async def synthesise(body: TtsRequest, request: Request) -> Response:
    """Accept text + emotion hint and return synthesised audio."""
    synth = request.app.state.tts

    try:
        audio_bytes, meta = await synth.synthesise(
            text=body.text,
            emotion=body.emotion,
            intensity=body.intensity,
        )
    except Exception as exc:
        log.error("TTS synthesis failed: %s", exc)
        return JSONResponse(
            {"error": "tts_error", "detail": str(exc)},
            status_code=503,
        )

    return Response(
        content=audio_bytes,
        media_type=f"audio/{meta.format}",
        headers={
            "X-Duration-Ms": str(meta.duration_ms),
            "X-Sample-Rate": str(meta.sample_rate),
            "X-Emotion": meta.emotion,
            "X-Cached": str(meta.cached).lower(),
        },
    )
