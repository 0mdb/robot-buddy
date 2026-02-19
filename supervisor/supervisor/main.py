"""Supervisor entry point.

Usage:
    python -m supervisor                    # default (expects real hardware)
    python -m supervisor --mock             # use mock reflex MCU
    python -m supervisor --port /dev/...    # specify serial port
    python -m supervisor --planner-api http://10.0.0.20:8100
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

import uvicorn

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.devices.audio_orchestrator import AudioOrchestrator
from supervisor.devices.face_client import FaceClient
from supervisor.devices.planner_client import PlannerClient
from supervisor.devices.reflex_client import REFLEX_PARAM_IDS, ReflexClient
from supervisor.inputs.camera_vision import VisionProcess
from supervisor.io.serial_transport import SerialTransport
from supervisor.mock.mock_reflex import MockReflex
from supervisor.runtime import Runtime

log = logging.getLogger("supervisor")

DEFAULT_PORT = "/dev/robot_reflex"
DEFAULT_FACE_PORT = "/dev/robot_face"
HTTP_PORT = 8080


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Robot Buddy Supervisor")
    p.add_argument("--mock", action="store_true", help="Use mock reflex MCU (PTY)")
    p.add_argument("--port", default=DEFAULT_PORT, help="Reflex serial port")
    p.add_argument("--http-port", type=int, default=HTTP_PORT, help="HTTP/WS port")
    p.add_argument("--no-vision", action="store_true", help="Disable vision process")
    p.add_argument("--face-port", default=DEFAULT_FACE_PORT, help="Face serial port")
    p.add_argument("--no-face", action="store_true", help="Disable face MCU")
    p.add_argument(
        "--planner-api",
        default="",
        help="Planner server base URL (e.g. http://10.0.0.20:8100)",
    )
    p.add_argument(
        "--planner-timeout",
        type=float,
        default=6.0,
        help="Planner server HTTP timeout in seconds",
    )
    p.add_argument(
        "--usb-speaker-device",
        default="default",
        help="ALSA playback device passed to aplay -D",
    )
    p.add_argument(
        "--usb-mic-device",
        default="default",
        help="ALSA capture device passed to arecord -D",
    )
    p.add_argument("--log-level", default="INFO", help="Log level")
    return p.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    mock: MockReflex | None = None
    port = args.port

    # Start mock if requested
    if args.mock:
        mock = MockReflex()
        mock.start()
        port = mock.device_path
        log.info("using mock reflex at %s", port)

    # Serial transport + reflex client
    transport = SerialTransport(port, label="reflex")
    reflex = ReflexClient(transport)

    # Face transport + client
    face_transport: SerialTransport | None = None
    face: FaceClient | None = None
    audio: AudioOrchestrator | None = None
    if not args.no_face:
        face_transport = SerialTransport(args.face_port, label="face")
        face = FaceClient(face_transport)

    # Planner server client (optional)
    planner: PlannerClient | None = None
    if args.planner_api:
        planner = PlannerClient(args.planner_api, timeout_s=args.planner_timeout)
        await planner.start()
        healthy = await planner.health_check()
        if healthy:
            log.info("planner server reachable at %s", args.planner_api)
        else:
            log.warning("planner server not reachable at startup: %s", args.planner_api)

    if args.planner_api and face is not None:
        audio = AudioOrchestrator(
            args.planner_api,
            face=face,
            speaker_device=args.usb_speaker_device,
            mic_device=args.usb_mic_device,
        )
        face.subscribe_button(audio.on_face_button)

    # Vision process
    vision: VisionProcess | None = None
    if not args.no_vision:
        vision = VisionProcess()
        vision.start()

    # Parameter registry + wire param changes to hardware / vision / policies
    registry = create_default_registry()

    _VISION_HSV_PARAMS = {
        "vision.floor_hsv_h_low", "vision.floor_hsv_h_high",
        "vision.floor_hsv_s_low", "vision.floor_hsv_s_high",
        "vision.floor_hsv_v_low", "vision.floor_hsv_v_high",
        "vision.ball_hsv_h_low",  "vision.ball_hsv_h_high",
        "vision.ball_hsv_s_low",  "vision.ball_hsv_s_high",
        "vision.ball_hsv_v_low",  "vision.ball_hsv_v_high",
        "vision.min_ball_radius_px",
    }
    _VISION_POLICY_PARAMS = {"vision.stale_ms", "vision.clear_low", "vision.clear_high"}

    def _on_param_change(name: str, value: object) -> None:
        if name in REFLEX_PARAM_IDS:
            reflex.send_set_config(name, value)  # type: ignore[arg-type]

        if name in _VISION_HSV_PARAMS and vision:
            r = registry.get_value
            vision.update_config({
                "floor_hsv_low":  (r("vision.floor_hsv_h_low"), r("vision.floor_hsv_s_low"),  r("vision.floor_hsv_v_low")),
                "floor_hsv_high": (r("vision.floor_hsv_h_high"), r("vision.floor_hsv_s_high"), r("vision.floor_hsv_v_high")),
                "ball_hsv_low":   (r("vision.ball_hsv_h_low"), r("vision.ball_hsv_s_low"),  r("vision.ball_hsv_v_low")),
                "ball_hsv_high":  (r("vision.ball_hsv_h_high"), r("vision.ball_hsv_s_high"), r("vision.ball_hsv_v_high")),
                "min_ball_radius": r("vision.min_ball_radius_px"),
            })

        if name in _VISION_POLICY_PARAMS:
            from supervisor.state.policies import configure_vision_policy
            configure_vision_policy(
                stale_ms=registry.get_value("vision.stale_ms", 500.0),
                clear_low=registry.get_value("vision.clear_low", 0.3),
                clear_high=registry.get_value("vision.clear_high", 0.6),
            )

    registry.on_change(_on_param_change)

    # WebSocket hub
    ws_hub = WsHub()

    # Runtime with telemetry wired to WS broadcast
    runtime = Runtime(
        reflex,
        on_telemetry=ws_hub.broadcast_telemetry,
        vision=vision,
        face=face,
        planner=planner,
        audio=audio,
    )

    # FastAPI app
    app = create_app(runtime, registry, ws_hub, vision=vision)

    # Start serial transports
    await transport.start()
    if face_transport:
        await face_transport.start()
        if audio is not None:
            await audio.start()

    # Start uvicorn + tick loop concurrently
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=args.http_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(
            runtime.run(),
            server.serve(),
        )
    finally:
        runtime.stop()
        if vision:
            vision.stop()
        if face_transport:
            if audio:
                await audio.stop()
            await face_transport.stop()
        await transport.stop()
        if planner:
            await planner.stop()
        if mock:
            mock.stop()


from supervisor.logging.handler import WebSocketLogHandler


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(WebSocketLogHandler())

    loop = asyncio.new_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: loop.stop())

    try:
        loop.run_until_complete(async_main(args))
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
    log.info("supervisor shut down")


if __name__ == "__main__":
    main()
