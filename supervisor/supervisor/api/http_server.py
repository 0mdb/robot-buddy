"""FastAPI HTTP + WebSocket server."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from supervisor.api.param_registry import ParamRegistry
    from supervisor.api.ws_hub import WsHub
    from supervisor.inputs.camera_vision import VisionProcess
    from supervisor.runtime import Runtime
from supervisor.logging.handler import log_queue

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent.parent / "static"


def create_app(
    runtime: Runtime,
    registry: ParamRegistry,
    ws_hub: WsHub,
    vision: VisionProcess | None = None,
) -> FastAPI:
    app = FastAPI(title="Robot Buddy Supervisor", version="0.1.0")

    # -- WebSocket logs ------------------------------------------------------
    @app.websocket("/ws/logs")
    async def websocket_logs(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                log_entry = await log_queue.get()
                await ws.send_text(log_entry)
                log_queue.task_done()
        except WebSocketDisconnect:
            pass
        finally:
            # No special cleanup needed
            pass

    # -- HTTP endpoints ------------------------------------------------------

    @app.get("/status")
    async def get_status():
        return JSONResponse(runtime.state.to_dict())

    @app.get("/debug/devices")
    async def get_device_debug():
        return JSONResponse(runtime.debug_devices())

    @app.get("/debug/planner")
    async def get_planner_debug():
        return JSONResponse(runtime.debug_planner())

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
            from supervisor.state.datatypes import Mode

            mode_str = body.get("mode", "").upper()
            try:
                target = Mode(mode_str)
            except ValueError:
                return JSONResponse(
                    {"ok": False, "reason": f"unknown mode: {mode_str}"},
                    status_code=400,
                )
            ok, reason = runtime.request_mode(target)
            return JSONResponse({"ok": ok, "reason": reason})
        elif action == "e_stop":
            runtime.request_estop()
            return JSONResponse({"ok": True, "reason": "e_stop sent"})
        elif action == "clear_e_stop":
            ok, reason = runtime.request_clear()
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
        if not vision:
            return JSONResponse({"error": "vision not available"}, status_code=503)

        async def generate():
            nonlocal _video_clients
            _video_clients += 1
            vision.set_mjpeg_enabled(True)
            log.info("video: client connected (%d active)", _video_clients)
            try:
                while True:
                    frame = vision.latest_frame()
                    if frame:
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
                    vision.set_mjpeg_enabled(False)
                log.info("video: client disconnected (%d active)", _video_clients)

        return StreamingResponse(
            generate(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    # -- WebSocket -----------------------------------------------------------

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
                _handle_ws_cmd(msg, runtime)
        except WebSocketDisconnect:
            pass
        finally:
            ws_hub.remove(ws)

    # -- Static files (must be last) -----------------------------------------

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


def _handle_ws_cmd(msg: dict, runtime: Runtime) -> None:
    """Process incoming WebSocket command messages."""
    msg_type = msg.get("type")
    if msg_type == "twist":
        v = int(msg.get("v", 0))
        w = int(msg.get("w", 0))
        runtime.set_teleop_twist(v, w)
    elif msg_type == "set_mode":
        from supervisor.state.datatypes import Mode

        try:
            target = Mode(msg.get("mode", "").upper())
            runtime.request_mode(target)
        except ValueError:
            pass
    elif msg_type == "e_stop":
        runtime.request_estop()
    elif msg_type == "clear":
        runtime.request_clear()
