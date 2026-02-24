"""Split state types for the supervisor (MIGRATION.md § State Split).

RobotState — MCU hardware, updated synchronously each tick.
WorldState — perception from workers, updated asynchronously from events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from supervisor.devices.expressions import FACE_MOOD_TO_EMOTION
from supervisor.devices.protocol import Fault, RangeStatus


# ── Enums ────────────────────────────────────────────────────────


class Mode(str, Enum):
    BOOT = "BOOT"
    IDLE = "IDLE"
    TELEOP = "TELEOP"
    WANDER = "WANDER"
    ERROR = "ERROR"


MOTION_MODES = frozenset({Mode.TELEOP, Mode.WANDER})


# ── Value types ──────────────────────────────────────────────────


@dataclass(slots=True)
class DesiredTwist:
    v_mm_s: int = 0
    w_mrad_s: int = 0


@dataclass(slots=True)
class SpeedCap:
    """Describes a speed limitation and why it was applied."""

    scale: float = 1.0
    reason: str = ""


@dataclass(slots=True)
class ClockSync:
    """Per-device clock sync state (PROTOCOL.md §2.2)."""

    state: str = "unsynced"  # "unsynced" | "synced" | "degraded"
    offset_ns: int = 0
    rtt_min_us: int = 0
    drift_us_per_s: float = 0.0
    samples: int = 0
    t_last_sync_ns: int = 0


# ── RobotState (MCU hardware — updated synchronously each tick) ──


@dataclass(slots=True)
class RobotState:
    """MCU hardware snapshot, rebuilt each tick."""

    mode: Mode = Mode.BOOT

    # Motion
    twist_cmd: DesiredTwist = field(default_factory=DesiredTwist)
    twist_capped: DesiredTwist = field(default_factory=DesiredTwist)

    # Reflex telemetry
    speed_l_mm_s: int = 0
    speed_r_mm_s: int = 0
    gyro_z_mrad_s: int = 0
    accel_x_mg: int = 0
    accel_y_mg: int = 0
    accel_z_mg: int = 0
    battery_mv: int = 0
    fault_flags: int = 0
    range_mm: int = 0
    range_status: int = RangeStatus.NOT_READY
    reflex_seq: int = 0
    reflex_rx_mono_ms: float = 0.0

    # Derived from IMU (computed each telemetry callback)
    tilt_angle_deg: float = 0.0  # atan2(accel_x_mg, accel_z_mg) — forward tilt
    accel_magnitude_mg: float = 0.0  # sqrt(x²+y²+z²) — should ≈ 1000 mg at rest

    # Computed from wheel speeds
    v_meas_mm_s: float = 0.0
    w_meas_mrad_s: float = 0.0

    # Connection state
    reflex_connected: bool = False
    face_connected: bool = False

    # Face telemetry
    face_mood: int = 0
    face_gesture: int = 0xFF
    face_system_mode: int = 0
    face_touch_active: bool = False
    face_listening: bool = False
    face_talking: bool = False
    face_talking_energy: int = 0
    face_manual_lock: bool = False
    face_manual_flags: int = 0
    face_last_button_id: int = -1
    face_last_button_event: int = -1
    face_last_button_state: int = 0
    face_conv_state: int = 0  # FaceConvState.IDLE
    face_conv_timer_ms: float = 0.0
    face_seq_phase: int = 0  # SeqPhase (mood transition sequencer)
    face_seq_mood_id: int = 0  # Current sequencer mood
    face_seq_intensity: float = 0.0  # Current sequencer intensity
    face_choreo_active: bool = False  # Transition choreographer running
    face_seq: int = 0
    face_rx_mono_ms: float = 0.0

    # Clock sync
    reflex_clock: ClockSync = field(default_factory=ClockSync)
    face_clock: ClockSync = field(default_factory=ClockSync)

    # Safety
    speed_caps: list[SpeedCap] = field(default_factory=list)

    # Timing
    tick_mono_ms: float = 0.0
    tick_dt_ms: float = 0.0

    def has_fault(self, f: Fault) -> bool:
        return bool(self.fault_flags & f)

    @property
    def any_fault(self) -> bool:
        return self.fault_flags != 0

    def to_dict(self) -> dict:
        """Serialize for JSON telemetry."""
        return {
            "mode": self.mode.value,
            "v_cmd": self.twist_cmd.v_mm_s,
            "w_cmd": self.twist_cmd.w_mrad_s,
            "v_capped": self.twist_capped.v_mm_s,
            "w_capped": self.twist_capped.w_mrad_s,
            "v_meas": round(self.v_meas_mm_s, 1),
            "w_meas": round(self.w_meas_mrad_s, 1),
            "speed_l": self.speed_l_mm_s,
            "speed_r": self.speed_r_mm_s,
            "gyro_z": self.gyro_z_mrad_s,
            "accel_x": self.accel_x_mg,
            "accel_y": self.accel_y_mg,
            "accel_z": self.accel_z_mg,
            "tilt_angle_deg": round(self.tilt_angle_deg, 1),
            "accel_magnitude_mg": round(self.accel_magnitude_mg, 1),
            "battery_mv": self.battery_mv,
            "fault_flags": self.fault_flags,
            "range_mm": self.range_mm,
            "range_status": self.range_status,
            "reflex_connected": self.reflex_connected,
            "face_connected": self.face_connected,
            "face_mood": FACE_MOOD_TO_EMOTION.get(self.face_mood, "unknown"),
            "face_gesture": self.face_gesture,
            "face_system_mode": self.face_system_mode,
            "face_touch_active": self.face_touch_active,
            "face_listening": self.face_listening,
            "face_talking": self.face_talking,
            "face_talking_energy": self.face_talking_energy,
            "face_manual_lock": self.face_manual_lock,
            "face_manual_flags": self.face_manual_flags,
            "face_last_button_id": self.face_last_button_id,
            "face_last_button_event": self.face_last_button_event,
            "face_last_button_state": self.face_last_button_state,
            "face_conv_state": self.face_conv_state,
            "face_conv_timer_ms": round(self.face_conv_timer_ms, 1),
            "face_seq_phase": self.face_seq_phase,
            "face_seq_mood_id": self.face_seq_mood_id,
            "face_seq_intensity": round(self.face_seq_intensity, 3),
            "face_choreo_active": self.face_choreo_active,
            "face_seq": self.face_seq,
            "face_rx_mono_ms": round(self.face_rx_mono_ms, 1),
            "speed_caps": [
                {"scale": c.scale, "reason": c.reason} for c in self.speed_caps
            ],
            "tick_dt_ms": round(self.tick_dt_ms, 2),
            "clock_sync": {
                "reflex": {
                    "state": self.reflex_clock.state,
                    "offset_ns": self.reflex_clock.offset_ns,
                    "rtt_min_us": self.reflex_clock.rtt_min_us,
                    "drift_us_per_s": self.reflex_clock.drift_us_per_s,
                    "samples": self.reflex_clock.samples,
                },
                "face": {
                    "state": self.face_clock.state,
                    "offset_ns": self.face_clock.offset_ns,
                    "rtt_min_us": self.face_clock.rtt_min_us,
                    "drift_us_per_s": self.face_clock.drift_us_per_s,
                    "samples": self.face_clock.samples,
                },
            },
        }


# ── WorldState (perception from workers — updated asynchronously) ──


@dataclass(slots=True)
class WorldState:
    """Perception state from workers, updated asynchronously."""

    # Vision
    clear_confidence: float = -1.0  # -1 = no data
    ball_confidence: float = 0.0
    ball_bearing_deg: float = 0.0
    vision_fps: float = 0.0
    vision_rx_mono_ms: float = 0.0
    vision_frame_seq: int = 0

    # Audio / speech
    speaking: bool = False
    current_energy: int = 0
    ptt_active: bool = False
    speech_source: str = ""
    speech_priority: int = 3  # idle

    # Planner
    planner_connected: bool = False
    planner_enabled: bool = False
    active_skill: str = "patrol_drift"
    last_plan_mono_ms: float = 0.0
    last_plan_actions: int = 0
    last_plan_id: str = ""
    last_plan: list[dict] | None = None
    last_plan_error: str = ""
    plan_seq_last_accepted: int = -1
    plan_dropped_stale: int = 0
    plan_dropped_cooldown: int = 0
    plan_dropped_out_of_order: int = 0
    plan_dropped_duplicate: int = 0
    say_requested: int = 0
    say_enqueued: int = 0
    say_dropped_reason: dict[str, int] = field(default_factory=dict)
    event_count: int = 0

    # Worker health
    worker_last_heartbeat_ms: dict[str, float] = field(default_factory=dict)
    worker_alive: dict[str, bool] = field(default_factory=dict)

    # Audio link state
    mic_link_up: bool = False
    spk_link_up: bool = False

    # Conversation
    session_id: str = ""
    turn_id: int = 0
    ai_state: str = "idle"
    conversation_trigger: str = ""  # "ptt" | "wake_word" | ""

    # MJPEG frame buffer (latest base64-encoded JPEG from vision worker)
    latest_jpeg_b64: str = ""

    # Personality engine (PE spec S2 §11.2)
    personality_mood: str = "neutral"
    personality_intensity: float = 0.0
    personality_valence: float = 0.0
    personality_arousal: float = 0.0
    personality_layer: int = 0
    personality_idle_state: str = "awake"
    personality_snapshot_ts_ms: float = 0.0
    personality_conversation_active: bool = False

    # Session/daily time limits (PE spec S2 §9.3 RS-1/RS-2)
    personality_session_time_s: float = 0.0
    personality_daily_time_s: float = 0.0
    personality_session_limit_reached: bool = False
    personality_daily_limit_reached: bool = False

    @property
    def vision_age_ms(self) -> float:
        """Milliseconds since last vision snapshot, or -1 if no data."""
        if self.vision_rx_mono_ms <= 0:
            return -1.0
        import time

        return time.monotonic() * 1000.0 - self.vision_rx_mono_ms

    @property
    def both_audio_links_up(self) -> bool:
        return self.mic_link_up and self.spk_link_up

    def to_dict(self) -> dict:
        """Serialize for JSON telemetry."""
        return {
            "clear_conf": round(self.clear_confidence, 2),
            "ball_conf": round(self.ball_confidence, 2),
            "ball_bearing": round(self.ball_bearing_deg, 1),
            "vision_fps": round(self.vision_fps, 1),
            "vision_age_ms": round(self.vision_age_ms, 1),
            "speaking": self.speaking,
            "current_energy": self.current_energy,
            "ptt_active": self.ptt_active,
            "planner_connected": self.planner_connected,
            "planner_enabled": self.planner_enabled,
            "active_skill": self.active_skill,
            "last_plan_mono_ms": round(self.last_plan_mono_ms, 1),
            "last_plan_actions": self.last_plan_actions,
            "last_plan_error": self.last_plan_error,
            "plan_dropped_stale": self.plan_dropped_stale,
            "plan_dropped_cooldown": self.plan_dropped_cooldown,
            "plan_dropped_out_of_order": self.plan_dropped_out_of_order,
            "plan_dropped_duplicate": self.plan_dropped_duplicate,
            "say_requested": self.say_requested,
            "say_enqueued": self.say_enqueued,
            "event_count": self.event_count,
            "worker_alive": dict(self.worker_alive),
            "mic_link_up": self.mic_link_up,
            "spk_link_up": self.spk_link_up,
            "session_id": self.session_id,
            "ai_state": self.ai_state,
            "personality_mood": self.personality_mood,
            "personality_intensity": round(self.personality_intensity, 3),
            "personality_valence": round(self.personality_valence, 3),
            "personality_arousal": round(self.personality_arousal, 3),
            "personality_layer": self.personality_layer,
            "personality_idle_state": self.personality_idle_state,
            "personality_conversation_active": self.personality_conversation_active,
            "personality_session_time_s": round(self.personality_session_time_s, 1),
            "personality_daily_time_s": round(self.personality_daily_time_s, 1),
            "personality_session_limit_reached": self.personality_session_limit_reached,
            "personality_daily_limit_reached": self.personality_daily_limit_reached,
        }
