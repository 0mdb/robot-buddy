"""Supervisor entry point.

Usage:
    python -m supervisor                    # default (expects real hardware)
    python -m supervisor --mock             # use mock reflex MCU
    python -m supervisor --port /dev/...    # specify serial port
    python -m supervisor --server-api http://10.0.0.20:8100
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
from supervisor.devices.conversation_manager import ConversationManager
from supervisor.devices.face_client import FaceClient
from supervisor.devices.personality_client import PersonalityClient
from supervisor.devices.protocol import FaceButtonEventType, FaceButtonId
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
        "--server-api",
        default="",
        help="Personality server base URL (e.g. http://10.0.0.20:8100)",
    )
    p.add_argument(
        "--server-timeout",
        type=float,
        default=6.0,
        help="Personality server HTTP timeout in seconds",
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
    conversation: ConversationManager | None = None
    if not args.no_face:
        face_transport = SerialTransport(args.face_port, label="face")
        face = FaceClient(face_transport)

    # Personality server client (optional)
    personality: PersonalityClient | None = None
    if args.server_api:
        personality = PersonalityClient(args.server_api, timeout_s=args.server_timeout)
        await personality.start()
        healthy = await personality.health_check()
        if healthy:
            log.info("personality server reachable at %s", args.server_api)
        else:
            log.warning("personality server not reachable at startup: %s", args.server_api)

    if args.server_api and face is not None:
        conversation = ConversationManager(
            args.server_api,
            face=face,
            speaker_device=args.usb_speaker_device,
            mic_device=args.usb_mic_device,
        )

        def _on_face_button(evt) -> None:
            if evt.button_id == int(FaceButtonId.ACTION) and evt.event_type == int(
                FaceButtonEventType.CLICK
            ):
                asyncio.create_task(conversation.cancel())
            elif evt.button_id == int(FaceButtonId.PTT) and evt.event_type == int(
                FaceButtonEventType.TOGGLE
            ):
                asyncio.create_task(conversation.set_ptt_enabled(bool(evt.state)))

        face.on_button(_on_face_button)

    # Vision process
    vision: VisionProcess | None = None
    if not args.no_vision:
        vision = VisionProcess()
        vision.start()

    # Parameter registry + wire reflex param changes to SET_CONFIG
    registry = create_default_registry()

    def _on_param_change(name: str, value: object) -> None:
        if name in REFLEX_PARAM_IDS:
            reflex.send_set_config(name, value)  # type: ignore[arg-type]

    registry.on_change(_on_param_change)

    # WebSocket hub
    ws_hub = WsHub()

    # Runtime with telemetry wired to WS broadcast
    runtime = Runtime(
        reflex,
        on_telemetry=ws_hub.broadcast_telemetry,
        vision=vision,
        face=face,
        personality=personality,
    )

    # FastAPI app
    app = create_app(runtime, registry, ws_hub, vision=vision)

    # Start serial transports
    await transport.start()
    if face_transport:
        await face_transport.start()
        if conversation is not None:
            await conversation.start()

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
            if conversation:
                await conversation.stop()
            await face_transport.stop()
        await transport.stop()
        if personality:
            await personality.stop()
        if mock:
            mock.stop()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

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
