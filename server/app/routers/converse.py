"""WebSocket /converse endpoint — bidirectional conversation streaming.

Protocol:
    Client → Server:
        {"type": "audio", "data": "<base64 PCM 16kHz 16-bit mono>"}
        {"type": "end_utterance"}
        {"type": "cancel"}
        {"type": "text", "text": "..."}  # bypass STT, send text directly

    Server → Client:
        {"type": "listening"}
        {"type": "transcription", "text": "..."}
        {"type": "emotion", "emotion": "excited", "intensity": 0.8}
        {"type": "gestures", "names": ["nod"]}
        {"type": "audio", "data": "<base64 PCM 16kHz 16-bit mono>", "chunk_index": N}
        {"type": "done"}
        {"type": "error", "message": "..."}
"""

from __future__ import annotations

import base64
import logging

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.llm.client import OllamaError
from app.llm.conversation import (
    ConversationHistory,
    generate_conversation_response,
)
from app.tts.orpheus import OrpheusTTS

log = logging.getLogger(__name__)

router = APIRouter()

# Lazy-loaded STT and TTS instances (shared across connections)
_stt = None
_tts = None


def _get_stt():
    global _stt
    if _stt is None:
        try:
            from app.stt.whisper import WhisperSTT

            _stt = WhisperSTT()
        except ImportError:
            log.warning("faster-whisper not installed. STT unavailable.")
    return _stt


def _get_tts() -> OrpheusTTS:
    global _tts
    if _tts is None:
        _tts = OrpheusTTS()
    return _tts


@router.websocket("/converse")
async def converse(ws: WebSocket):
    """Bidirectional conversation WebSocket.

    Maintains per-connection conversation history. Accepts audio or text input,
    responds with emotion metadata and streamed TTS audio.
    """
    await ws.accept()
    log.info("Conversation WebSocket connected")

    history = ConversationHistory(max_turns=20)
    audio_buffer = bytearray()
    ollama_client: httpx.AsyncClient = ws.app.state.ollama._client

    await ws.send_json({"type": "listening"})

    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type", "")

            if msg_type == "audio":
                # Accumulate audio chunks
                data = msg.get("data", "")
                if data:
                    audio_buffer.extend(base64.b64decode(data))

            elif msg_type == "end_utterance":
                # Transcribe accumulated audio → generate response
                if not audio_buffer:
                    await ws.send_json({"type": "error", "message": "No audio received"})
                    continue

                user_text = await _transcribe_audio(bytes(audio_buffer))
                audio_buffer.clear()

                if not user_text.strip():
                    await ws.send_json({"type": "error", "message": "Could not understand audio"})
                    await ws.send_json({"type": "listening"})
                    continue

                await ws.send_json({"type": "transcription", "text": user_text})
                await _generate_and_stream(ws, ollama_client, history, user_text)
                await ws.send_json({"type": "listening"})

            elif msg_type == "text":
                # Direct text input (bypass STT)
                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue

                await _generate_and_stream(ws, ollama_client, history, user_text)
                await ws.send_json({"type": "listening"})

            elif msg_type == "cancel":
                audio_buffer.clear()
                log.info("Client cancelled current utterance")

            else:
                log.debug("Unknown message type: %s", msg_type)

    except WebSocketDisconnect:
        log.info("Conversation WebSocket disconnected (turns=%d)", history.turn_count)
    except Exception:
        log.exception("Conversation WebSocket error")
        try:
            await ws.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass


async def _transcribe_audio(pcm_audio: bytes) -> str:
    """Transcribe PCM audio using Whisper STT."""
    stt = _get_stt()
    if stt is None:
        log.warning("STT unavailable, returning empty transcription")
        return ""

    try:
        return await stt.transcribe(pcm_audio)
    except Exception:
        log.exception("STT transcription failed")
        return ""


async def _generate_and_stream(
    ws: WebSocket,
    ollama_client: httpx.AsyncClient,
    history: ConversationHistory,
    user_text: str,
) -> None:
    """Generate LLM response and stream emotion + TTS audio to client."""
    try:
        response = await generate_conversation_response(
            ollama_client, history, user_text
        )
    except httpx.TimeoutException:
        await ws.send_json({"type": "error", "message": "LLM timeout"})
        return
    except (httpx.ConnectError, OllamaError) as e:
        await ws.send_json({"type": "error", "message": str(e)})
        return

    # 1. Send emotion immediately (face changes before speech)
    await ws.send_json({
        "type": "emotion",
        "emotion": response.emotion,
        "intensity": response.intensity,
    })

    # 2. Send gestures if any
    if response.gestures:
        await ws.send_json({
            "type": "gestures",
            "names": response.gestures,
        })

    # 3. Stream TTS audio
    if response.text:
        tts = _get_tts()
        chunk_index = 0
        async for chunk in tts.stream(response.text, response.emotion):
            if chunk:
                await ws.send_json({
                    "type": "audio",
                    "data": base64.b64encode(chunk).decode("ascii"),
                    "sample_rate": 16000,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

    await ws.send_json({"type": "done"})
