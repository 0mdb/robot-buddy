"""FastAPI HTTP + WebSocket server for supervisor v2.

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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from supervisor_v2.api.param_registry import ParamRegistry
    from supervisor_v2.api.ws_hub import WsHub
    from supervisor_v2.core.tick_loop import TickLoop
    from supervisor_v2.core.worker_manager import WorkerManager

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static"


def create_app(
    tick: TickLoop,
    registry: ParamRegistry,
    ws_hub: WsHub,
    workers: WorkerManager,
) -> FastAPI:
    app = FastAPI(title="Robot Buddy Supervisor v2", version="2.0.0")

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
        return JSONResponse({
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
        })

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
            from supervisor_v2.core.state import Mode

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
            await workers.send_to("vision", "vision.config.update", {"mjpeg_enabled": True})
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
                await _handle_ws_cmd(msg, tick)
        except WebSocketDisconnect:
            pass
        finally:
            ws_hub.remove(ws)

    # -- Static files (must be last) -----------------------------------------

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


async def _handle_ws_cmd(msg: dict, tick: TickLoop) -> None:
    """Process incoming WebSocket command messages."""
    msg_type = msg.get("type")
    if msg_type == "twist":
        v = int(msg.get("v", 0))
        w = int(msg.get("w", 0))
        tick.set_teleop_twist(v, w)
    elif msg_type == "set_mode":
        from supervisor_v2.core.state import Mode

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
        tick.robot.face_manual_lock = bool(msg.get("enabled", False))
    elif msg_type == "face_set_flags":
        from supervisor_v2.devices.protocol import pack_face_flags

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
        from supervisor_v2.devices.expressions import EMOTION_TO_FACE_MOOD, normalize_emotion_name

        mood_id = msg.get("mood_id")
        if not isinstance(mood_id, int):
            mood_id = EMOTION_TO_FACE_MOOD.get(
                normalize_emotion_name(str(msg.get("emotion", "")) or "neutral") or "neutral"
            )
        if mood_id is None:
            return
        if tick._face and tick._face.connected:
            tick._face.send_state(
                mood_id=int(mood_id),
                intensity=int(float(msg.get("intensity", 1.0)) * 255),
                gaze_x=int(float(msg.get("gaze_x", 0.0)) * 127),
                gaze_y=int(float(msg.get("gaze_y", 0.0)) * 127),
                brightness=int(float(msg.get("brightness", 1.0)) * 255),
            )
    elif msg_type == "face_gesture":
        from supervisor_v2.devices.expressions import GESTURE_TO_FACE_ID, normalize_face_gesture_name

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
        from supervisor_v2.devices.protocol import FaceSystemMode

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
