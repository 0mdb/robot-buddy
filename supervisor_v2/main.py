"""Supervisor v2 entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Robot Buddy Supervisor v2")
    p.add_argument("--mock", action="store_true", help="Use mock Reflex MCU (no hardware)")
    p.add_argument("--port", default=None, help="Reflex serial port (default: /dev/robot_reflex)")
    p.add_argument("--face-port", default=None, help="Face serial port (default: /dev/robot_face)")
    p.add_argument("--no-face", action="store_true", help="Disable Face MCU")
    p.add_argument("--no-vision", action="store_true", help="Disable vision worker")
    p.add_argument("--no-planner", action="store_true", help="Disable AI/planner worker")
    p.add_argument("--http-port", type=int, default=8080, help="HTTP server port")
    p.add_argument("--planner-api", default=None, help="Planner server base URL")
    p.add_argument("--robot-id", default=os.environ.get("ROBOT_ID", ""), help="Robot ID")
    p.add_argument("--config", default=None, help="YAML config file path")
    p.add_argument("--log-level", default="INFO", help="Log level")
    p.add_argument("--usb-speaker-device", default="default", help="ALSA speaker device")
    p.add_argument("--usb-mic-device", default="default", help="ALSA mic device")
    return p.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    import uvicorn

    from supervisor_v2.api.http_server import create_app
    from supervisor_v2.api.param_registry import create_default_registry
    from supervisor_v2.api.ws_hub import WsHub
    from supervisor_v2.config import load_config
    from supervisor_v2.core.tick_loop import TickLoop
    from supervisor_v2.core.worker_manager import WorkerManager
    from supervisor_v2.devices.face_client import FaceClient
    from supervisor_v2.devices.reflex_client import ReflexClient
    from supervisor_v2.io.serial_transport import SerialTransport

    cfg = load_config(args.config)

    # Apply CLI overrides
    if args.port:
        cfg.serial.reflex_port = args.port
    if args.face_port:
        cfg.serial.face_port = args.face_port
    if args.mock:
        cfg.mock = True
    cfg.network.http_port = args.http_port

    mock_reflex = None
    reflex = None
    face = None
    http_server = None

    try:
        # ── Reflex MCU ───────────────────────────────────────────
        if cfg.mock:
            from supervisor_v2.mock.mock_reflex import MockReflex
            mock_reflex = MockReflex()
            mock_reflex.start()
            reflex_port = mock_reflex.device_path
            log.info("mock reflex on %s", reflex_port)
        else:
            reflex_port = cfg.serial.reflex_port

        reflex_transport = SerialTransport(
            port=reflex_port, baudrate=cfg.serial.baudrate, label="reflex"
        )
        reflex = ReflexClient(reflex_transport)
        await reflex_transport.start()

        # ── Face MCU ─────────────────────────────────────────────
        if not args.no_face:
            face_transport = SerialTransport(
                port=cfg.serial.face_port, baudrate=cfg.serial.baudrate, label="face"
            )
            face = FaceClient(face_transport)
            await face_transport.start()

        # ── API components ─────────────────────────────────────
        registry = create_default_registry()
        ws_hub = WsHub()

        # ── Worker Manager ───────────────────────────────────────
        planner_enabled = bool(args.robot_id and args.planner_api and not args.no_planner)

        # We create the tick loop first so we can use its on_worker_event as callback
        workers = WorkerManager(
            on_event=lambda name, env: tick.on_worker_event(name, env),
            heartbeat_timeout_s=cfg.workers.heartbeat_timeout_s,
            max_restarts=cfg.workers.max_restarts,
        )

        # Register workers
        if not args.no_vision:
            workers.register("vision", "supervisor_v2.workers.vision_worker")

        if planner_enabled:
            workers.register("tts", "supervisor_v2.workers.tts_worker")
            workers.register("ai", "supervisor_v2.workers.ai_worker")

        # ── Tick Loop ────────────────────────────────────────────
        tick = TickLoop(
            reflex=reflex,
            face=face,
            workers=workers,
            on_telemetry=ws_hub.broadcast_telemetry,
            planner_enabled=planner_enabled,
            robot_id=args.robot_id,
        )

        # ── HTTP server ──────────────────────────────────────────
        app = create_app(tick, registry, ws_hub, workers)
        http_config = uvicorn.Config(
            app,
            host=cfg.network.host,
            port=cfg.network.http_port,
            log_level="warning",
        )
        http_server = uvicorn.Server(http_config)

        # ── Start everything ─────────────────────────────────────
        await workers.start()

        # Send init configs to workers
        if not args.no_vision:
            await workers.send_to("vision", "vision.config.update", {
                "mjpeg_enabled": False,
            })

        if planner_enabled:
            tts_init = {
                "audio_mode": cfg.workers.audio_mode,
                "mic_socket_path": workers.mic_socket_path,
                "spk_socket_path": workers.spk_socket_path,
                "speaker_device": args.usb_speaker_device,
                "mic_device": args.usb_mic_device,
                "tts_endpoint": args.planner_api + "/tts" if args.planner_api else "",
            }
            await workers.send_to("tts", "tts.config.init", tts_init)

            ai_init = {
                "audio_mode": cfg.workers.audio_mode,
                "mic_socket_path": workers.mic_socket_path,
                "spk_socket_path": workers.spk_socket_path,
                "server_base_url": args.planner_api or "",
                "robot_id": args.robot_id,
            }
            await workers.send_to("ai", "ai.config.init", ai_init)

        # Wire param changes to vision worker
        def _on_param_change(name: str, value: object) -> None:
            if name.startswith("vision.") and workers.worker_alive("vision"):
                asyncio.ensure_future(
                    workers.send_to("vision", "vision.config.update", {
                        _vision_param_to_key(name): value,
                    })
                )

        registry.on_change(_on_param_change)

        log.info("supervisor v2 running (mock=%s, vision=%s, planner=%s, http=%s:%d)",
                 cfg.mock, not args.no_vision, planner_enabled,
                 cfg.network.host, cfg.network.http_port)

        # Run tick loop and HTTP server concurrently
        await asyncio.gather(
            tick.run(),
            http_server.serve(),
        )

    finally:
        log.info("shutting down...")
        if http_server:
            http_server.should_exit = True
        if 'workers' in dir():
            await workers.stop()
        if reflex and hasattr(reflex, '_transport'):
            await reflex._transport.stop()
        if face and hasattr(face, '_transport'):
            await face._transport.stop()
        if mock_reflex:
            mock_reflex.stop()


def _vision_param_to_key(name: str) -> str:
    """Map registry param name → vision worker config key."""
    mapping = {
        "vision.floor_hsv_h_low": "floor_hsv_low",
        "vision.floor_hsv_h_high": "floor_hsv_high",
        "vision.floor_hsv_s_low": "floor_hsv_low",
        "vision.floor_hsv_s_high": "floor_hsv_high",
        "vision.floor_hsv_v_low": "floor_hsv_low",
        "vision.floor_hsv_v_high": "floor_hsv_high",
        "vision.ball_hsv_h_low": "ball_hsv_low",
        "vision.ball_hsv_h_high": "ball_hsv_high",
        "vision.ball_hsv_s_low": "ball_hsv_low",
        "vision.ball_hsv_s_high": "ball_hsv_high",
        "vision.ball_hsv_v_low": "ball_hsv_low",
        "vision.ball_hsv_v_high": "ball_hsv_high",
        "vision.min_ball_radius_px": "min_ball_radius",
    }
    return mapping.get(name, name.replace("vision.", ""))


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass
