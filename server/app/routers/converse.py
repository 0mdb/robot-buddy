"""WebSocket /converse endpoint — bidirectional conversation streaming.

Protocol:
    Client → Server:
        {"type": "audio", "data": "<base64 PCM 16kHz 16-bit mono>"}
        {"type": "end_utterance"}
        {"type": "cancel"}
        {"type": "text", "text": "..."}  # bypass STT, send text directly
        {"type": "profile", "profile": {...}}  # personality profile (PE spec §12.5)

    Server → Client:
        {"type": "listening"}
        {"type": "transcription", "text": "..."}
        {"type": "emotion", "emotion": "excited", "intensity": 0.8, "mood_reason": "..."}
        {"type": "gestures", "names": ["nod"]}
        {"type": "memory_tags", "tags": [{"tag": "likes_dinosaurs", "category": "topic"}]}
        {"type": "audio", "data": "<base64 PCM 16kHz 16-bit mono>", "chunk_index": N}
        {"type": "done"}
        {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ai_runtime import get_stt, get_tts
from app.config import settings
from app.llm.base import LLMBusyError, LLMError, LLMTimeoutError, LLMUnavailableError
from app.llm.base import PlannerLLMBackend
from app.llm.conversation import (
    ConversationHistory,
)
from app.llm.stream_parser import (
    ConversationStreamParser,
    MetadataReady,
    Sentence,
)
from app.tts.orpheus import TTSBusyError

log = logging.getLogger(__name__)

router = APIRouter()

# ── Audio buffer safety limits ───────────────────────────────────────────

# Max audio buffer size: 16 kHz * 2 bytes/sample * 30 seconds = 960 KB.
_MAX_AUDIO_BUFFER_BYTES = 16_000 * 2 * 30  # ~30 seconds of PCM 16-bit mono


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

    # Dev-only per-session generation overrides
    override_temperature = _to_float(ws.query_params.get("override_temperature"))
    override_max_output_tokens = _to_int(
        ws.query_params.get("override_max_output_tokens")
    )
    if override_temperature is not None or override_max_output_tokens is not None:
        log.info(
            "Generation overrides: temperature=%s max_output_tokens=%s",
            override_temperature,
            override_max_output_tokens,
        )

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

    # Restore stashed history from a previous connection, or start fresh.
    stashed = registry.take_stashed_history(robot_id)
    if stashed is not None:
        history = stashed
        log.info(
            "Conversation WebSocket connected (robot_id=%s, restored %d turns)",
            robot_id,
            history.turn_count,
        )
    else:
        history = ConversationHistory(max_turns=20)
        log.info(
            "Conversation WebSocket connected (robot_id=%s, new session)", robot_id
        )

    audio_buffer = bytearray()
    llm = ws.app.state.llm

    await ws.send_json({"type": "listening"})

    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type", "")

            if msg_type == "audio":
                # Accumulate audio chunks with overflow protection.
                data = msg.get("data", "")
                if data:
                    decoded = base64.b64decode(data)
                    if len(audio_buffer) + len(decoded) > _MAX_AUDIO_BUFFER_BYTES:
                        log.warning(
                            "Audio buffer overflow (%d + %d > %d), clearing",
                            len(audio_buffer),
                            len(decoded),
                            _MAX_AUDIO_BUFFER_BYTES,
                        )
                        audio_buffer.clear()
                        await ws.send_json(
                            {"type": "error", "message": "audio_buffer_overflow"}
                        )
                        await ws.send_json({"type": "listening"})
                        continue
                    audio_buffer.extend(decoded)

            elif msg_type == "end_utterance":
                # Transcribe accumulated audio → generate response
                if not audio_buffer:
                    await ws.send_json(
                        {"type": "error", "message": "No audio received"}
                    )
                    continue

                t_stt = time.monotonic()
                user_text = await _transcribe_audio(bytes(audio_buffer))
                stt_latency_ms = round((time.monotonic() - t_stt) * 1000)
                audio_buffer.clear()

                if not user_text.strip():
                    await ws.send_json(
                        {"type": "error", "message": "Could not understand audio"}
                    )
                    await ws.send_json({"type": "listening"})
                    continue

                await ws.send_json(
                    {
                        "type": "transcription",
                        "text": user_text,
                        "stt_latency_ms": stt_latency_ms,
                    }
                )
                await _generate_and_stream(
                    ws,
                    llm,
                    history,
                    user_text,
                    override_temperature=override_temperature,
                    override_max_output_tokens=override_max_output_tokens,
                )
                await ws.send_json({"type": "listening"})

            elif msg_type == "text":
                # Direct text input (bypass STT)
                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue

                await _generate_and_stream(
                    ws,
                    llm,
                    history,
                    user_text,
                    override_temperature=override_temperature,
                    override_max_output_tokens=override_max_output_tokens,
                )
                await ws.send_json({"type": "listening"})

            elif msg_type == "profile":
                # Personality profile injection (PE spec S2 §12.5)
                profile = msg.get("profile")
                if isinstance(profile, dict):
                    history.update_profile(profile)

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
        await registry.unregister(robot_id=robot_id, websocket=ws, history=history)


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


def _to_float(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    try:
        return float(raw)
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
    *,
    override_temperature: float | None = None,
    override_max_output_tokens: int | None = None,
) -> None:
    """Dispatch to the streaming or batch generator based on config."""
    if settings.llm_stream_enabled:
        await _generate_and_stream_live(
            ws,
            llm,
            history,
            user_text,
            override_temperature=override_temperature,
            override_max_output_tokens=override_max_output_tokens,
        )
    else:
        await _generate_and_stream_batch(
            ws,
            llm,
            history,
            user_text,
            override_temperature=override_temperature,
            override_max_output_tokens=override_max_output_tokens,
        )


async def _generate_and_stream_batch(
    ws: WebSocket,
    llm: PlannerLLMBackend,
    history: ConversationHistory,
    user_text: str,
    *,
    override_temperature: float | None = None,
    override_max_output_tokens: int | None = None,
) -> None:
    """Original atomic-LLM path. Kept behind RB_LLM_STREAM=0 as a rollback lever."""
    t_llm = time.monotonic()
    try:
        response = await llm.generate_conversation(
            history,
            user_text,
            override_temperature=override_temperature,
            override_max_output_tokens=override_max_output_tokens,
        )
    except LLMBusyError:
        await ws.send_json({"type": "error", "message": "llm_busy"})
        return
    except LLMTimeoutError:
        await ws.send_json({"type": "error", "message": "LLM timeout"})
        return
    except (LLMUnavailableError, LLMError) as e:
        await ws.send_json({"type": "error", "message": str(e)})
        return
    llm_latency_ms = round((time.monotonic() - t_llm) * 1000)

    emotion_msg: dict[str, object] = {
        "type": "emotion",
        "emotion": response.emotion,
        "intensity": response.intensity,
        "llm_latency_ms": llm_latency_ms,
    }
    if response.mood_reason:
        emotion_msg["mood_reason"] = response.mood_reason
    await ws.send_json(emotion_msg)

    if response.gestures:
        await ws.send_json({"type": "gestures", "names": response.gestures})

    if response.memory_tags:
        await ws.send_json({"type": "memory_tags", "tags": response.memory_tags})

    if response.text:
        await ws.send_json({"type": "assistant_text", "text": response.text})

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


async def _generate_and_stream_live(
    ws: WebSocket,
    llm: PlannerLLMBackend,
    history: ConversationHistory,
    user_text: str,
    *,
    override_temperature: float | None = None,
    override_max_output_tokens: int | None = None,
) -> None:
    """Streaming LLM → per-sentence TTS pipeline.

    Producer drives the LLM token stream through a ``ConversationStreamParser``.
    On ``MetadataReady`` it emits the usual WS metadata messages immediately.
    On each ``Sentence`` it spawns a TTS runner (bounded to depth-2 concurrency
    via ``_TTS_PIPELINE_DEPTH``) and hands a chunk-queue to the consumer, which
    drains them strictly in order and forwards PCM to the WS. One
    ``assistant_text`` + ``done`` is sent at end of turn — matching the batch
    contract, so supervisor/dashboard code is unchanged.
    """
    parser = ConversationStreamParser()
    tts = get_tts()
    t_start = time.monotonic()

    llm_latency_ms: int | None = None
    first_audio_latency_ms: int | None = None
    metadata_seen = False
    emotion_for_tts = "neutral"

    # tts_queues: FIFO of per-sentence chunk queues. Size 2 enforces the
    # pipeline-depth-2 cap recommended by review — producer blocks when
    # two TTS syntheses are already in flight, keeping us under the Orpheus
    # busy threshold.
    sentence_chunk_queues: asyncio.Queue[asyncio.Queue[bytes | None] | None] = (
        asyncio.Queue(maxsize=_TTS_PIPELINE_DEPTH)
    )

    async def _spawn_tts_runner(
        sentence: str, emotion: str, tg: asyncio.TaskGroup
    ) -> asyncio.Queue[bytes | None]:
        q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=_TTS_CHUNK_BUFFER)

        async def _runner() -> None:
            try:
                async for chunk in tts.stream(sentence, emotion):
                    if chunk:
                        await q.put(chunk)
            finally:
                await q.put(None)

        tg.create_task(_runner())
        return q

    # Limit TTS calls to 2 per turn: the FIRST natural sentence early (for
    # latency), then one coalesced call for everything after. Each Orpheus
    # call re-applies the `<happy>` prosody tag (apply_prosody_tag in
    # orpheus.py), and on short inputs the tokenizer occasionally vocalises
    # that tag rather than treating it as a control — the "happy happy"
    # artifact. Two calls keeps the tag count down and gives the second
    # call enough content for natural prosody.
    sent_first = False
    coalesce_buf: list[str] = []

    async def _dispatch_tts(text: str, tg: asyncio.TaskGroup) -> None:
        if not text:
            return
        log.info("tts dispatch: emotion=%s len=%d", emotion_for_tts, len(text))
        q = await _spawn_tts_runner(text, emotion_for_tts, tg)
        await sentence_chunk_queues.put(q)

    async def _produce(tg: asyncio.TaskGroup) -> None:
        nonlocal metadata_seen, emotion_for_tts, llm_latency_ms, sent_first

        stream = llm.stream_conversation(
            history,
            user_text,
            override_temperature=override_temperature,
            override_max_output_tokens=override_max_output_tokens,
        )
        try:
            async for delta in stream:
                for event in parser.feed(delta):
                    if isinstance(event, MetadataReady):
                        metadata_seen = True
                        resp = event.response
                        emotion_for_tts = resp.emotion
                        llm_latency_ms = round((time.monotonic() - t_start) * 1000)
                        emotion_msg: dict[str, object] = {
                            "type": "emotion",
                            "emotion": resp.emotion,
                            "intensity": resp.intensity,
                            "llm_latency_ms": llm_latency_ms,
                        }
                        if resp.mood_reason:
                            emotion_msg["mood_reason"] = resp.mood_reason
                        await ws.send_json(emotion_msg)
                        if resp.gestures:
                            await ws.send_json(
                                {"type": "gestures", "names": resp.gestures}
                            )
                        if resp.memory_tags:
                            await ws.send_json(
                                {"type": "memory_tags", "tags": resp.memory_tags}
                            )
                    elif isinstance(event, Sentence):
                        if not sent_first:
                            await _dispatch_tts(event.text, tg)
                            sent_first = True
                        else:
                            coalesce_buf.append(event.text)
        finally:
            # Flush the final buffered fragment (short-sentence tail).
            for event in parser.close():
                if isinstance(event, Sentence):
                    if not sent_first:
                        await _dispatch_tts(event.text, tg)
                        sent_first = True
                    else:
                        coalesce_buf.append(event.text)
            # Coalesce everything after the first sentence into a single
            # TTS call.
            if coalesce_buf:
                await _dispatch_tts(" ".join(coalesce_buf), tg)
                coalesce_buf.clear()
            # EOF signal to consumer. Guarded so we don't deadlock if the
            # group is already tearing down.
            try:
                await sentence_chunk_queues.put(None)
            except (asyncio.CancelledError, RuntimeError):
                raise

    async def _consume() -> None:
        nonlocal first_audio_latency_ms
        chunk_index = 0
        while True:
            q = await sentence_chunk_queues.get()
            if q is None:
                return
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                if first_audio_latency_ms is None:
                    first_audio_latency_ms = round((time.monotonic() - t_start) * 1000)
                await ws.send_json(
                    {
                        "type": "audio",
                        "data": base64.b64encode(chunk).decode("ascii"),
                        "sample_rate": 16000,
                        "chunk_index": chunk_index,
                    }
                )
                chunk_index += 1

    error_message: str | None = None
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_produce(tg))
            tg.create_task(_consume())
    except* LLMBusyError:
        error_message = "llm_busy"
    except* LLMTimeoutError:
        error_message = "LLM timeout"
    except* (LLMUnavailableError, LLMError) as eg:
        error_message = str(next(iter(eg.exceptions))) if eg.exceptions else "llm_error"
    except* TTSBusyError:
        error_message = "tts_busy_no_fallback"
    except* Exception:
        log.exception("Streaming conversation failed")
        error_message = "internal_error"

    if error_message is not None:
        await ws.send_json({"type": "error", "message": error_message})
        return

    full_text = parser.full_text()

    if metadata_seen:
        history.add_assistant(full_text, emotion=emotion_for_tts)

    if full_text:
        await ws.send_json({"type": "assistant_text", "text": full_text})

    if first_audio_latency_ms is not None and llm_latency_ms is not None:
        log.info(
            "streaming turn: llm=%dms first_audio=%dms text_len=%d",
            llm_latency_ms,
            first_audio_latency_ms,
            len(full_text),
        )

    await ws.send_json({"type": "done"})


# Depth-2 cap on concurrent TTS syntheses per turn. Must not exceed
# settings.tts_busy_queue_threshold or Orpheus will shed to espeak mid-turn.
_TTS_PIPELINE_DEPTH = 2
# Per-sentence chunk queue size. 32 × 10ms = 320ms of audio buffered per
# runner — comfortable without starving the Orpheus internal queue.
_TTS_CHUNK_BUFFER = 32
