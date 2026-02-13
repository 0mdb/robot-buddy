"""Supervisor configuration with defaults, loadable from YAML."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class SerialConfig:
    reflex_port: str = "/dev/robot_reflex"
    face_port: str = "/dev/robot_face"
    baudrate: int = 115200


@dataclass
class ControlConfig:
    tick_hz: int = 50
    telemetry_hz: int = 20


@dataclass
class SafetyConfig:
    speed_cap_close_mm: int = 300
    speed_cap_close_scale: float = 0.25
    speed_cap_medium_mm: int = 500
    speed_cap_medium_scale: float = 0.50
    speed_cap_stale_scale: float = 0.50


@dataclass
class NetworkConfig:
    http_port: int = 8080
    host: str = "0.0.0.0"


@dataclass
class LoggingConfig:
    record_jsonl: bool = True
    record_rate_hz: int = 10
    record_max_mb: int = 50
    record_roll_count: int = 3
    record_dir: str = "/tmp/robot-buddy-logs"


@dataclass
class VisionConfig:
    enabled: bool = True
    camera_id: int = 0
    capture_width: int = 640
    capture_height: int = 480
    process_width: int = 320
    process_height: int = 240


@dataclass
class SupervisorConfig:
    serial: SerialConfig = field(default_factory=SerialConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    mock: bool = False


def load_config(path: str | Path | None = None) -> SupervisorConfig:
    """Load config from YAML file, falling back to defaults."""
    if path is None:
        return SupervisorConfig()

    path = Path(path)
    if not path.exists():
        log.warning("config file not found: %s, using defaults", path)
        return SupervisorConfig()

    try:
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        cfg = SupervisorConfig()
        if "serial" in raw:
            for k, v in raw["serial"].items():
                setattr(cfg.serial, k, v)
        if "control" in raw:
            for k, v in raw["control"].items():
                setattr(cfg.control, k, v)
        if "safety" in raw:
            for k, v in raw["safety"].items():
                setattr(cfg.safety, k, v)
        if "network" in raw:
            for k, v in raw["network"].items():
                setattr(cfg.network, k, v)
        if "logging" in raw:
            for k, v in raw["logging"].items():
                setattr(cfg.logging, k, v)
        if "vision" in raw:
            for k, v in raw["vision"].items():
                setattr(cfg.vision, k, v)
        cfg.mock = raw.get("mock", False)

        log.info("config loaded from %s", path)
        return cfg
    except Exception as e:
        log.warning("config load error: %s, using defaults", e)
        return SupervisorConfig()
