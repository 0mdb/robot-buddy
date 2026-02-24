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
    low_battery_mv: int = 6400  # 2S LiPo ~3.2 V/cell; override via config YAML


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
class WorkerConfig:
    """Worker process configuration (new in v2)."""

    audio_mode: str = "direct"  # "direct" | "relay"
    server_base_url: str = ""
    tts_endpoint: str = ""
    speaker_device: str = "default"
    mic_device: str = "default"
    robot_id: str = ""
    heartbeat_timeout_s: float = 5.0
    max_restarts: int = 5
    restart_backoff_min_s: float = 1.0
    restart_backoff_max_s: float = 5.0


@dataclass
class GuardrailConfig:
    """Toggleable guardrails (PE spec S2 §9.5).

    All on by default.  HC-1 through HC-10 are NOT toggleable and are
    always enforced regardless of these settings.
    """

    negative_duration_caps: bool = True
    negative_intensity_caps: bool = True
    context_gate: bool = True
    session_time_limit_s: float = 900.0  # RS-1: 15 min
    daily_time_limit_s: float = 2700.0  # RS-2: 45 min


@dataclass
class PersonalityConfig:
    """Personality engine configuration (PE spec S2 §14.3)."""

    # Axis positions (spec §1.1)
    energy: float = 0.40
    reactivity: float = 0.50
    initiative: float = 0.30
    vulnerability: float = 0.35
    predictability: float = 0.75

    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)

    memory_path: str = "./data/personality_memory.json"
    memory_consent: bool = False  # COPPA default: opt-out


@dataclass
class SupervisorConfig:
    serial: SerialConfig = field(default_factory=SerialConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
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
        import yaml  # type: ignore[import-untyped]

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        cfg = SupervisorConfig()
        for section_name in (
            "serial",
            "control",
            "safety",
            "network",
            "logging",
            "vision",
            "workers",
            "personality",
        ):
            if section_name in raw:
                section = getattr(cfg, section_name)
                for k, v in raw[section_name].items():
                    setattr(section, k, v)
        cfg.mock = raw.get("mock", False)

        log.info("config loaded from %s", path)
        return cfg
    except Exception as e:
        log.warning("config load error: %s, using defaults", e)
        return SupervisorConfig()
