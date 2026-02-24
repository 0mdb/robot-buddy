"""Supervisor entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def _get_int(registry: object, name: str, default: int) -> int:
    """Best-effort int read from ParamRegistry-like object."""
    try:
        value = registry.get_value(name, default)  # type: ignore[attr-defined]
        return int(value)
    except Exception:
        return int(default)


def _get_float(registry: object, name: str, default: float) -> float:
    """Best-effort float read from ParamRegistry-like object."""
    try:
        value = registry.get_value(name, default)  # type: ignore[attr-defined]
        return float(value)
    except Exception:
        return float(default)


def _build_vision_worker_config(registry: object) -> dict[str, object]:
    """Build a complete vision.config.update payload from registry values.

    Does not include mjpeg_enabled (owned by /video client presence).
    """
    floor_hsv_low = [
        _get_int(registry, "vision.floor_hsv_h_low", 0),
        _get_int(registry, "vision.floor_hsv_s_low", 0),
        _get_int(registry, "vision.floor_hsv_v_low", 50),
    ]
    floor_hsv_high = [
        _get_int(registry, "vision.floor_hsv_h_high", 180),
        _get_int(registry, "vision.floor_hsv_s_high", 80),
        _get_int(registry, "vision.floor_hsv_v_high", 220),
    ]
    ball_hsv_low = [
        _get_int(registry, "vision.ball_hsv_h_low", 170),
        _get_int(registry, "vision.ball_hsv_s_low", 80),
        _get_int(registry, "vision.ball_hsv_v_low", 40),
    ]
    ball_hsv_high = [
        _get_int(registry, "vision.ball_hsv_h_high", 15),
        _get_int(registry, "vision.ball_hsv_s_high", 255),
        _get_int(registry, "vision.ball_hsv_v_high", 255),
    ]
    min_ball_radius = _get_int(registry, "vision.min_ball_radius_px", 8)

    return {
        "floor_hsv_low": floor_hsv_low,
        "floor_hsv_high": floor_hsv_high,
        "ball_hsv_low": ball_hsv_low,
        "ball_hsv_high": ball_hsv_high,
        "min_ball_radius": min_ball_radius,
    }


def _configure_vision_policy_from_registry(registry: object) -> None:
    from supervisor.core.safety import configure_vision_policy

    stale_ms = _get_float(registry, "vision.stale_ms", 500.0)
    clear_low = _get_float(registry, "vision.clear_low", 0.3)
    clear_high = _get_float(registry, "vision.clear_high", 0.6)
    configure_vision_policy(
        stale_ms=stale_ms,
        clear_low=clear_low,
        clear_high=clear_high,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Robot Buddy Supervisor")
    p.add_argument(
        "--mock", action="store_true", help="Use mock Reflex MCU (no hardware)"
    )
    p.add_argument(
        "--port", default=None, help="Reflex serial port (default: /dev/robot_reflex)"
    )
    p.add_argument(
        "--face-port", default=None, help="Face serial port (default: /dev/robot_face)"
    )
    p.add_argument("--no-face", action="store_true", help="Disable Face MCU")
    p.add_argument("--no-vision", action="store_true", help="Disable vision worker")
    p.add_argument(
        "--no-planner", action="store_true", help="Disable AI/planner worker"
    )
    p.add_argument("--http-port", type=int, default=8080, help="HTTP server port")
    p.add_argument("--planner-api", default=None, help="Planner server base URL")
    p.add_argument(
        "--robot-id", default=os.environ.get("ROBOT_ID", ""), help="Robot ID"
    )
    p.add_argument("--config", default=None, help="YAML config file path")
    p.add_argument("--log-level", default="INFO", help="Log level")
    p.add_argument(
        "--usb-speaker-device", default="default", help="ALSA speaker device"
    )
    p.add_argument("--usb-mic-device", default="default", help="ALSA mic device")
    return p.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    import uvicorn

    from supervisor.api.http_server import create_app
    from supervisor.api.param_registry import create_default_registry
    from supervisor.api.ws_hub import WsHub
    from supervisor.config import load_config
    from supervisor.core.tick_loop import TickLoop
    from supervisor.core.worker_manager import WorkerManager
    from supervisor.devices.clock_sync import (
        ClockSyncEngine,
    )
    from supervisor.devices.face_client import FaceClient
    from supervisor.devices.reflex_client import ReflexClient
    from supervisor.io.serial_transport import SerialTransport

    cfg = load_config(args.config)

    # Apply CLI overrides
    if args.port:
        cfg.serial.reflex_port = args.port
    if args.face_port:
        cfg.serial.face_port = args.face_port
    if args.mock:
        cfg.mock = True
    cfg.network.http_port = args.http_port

    from supervisor.api.protocol_capture import ProtocolCapture

    capture = ProtocolCapture()
    mock_reflex = None
    reflex = None
    face = None
    http_server = None

    try:
        # ── Reflex MCU ───────────────────────────────────────────
        if cfg.mock:
            from supervisor.mock.mock_reflex import MockReflex

            mock_reflex = MockReflex()
            mock_reflex.start()
            reflex_port = mock_reflex.device_path
            log.info("mock reflex on %s", reflex_port)
        else:
            reflex_port = cfg.serial.reflex_port

        reflex_transport = SerialTransport(
            port=reflex_port, baudrate=cfg.serial.baudrate, label="reflex"
        )
        reflex = ReflexClient(reflex_transport, capture=capture)
        await reflex_transport.start()
        await reflex_transport.negotiate_v2()

        # ── Face MCU ─────────────────────────────────────────────
        if not args.no_face:
            face_transport = SerialTransport(
                port=cfg.serial.face_port, baudrate=cfg.serial.baudrate, label="face"
            )
            face = FaceClient(face_transport, capture=capture)
            await face_transport.start()
            await face_transport.negotiate_v2()

        # ── API components ─────────────────────────────────────
        registry = create_default_registry()
        ws_hub = WsHub()

        # ── Worker Manager ───────────────────────────────────────
        planner_enabled = bool(
            args.robot_id and args.planner_api and not args.no_planner
        )

        # We create the tick loop first so we can use its on_worker_event as callback
        workers = WorkerManager(
            on_event=lambda name, env: tick.on_worker_event(name, env),
            heartbeat_timeout_s=cfg.workers.heartbeat_timeout_s,
            max_restarts=cfg.workers.max_restarts,
        )

        # Register workers
        if not args.no_vision:
            workers.register("vision", "supervisor.workers.vision_worker")

        if planner_enabled:
            workers.register("ear", "supervisor.workers.ear_worker")
            workers.register("tts", "supervisor.workers.tts_worker")
            workers.register("ai", "supervisor.workers.ai_worker")

        # Personality worker (Layer 0 is fully deterministic, no server needed)
        workers.register("personality", "supervisor.workers.personality_worker")

        # ── Tick Loop ────────────────────────────────────────────
        tick = TickLoop(
            reflex=reflex,
            face=face,
            workers=workers,
            on_telemetry=ws_hub.broadcast_telemetry,
            planner_enabled=planner_enabled,
            robot_id=args.robot_id,
            low_battery_mv=cfg.safety.low_battery_mv,
        )

        # ── HTTP server ──────────────────────────────────────────
        app = create_app(tick, registry, ws_hub, workers, capture=capture)
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
            # Apply initial safety policy thresholds (vision.* params)
            _configure_vision_policy_from_registry(registry)

            await workers.send_to(
                "vision",
                "vision.config.update",
                {
                    "mjpeg_enabled": False,
                    **_build_vision_worker_config(registry),
                },
            )

        if planner_enabled:
            ear_init = {
                "mic_device": args.usb_mic_device,
                "mic_socket_path": workers.mic_socket_path,
                "wakeword_model_path": str(
                    Path(__file__).parent / "models" / "hey_buddy.onnx"
                ),
                "wakeword_threshold": 0.5,
                "vad_silence_ms": 1200,
                "vad_min_speech_ms": 300,
            }
            await workers.send_to("ear", "ear.config.init", ear_init)

            tts_init = {
                "audio_mode": cfg.workers.audio_mode,
                "spk_socket_path": workers.spk_socket_path,
                "speaker_device": args.usb_speaker_device,
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

        # Personality worker config (PE spec S2 §14.3)
        pe = cfg.personality
        await workers.send_to(
            "personality",
            "personality.config.init",
            {
                "axes": {
                    "energy": pe.energy,
                    "reactivity": pe.reactivity,
                    "initiative": pe.initiative,
                    "vulnerability": pe.vulnerability,
                    "predictability": pe.predictability,
                },
                "guardrails": {
                    "negative_duration_caps": pe.guardrails.negative_duration_caps,
                    "negative_intensity_caps": pe.guardrails.negative_intensity_caps,
                    "context_gate": pe.guardrails.context_gate,
                    "session_time_limit_s": pe.guardrails.session_time_limit_s,
                    "daily_time_limit_s": pe.guardrails.daily_time_limit_s,
                },
                "memory_path": pe.memory_path,
                "memory_consent": pe.memory_consent,
            },
        )

        # Wire param changes to vision worker + safety policy
        _VISION_WORKER_PARAMS = {
            "vision.floor_hsv_h_low",
            "vision.floor_hsv_h_high",
            "vision.floor_hsv_s_low",
            "vision.floor_hsv_s_high",
            "vision.floor_hsv_v_low",
            "vision.floor_hsv_v_high",
            "vision.ball_hsv_h_low",
            "vision.ball_hsv_h_high",
            "vision.ball_hsv_s_low",
            "vision.ball_hsv_s_high",
            "vision.ball_hsv_v_low",
            "vision.ball_hsv_v_high",
            "vision.min_ball_radius_px",
        }
        _VISION_POLICY_PARAMS = {
            "vision.stale_ms",
            "vision.clear_low",
            "vision.clear_high",
        }

        vision_cfg_scheduled = False
        vision_policy_scheduled = False

        async def _flush_vision_worker_config() -> None:
            nonlocal vision_cfg_scheduled
            await asyncio.sleep(0)  # coalesce multiple updates in one event loop tick
            vision_cfg_scheduled = False
            if not workers.worker_alive("vision"):
                return
            await workers.send_to(
                "vision",
                "vision.config.update",
                _build_vision_worker_config(registry),
            )

        async def _flush_vision_policy() -> None:
            nonlocal vision_policy_scheduled
            await asyncio.sleep(0)  # coalesce multiple updates in one event loop tick
            vision_policy_scheduled = False
            _configure_vision_policy_from_registry(registry)

        def _on_param_change(name: str, _value: object) -> None:
            nonlocal vision_cfg_scheduled, vision_policy_scheduled
            if name in _VISION_WORKER_PARAMS and not vision_cfg_scheduled:
                vision_cfg_scheduled = True
                asyncio.create_task(_flush_vision_worker_config())
            if name in _VISION_POLICY_PARAMS and not vision_policy_scheduled:
                vision_policy_scheduled = True
                asyncio.create_task(_flush_vision_policy())

        registry.on_change(_on_param_change)

        # ── Clock Sync ────────────────────────────────────────────
        reflex_sync = ClockSyncEngine(
            transport=reflex_transport,
            clock_state=tick.robot.reflex_clock,
            label="reflex",
        )

        face_sync: ClockSyncEngine | None = None
        if face:
            from supervisor.devices.clock_sync import _RTT_THRESHOLD_FACE_NS

            face_sync = ClockSyncEngine(
                transport=face_transport,
                clock_state=tick.robot.face_clock,
                label="face",
                rtt_threshold_ns=_RTT_THRESHOLD_FACE_NS,
            )

        # ── Raw Packet Logger ─────────────────────────────────────
        from supervisor.io.raw_logger import RawPacketLogger

        raw_log_dir = Path(cfg.logging.record_dir) / "raw"
        raw_logger = RawPacketLogger(raw_log_dir)
        raw_logger.start()
        reflex_transport.on_raw_frame(raw_logger.log_frame)
        if face:
            face_transport.on_raw_frame(raw_logger.log_frame)

        log.info(
            "supervisor running (mock=%s, vision=%s, planner=%s, http=%s:%d)",
            cfg.mock,
            not args.no_vision,
            planner_enabled,
            cfg.network.host,
            cfg.network.http_port,
        )

        # Run tick loop, HTTP server, and clock sync concurrently
        tasks = [tick.run(), http_server.serve(), reflex_sync.run()]
        if face_sync:
            tasks.append(face_sync.run())
        await asyncio.gather(*tasks)

    finally:
        log.info("shutting down...")
        if http_server:
            http_server.should_exit = True
        if "workers" in dir():
            await workers.stop()
        if reflex and hasattr(reflex, "_transport"):
            await reflex._transport.stop()
        if face and hasattr(face, "_transport"):
            await face._transport.stop()
        if mock_reflex:
            mock_reflex.stop()


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
