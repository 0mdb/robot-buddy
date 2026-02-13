"""Supervisor entry point.

Usage:
    python -m supervisor                    # default (expects real hardware)
    python -m supervisor --mock             # use mock reflex MCU
    python -m supervisor --port /dev/...    # specify serial port
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
from supervisor.devices.reflex_client import REFLEX_PARAM_IDS, ReflexClient
from supervisor.inputs.camera_vision import VisionProcess
from supervisor.io.serial_transport import SerialTransport
from supervisor.mock.mock_reflex import MockReflex
from supervisor.runtime import Runtime

log = logging.getLogger("supervisor")

DEFAULT_PORT = "/dev/robot_reflex"
HTTP_PORT = 8080


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Robot Buddy Supervisor")
    p.add_argument("--mock", action="store_true", help="Use mock reflex MCU (PTY)")
    p.add_argument("--port", default=DEFAULT_PORT, help="Reflex serial port")
    p.add_argument("--http-port", type=int, default=HTTP_PORT, help="HTTP/WS port")
    p.add_argument("--no-vision", action="store_true", help="Disable vision process")
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
    runtime = Runtime(reflex, on_telemetry=ws_hub.broadcast_telemetry, vision=vision)

    # FastAPI app
    app = create_app(runtime, registry, ws_hub, vision=vision)

    # Start serial transport
    await transport.start()

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
        await transport.stop()
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
