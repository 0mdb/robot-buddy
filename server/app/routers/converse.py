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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ai_runtime import get_stt, get_tts
from app.llm.base import LLMBusyError, LLMError, LLMTimeoutError, LLMUnavailableError
from app.llm.base import PlannerLLMBackend
from app.llm.conversation import (
    ConversationHistory,
)
from app.tts.orpheus import TTSBusyError

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/converse")
async def converse(ws: WebSocket):
    """Bidirectional conversation WebSocket.

    Maintains per-connection conversation history. Accepts audio or text input,
    responds with emotion metadata and streamed TTS audio.
    """
    robot_id = (ws.query_params.get("robot_id") or "").strip()
    if not robot_id:
        await ws.close(code=4400, reason="missing_robot_id")
        return

    session_seq = _to_int(ws.query_params.get("session_seq"))
    session_monotonic_ts_ms = _to_int(ws.query_params.get("session_monotonic_ts_ms"))

    await ws.accept()
    registry = ws.app.state.converse_registry
    old_ws = await registry.register(
        robot_id=robot_id,
        websocket=ws,
        session_seq=session_seq,
        session_monotonic_ts_ms=session_monotonic_ts_ms,
    )
    if old_ws is not None:
        try:
            await old_ws.close(code=4001, reason="replaced_by_newer_session")
        except Exception:
            pass

    log.info("Conversation WebSocket connected (robot_id=%s)", robot_id)

    history = ConversationHistory(max_turns=20)
    audio_buffer = bytearray()
    llm = ws.app.state.llm

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
                    await ws.send_json(
                        {"type": "error", "message": "No audio received"}
                    )
                    continue

                user_text = await _transcribe_audio(bytes(audio_buffer))
                audio_buffer.clear()

                if not user_text.strip():
                    await ws.send_json(
                        {"type": "error", "message": "Could not understand audio"}
                    )
                    await ws.send_json({"type": "listening"})
                    continue

                await ws.send_json({"type": "transcription", "text": user_text})
                await _generate_and_stream(ws, llm, history, user_text)
                await ws.send_json({"type": "listening"})

            elif msg_type == "text":
                # Direct text input (bypass STT)
                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue

                await _generate_and_stream(ws, llm, history, user_text)
                await ws.send_json({"type": "listening"})

            elif msg_type == "cancel":
                audio_buffer.clear()
                log.info("Client cancelled current utterance")

            else:
                log.debug("Unknown message type: %s", msg_type)

    except WebSocketDisconnect:
        log.info(
            "Conversation WebSocket disconnected (robot_id=%s turns=%d)",
            robot_id,
            history.turn_count,
        )
    except Exception:
        log.exception("Conversation WebSocket error")
        try:
            await ws.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
    finally:
        await registry.unregister(robot_id=robot_id, websocket=ws)


def _to_int(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _transcribe_audio(pcm_audio: bytes) -> str:
    """Transcribe PCM audio using Whisper STT."""
    stt = get_stt()
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
    llm: PlannerLLMBackend,
    history: ConversationHistory,
    user_text: str,
) -> None:
    """Generate LLM response and stream emotion + TTS audio to client."""
    try:
        response = await llm.generate_conversation(history, user_text)
    except LLMBusyError:
        await ws.send_json({"type": "error", "message": "llm_busy"})
        return
    except LLMTimeoutError:
        await ws.send_json({"type": "error", "message": "LLM timeout"})
        return
    except (LLMUnavailableError, LLMError) as e:
        await ws.send_json({"type": "error", "message": str(e)})
        return

    # 1. Send emotion immediately (face changes before speech)
    await ws.send_json(
        {
            "type": "emotion",
            "emotion": response.emotion,
            "intensity": response.intensity,
        }
    )

    # 2. Send gestures if any
    if response.gestures:
        await ws.send_json(
            {
                "type": "gestures",
                "names": response.gestures,
            }
        )

    # 3. Stream TTS audio
    if response.text:
        tts = get_tts()
        chunk_index = 0
        try:
            async for chunk in tts.stream(response.text, response.emotion):
                if chunk:
                    await ws.send_json(
                        {
                            "type": "audio",
                            "data": base64.b64encode(chunk).decode("ascii"),
                            "sample_rate": 16000,
                            "chunk_index": chunk_index,
                        }
                    )
                    chunk_index += 1
        except TTSBusyError:
            await ws.send_json({"type": "error", "message": "tts_busy_no_fallback"})
            return
        except Exception:
            log.exception("TTS stream failed")
            await ws.send_json({"type": "error", "message": "tts_unavailable"})
            return
        if chunk_index == 0:
            await ws.send_json({"type": "error", "message": "tts_unavailable"})
            return

    await ws.send_json({"type": "done"})
