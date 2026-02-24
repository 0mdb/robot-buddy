"""FastAPI HTTP + WebSocket server for the supervisor.

Adapts v1 http_server.py for the v2 architecture:
- State from TickLoop (RobotState + WorldState) instead of Runtime
- Worker commands via WorkerManager (not direct methods)
- MJPEG from vision worker (base64 frames via NDJSON, not VisionProcess)
- New debug endpoints: /debug/workers, /debug/clocks
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING


from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from supervisor.api.param_persistence import load_params, on_param_changed
from supervisor.messages.types import TTS_CMD_SET_MUTE, TTS_CMD_SET_VOLUME
from supervisor.vision.mask_store import (
    default_mask,
    load_mask,
    save_mask_atomic,
    validate_and_normalize_mask,
)

if TYPE_CHECKING:
    from supervisor.api.conversation_capture import ConversationCapture
    from supervisor.api.param_registry import ParamRegistry
    from supervisor.api.protocol_capture import ProtocolCapture
    from supervisor.api.ws_hub import WsHub
    from supervisor.core.tick_loop import TickLoop
    from supervisor.core.worker_manager import WorkerManager

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static"
VISION_MASK_PATH = Path("./data/vision_mask.json")


# -- WebSocket log broadcaster ------------------------------------------------


class WebSocketLogBroadcaster(logging.Handler):
    """Logging handler that broadcasts JSON log entries to connected WS clients.

    Supports multiple concurrent clients (broadcast, not single-consumer queue).
    Each client gets its own asyncio.Queue so slow clients don't block others.
    """

    def __init__(self, maxsize: int = 256) -> None:
        super().__init__()
        self._clients: set[asyncio.Queue[str]] = set()
        self._maxsize = maxsize

    def add_client(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._maxsize)
        self._clients.add(q)
        return q

    def remove_client(self, q: asyncio.Queue[str]) -> None:
        self._clients.discard(q)

    def emit(self, record: logging.LogRecord) -> None:
        entry = json.dumps(
            {
                "ts": record.created,
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
        )
        for q in list(self._clients):
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                # Drop oldest entry to make room
                try:
                    q.get_nowait()
                    q.put_nowait(entry)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


_log_broadcaster = WebSocketLogBroadcaster()


def install_log_handler() -> None:
    """Attach the broadcast handler to the root logger. Call once at startup."""
    root = logging.getLogger()
    # Avoid duplicate installs
    if _log_broadcaster not in root.handlers:
        _log_broadcaster.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(_log_broadcaster)


# -- Cache-Control middleware --------------------------------------------------


class NoCacheIndexMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control: no-cache on index.html so browsers pick up new builds.

    Vite's hashed asset filenames (index-D3fX.js) are safe to cache indefinitely,
    but index.html must be fetched fresh so the browser loads new asset hashes.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith("/index.html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


def create_app(
    tick: TickLoop,
    registry: ParamRegistry,
    ws_hub: WsHub,
    workers: WorkerManager,
    capture: ProtocolCapture | None = None,
    conv_capture: ConversationCapture | None = None,
    tts_endpoint: str = "",
) -> FastAPI:
    import psutil

    app = FastAPI(title="Robot Buddy Supervisor", version="2.0.0")
    app.add_middleware(NoCacheIndexMiddleware)
    install_log_handler()

    # Prime psutil CPU measurement (first call always returns 0.0)
    psutil.cpu_percent(interval=None)

    # -- Param persistence + worker notifications ----------------------------
    load_params(registry)
    registry.on_change(on_param_changed)

    def _on_param_change(name: str, value: object) -> None:
        if name == "tts.speaker_volume":
            asyncio.ensure_future(
                workers.send_to("tts", TTS_CMD_SET_VOLUME, {"volume": value})
            )

    registry.on_change(_on_param_change)

    # -- WebSocket logs ------------------------------------------------------

    @app.websocket("/ws/logs")
    async def websocket_logs(ws: WebSocket):
        await ws.accept()
        q = _log_broadcaster.add_client()
        try:
            while True:
                entry = await q.get()
                await ws.send_text(entry)
        except WebSocketDisconnect:
            pass
        finally:
            _log_broadcaster.remove_client(q)

    # -- WebSocket protocol capture ------------------------------------------

    if capture is not None:

        @app.websocket("/ws/protocol")
        async def websocket_protocol(ws: WebSocket):
            await ws.accept()
            q = capture.add_client()
            try:
                while True:
                    entry = await q.get()
                    await ws.send_text(entry)
            except WebSocketDisconnect:
                pass
            finally:
                capture.remove_client(q)

    # -- WebSocket conversation capture ----------------------------------------

    if conv_capture is not None:

        @app.websocket("/ws/conversation")
        async def websocket_conversation(ws: WebSocket):
            await ws.accept()
            q = conv_capture.add_client()
            try:
                while True:
                    entry = await q.get()
                    await ws.send_text(entry)
            except WebSocketDisconnect:
                pass
            finally:
                conv_capture.remove_client(q)

    # -- HTTP endpoints ------------------------------------------------------

    @app.get("/status")
    async def get_status():
        combined = tick.robot.to_dict()
        combined.update(tick.world.to_dict())
        return JSONResponse(combined)

    @app.get("/debug/devices")
    async def get_device_debug():
        return JSONResponse(tick.debug_devices())

    @app.get("/debug/planner")
    async def get_planner_debug():
        return JSONResponse(tick.debug_planner())

    @app.get("/debug/workers")
    async def get_worker_debug():
        return JSONResponse(workers.worker_snapshot())

    @app.get("/debug/clocks")
    async def get_clock_debug():
        return JSONResponse(
            {
                "reflex": {
                    "state": tick.robot.reflex_clock.state,
                    "offset_ns": tick.robot.reflex_clock.offset_ns,
                    "rtt_min_us": tick.robot.reflex_clock.rtt_min_us,
                    "drift_us_per_s": tick.robot.reflex_clock.drift_us_per_s,
                    "samples": tick.robot.reflex_clock.samples,
                },
                "face": {
                    "state": tick.robot.face_clock.state,
                    "offset_ns": tick.robot.face_clock.offset_ns,
                    "rtt_min_us": tick.robot.face_clock.rtt_min_us,
                    "drift_us_per_s": tick.robot.face_clock.drift_us_per_s,
                    "samples": tick.robot.face_clock.samples,
                },
            }
        )

    @app.get("/debug/system")
    async def get_system_debug():
        import time

        cpu_temp = None
        try:
            temps = psutil.sensors_temperatures()
            if "cpu_thermal" in temps:
                cpu_temp = temps["cpu_thermal"][0].current
            elif temps:
                first = next(iter(temps.values()))
                cpu_temp = first[0].current if first else None
        except Exception:
            pass

        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        freq = psutil.cpu_freq()
        return JSONResponse(
            {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "cpu_count": psutil.cpu_count(),
                "cpu_freq_mhz": round(freq.current) if freq else None,
                "cpu_temp_c": round(cpu_temp, 1) if cpu_temp is not None else None,
                "mem_total_mb": round(vm.total / 1048576),
                "mem_used_mb": round(vm.used / 1048576),
                "mem_percent": vm.percent,
                "disk_total_gb": round(disk.total / 1073741824, 1),
                "disk_used_gb": round(disk.used / 1073741824, 1),
                "disk_percent": disk.percent,
                "load_avg": list(psutil.getloadavg()),
                "uptime_s": round(time.monotonic()),
            }
        )

    @app.get("/params")
    async def get_params():
        return JSONResponse(registry.get_all())

    @app.post("/params")
    async def set_params(body: dict):
        items = body.get("items", {})
        if not items:
            return JSONResponse({"error": "no items"}, status_code=400)
        results = registry.bulk_set(items)
        status_code = 200 if all(ok for ok, _ in results.values()) else 422
        return JSONResponse(
            {k: {"ok": ok, "reason": r} for k, (ok, r) in results.items()},
            status_code=status_code,
        )

    @app.post("/actions")
    async def post_action(body: dict):
        action = body.get("action")
        if action == "set_mode":
            from supervisor.core.state import Mode

            mode_str = body.get("mode", "").upper()
            try:
                Mode(mode_str)
            except ValueError:
                return JSONResponse(
                    {"ok": False, "reason": f"unknown mode: {mode_str}"},
                    status_code=400,
                )
            ok, reason = tick.request_mode(mode_str)
            return JSONResponse({"ok": ok, "reason": reason})
        elif action == "e_stop":
            if tick._reflex and tick._reflex.connected:
                tick._reflex.send_estop()
            return JSONResponse({"ok": True, "reason": "e_stop sent"})
        elif action == "clear_e_stop":
            ok, reason = tick.clear_error()
            return JSONResponse({"ok": ok, "reason": reason})
        else:
            return JSONResponse(
                {"ok": False, "reason": f"unknown action: {action}"}, status_code=400
            )

    # -- Personality memory (PE spec S2 §8.5) --------------------------------

    @app.get("/api/personality/memory")
    async def get_personality_memory():
        """Parent memory viewer — returns all stored memory entries."""
        # Get consent status from worker health snapshot
        consent = False
        if workers.worker_alive("personality"):
            snap = workers.worker_snapshot().get("personality", {})
            consent = snap.get("health", {}).get("memory_consent", False)

        # Read memory file from default path
        memory_path = Path("./data/personality_memory.json")
        if not memory_path.exists():
            return JSONResponse(
                {"version": 1, "entries": [], "entry_count": 0, "consent": consent}
            )
        try:
            data = json.loads(memory_path.read_text())
            data["consent"] = consent
            data["entry_count"] = len(data.get("entries", []))
            return JSONResponse(data)
        except Exception as e:
            log.warning("failed to read memory file: %s", e)
            return JSONResponse({"entries": [], "entry_count": 0, "consent": consent})

    @app.delete("/api/personality/memory")
    async def delete_personality_memory():
        """Parent 'Forget Everything' — wipe all memory entries."""
        from supervisor.messages.types import PERSONALITY_CMD_RESET_MEMORY

        if workers.worker_alive("personality"):
            asyncio.ensure_future(
                workers.send_to("personality", PERSONALITY_CMD_RESET_MEMORY, {})
            )
        return JSONResponse({"ok": True})

    # -- Vision masks (dashboard mask editor) --------------------------------

    @app.get("/api/vision/mask")
    async def get_vision_mask():
        return JSONResponse(load_mask(VISION_MASK_PATH))

    @app.put("/api/vision/mask")
    async def put_vision_mask(body: dict):
        try:
            mask = validate_and_normalize_mask(body)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=422)

        try:
            save_mask_atomic(VISION_MASK_PATH, mask)
        except Exception as e:
            log.warning("failed to save vision mask: %s", e)
            return JSONResponse({"error": "failed to save mask"}, status_code=500)

        if workers.worker_alive("vision"):
            await workers.send_to("vision", "vision.config.update", {"mask": mask})

        return JSONResponse(mask)

    @app.delete("/api/vision/mask")
    async def delete_vision_mask():
        mask = default_mask()
        try:
            save_mask_atomic(VISION_MASK_PATH, mask)
        except Exception as e:
            log.warning("failed to reset vision mask: %s", e)
            return JSONResponse({"error": "failed to reset mask"}, status_code=500)

        if workers.worker_alive("vision"):
            await workers.send_to("vision", "vision.config.update", {"mask": mask})

        return JSONResponse({"ok": True, "mask": mask})

    # -- MJPEG video stream --------------------------------------------------

    _video_clients: int = 0

    @app.get("/video")
    async def video_feed():
        nonlocal _video_clients

        if not workers.worker_alive("vision"):
            return JSONResponse({"error": "vision not available"}, status_code=503)

        async def generate():
            nonlocal _video_clients
            _video_clients += 1
            # Enable MJPEG on vision worker
            await workers.send_to(
                "vision", "vision.config.update", {"mjpeg_enabled": True}
            )
            log.info("video: client connected (%d active)", _video_clients)
            try:
                last_seq = 0
                while True:
                    b64 = tick.world.latest_jpeg_b64
                    seq = tick.world.vision_frame_seq
                    if b64 and seq != last_seq:
                        last_seq = seq
                        frame = base64.b64decode(b64)
                        yield (
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + frame
                            + b"\r\n"
                        )
                    await asyncio.sleep(0.1)  # 10 FPS max
            finally:
                _video_clients -= 1
                if _video_clients <= 0:
                    _video_clients = 0
                    await workers.send_to(
                        "vision", "vision.config.update", {"mjpeg_enabled": False}
                    )
                log.info("video: client disconnected (%d active)", _video_clients)

        return StreamingResponse(
            generate(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    # -- WebSocket telemetry + commands --------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        ws_hub.add(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await _handle_ws_cmd(msg, tick, conv_capture, tts_endpoint)
        except WebSocketDisconnect:
            pass
        finally:
            ws_hub.remove(ws)

    # -- Static files (must be last) -----------------------------------------

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


async def _handle_ws_cmd(
    msg: dict,
    tick: TickLoop,
    conv_capture: ConversationCapture | None = None,
    tts_endpoint: str = "",
) -> None:
    """Process incoming WebSocket command messages."""
    msg_type = msg.get("type")
    if msg_type == "twist":
        v = int(msg.get("v", 0))
        w = int(msg.get("w", 0))
        tick.set_teleop_twist(v, w)
    elif msg_type == "set_mode":
        from supervisor.core.state import Mode

        try:
            target = Mode(msg.get("mode", "").upper())
            tick.request_mode(target.value)
        except ValueError:
            pass
    elif msg_type == "e_stop":
        if tick._reflex and tick._reflex.connected:
            tick._reflex.send_estop()
    elif msg_type == "clear":
        tick.clear_error()
    elif msg_type == "face_manual_lock":
        from supervisor.devices.protocol import (
            FACE_FLAG_IDLE_WANDER,
            FACE_FLAGS_ALL,
        )

        enabled = bool(msg.get("enabled", False))
        tick.robot.face_manual_lock = enabled
        if enabled and tick._face and tick._face.connected:
            # Disable idle_wander so MCU doesn't override commanded gaze
            flags = tick.robot.face_manual_flags or FACE_FLAGS_ALL
            flags &= ~FACE_FLAG_IDLE_WANDER
            tick.robot.face_manual_flags = flags
            tick._face.send_flags(flags)
    elif msg_type == "face_set_flags":
        from supervisor.devices.protocol import pack_face_flags

        flags = pack_face_flags(
            idle_wander=bool(msg.get("idle_wander", True)),
            autoblink=bool(msg.get("autoblink", True)),
            solid_eye=bool(msg.get("solid_eye", True)),
            show_mouth=bool(msg.get("show_mouth", True)),
            edge_glow=bool(msg.get("edge_glow", True)),
            sparkle=bool(msg.get("sparkle", True)),
            afterglow=bool(msg.get("afterglow", True)),
        )
        tick.robot.face_manual_flags = flags
        if tick._face and tick._face.connected:
            tick._face.send_flags(flags)
    elif msg_type == "face_set_state":
        from supervisor.devices.expressions import (
            EMOTION_TO_FACE_MOOD,
            normalize_emotion_name,
        )

        mood_id = msg.get("mood_id")
        if not isinstance(mood_id, int):
            mood_id = EMOTION_TO_FACE_MOOD.get(
                normalize_emotion_name(str(msg.get("emotion", "")) or "neutral")
                or "neutral"
            )
        if mood_id is None:
            return
        if tick._face and tick._face.connected:
            tick._face.send_state(
                emotion_id=int(mood_id),
                intensity=float(msg.get("intensity", 1.0)),
                gaze_x=float(msg.get("gaze_x", 0.0)),
                gaze_y=float(msg.get("gaze_y", 0.0)),
                brightness=float(msg.get("brightness", 1.0)),
            )
    elif msg_type == "face_gesture":
        from supervisor.devices.expressions import (
            GESTURE_TO_FACE_ID,
            normalize_face_gesture_name,
        )

        gesture_id = msg.get("gesture_id")
        if not isinstance(gesture_id, int):
            name = normalize_face_gesture_name(str(msg.get("name", "")))
            if not name:
                return
            gesture_id = GESTURE_TO_FACE_ID.get(name)
        if gesture_id is None:
            return
        if tick._face and tick._face.connected:
            tick._face.send_gesture(
                int(gesture_id),
                duration_ms=int(msg.get("duration_ms", 0)),
            )
    elif msg_type == "face_set_system":
        from supervisor.devices.protocol import FaceSystemMode

        raw_mode = msg.get("mode", FaceSystemMode.NONE)
        mode_u8: int | None = None
        if isinstance(raw_mode, int):
            mode_u8 = raw_mode
        else:
            key = str(raw_mode or "").strip().upper()
            if key == "ERROR":
                key = "ERROR_DISPLAY"
            if key in FaceSystemMode.__members__:
                mode_u8 = int(FaceSystemMode[key])
        if mode_u8 is None:
            return
        if tick._face and tick._face.connected:
            tick._face.send_system_mode(mode_u8, param=int(msg.get("param", 0)))
    elif msg_type == "face_set_talking":
        if tick._face and tick._face.connected:
            tick._face.send_talking(
                bool(msg.get("talking", False)),
                energy=int(msg.get("energy", 0)),
            )
    # -- Conversation commands -----------------------------------------------
    elif msg_type == "conversation.start":
        trigger = str(msg.get("trigger", "dashboard"))
        tick._start_conversation(trigger)
    elif msg_type == "conversation.cancel":
        from supervisor.devices.protocol import FaceConvState

        if tick.world.session_id:
            tick._conv.set_state(FaceConvState.DONE)
            tick._end_conversation()
    elif msg_type == "conversation.end_utterance":
        if tick.world.session_id:
            from supervisor.devices.protocol import FaceConvState

            tick._conv.set_state(FaceConvState.THINKING)
            asyncio.ensure_future(
                tick._workers.send_to(
                    "ai",
                    "ai.cmd.end_utterance",
                    {"session_id": tick.world.session_id},
                )
            )
            asyncio.ensure_future(
                tick._workers.send_to("ear", "ear.cmd.stop_listening")
            )
            tick.robot.face_listening = False
    elif msg_type == "conversation.send_text":
        text = str(msg.get("text", "")).strip()
        if text and tick.world.session_id:
            asyncio.ensure_future(
                tick._workers.send_to(
                    "ai",
                    "ai.cmd.send_text",
                    {"text": text, "session_id": tick.world.session_id},
                )
            )
    elif msg_type == "conversation.config":
        if tick.world.session_id:
            asyncio.ensure_future(
                tick._workers.send_to(
                    "ai",
                    "ai.cmd.config",
                    {
                        "stream_audio": msg.get("stream_audio", True),
                        "stream_text": msg.get("stream_text", True),
                    },
                )
            )
    elif msg_type == "tts.set_mute":
        asyncio.ensure_future(
            tick._workers.send_to(
                "tts",
                TTS_CMD_SET_MUTE,
                {
                    "muted": bool(msg.get("muted", False)),
                    "mute_chimes": bool(msg.get("mute_chimes", False)),
                },
            )
        )
    # -- TTS benchmark --------------------------------------------------------
    elif msg_type == "tts_benchmark.start":
        if tts_endpoint and conv_capture:
            from supervisor.api.tts_benchmark import start_benchmark

            started = start_benchmark(
                tts_endpoint,
                conv_capture,
                session_active=bool(tick.world.session_id),
            )
            if not started:
                log.warning("tts_benchmark.start rejected")
    # -- Ear workbench --------------------------------------------------------
    elif msg_type == "ear.stream_scores":
        asyncio.ensure_future(
            tick._workers.send_to(
                "ear",
                "ear.cmd.stream_scores",
                {"enabled": bool(msg.get("enabled", False))},
            )
        )
    elif msg_type == "ear.set_threshold":
        asyncio.ensure_future(
            tick._workers.send_to(
                "ear",
                "ear.cmd.set_threshold",
                {"threshold": float(msg.get("threshold", 0.5))},
            )
        )
    # -- Personality commands ---------------------------------------------------
    elif msg_type == "personality.override_affect":
        from supervisor.messages.types import PERSONALITY_CMD_OVERRIDE_AFFECT

        asyncio.ensure_future(
            tick._workers.send_to(
                "personality",
                PERSONALITY_CMD_OVERRIDE_AFFECT,
                {
                    "valence": float(msg.get("valence", 0.0)),
                    "arousal": float(msg.get("arousal", 0.0)),
                    "magnitude": float(msg.get("magnitude", 0.5)),
                },
            )
        )
    elif msg_type == "personality.set_guardrail":
        from supervisor.messages.types import PERSONALITY_CMD_SET_GUARDRAIL

        payload: dict[str, object] = {}
        for key in (
            "negative_duration_caps",
            "negative_intensity_caps",
            "context_gate",
        ):
            if key in msg:
                payload[key] = bool(msg[key])
        for key in ("session_time_limit_s", "daily_time_limit_s"):
            if key in msg:
                payload[key] = float(msg[key])
        if msg.get("reset_daily"):
            payload["reset_daily"] = True
        if payload:
            asyncio.ensure_future(
                tick._workers.send_to(
                    "personality", PERSONALITY_CMD_SET_GUARDRAIL, payload
                )
            )
    # -- Generation override commands (dev-only) --------------------------------
    elif msg_type == "ai.set_generation_overrides":
        from supervisor.messages.types import AI_CMD_SET_GENERATION_OVERRIDES

        override_payload: dict[str, object] = {}
        if "temperature" in msg:
            override_payload["temperature"] = float(msg["temperature"])
        if "max_output_tokens" in msg:
            override_payload["max_output_tokens"] = int(msg["max_output_tokens"])
        if override_payload:
            asyncio.ensure_future(
                tick._workers.send_to(
                    "ai", AI_CMD_SET_GENERATION_OVERRIDES, override_payload
                )
            )
    elif msg_type == "ai.clear_generation_overrides":
        from supervisor.messages.types import AI_CMD_CLEAR_GENERATION_OVERRIDES

        asyncio.ensure_future(
            tick._workers.send_to("ai", AI_CMD_CLEAR_GENERATION_OVERRIDES, {})
        )
