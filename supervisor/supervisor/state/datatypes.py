"""Core data types for supervisor state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from supervisor.devices.expressions import FACE_MOOD_TO_EMOTION
from supervisor.devices.protocol import Fault, RangeStatus


class Mode(str, Enum):
    BOOT = "BOOT"
    IDLE = "IDLE"
    TELEOP = "TELEOP"
    WANDER = "WANDER"
    ERROR = "ERROR"
    # Deferred modes (TODO)
    # LINE_FOLLOW = "LINE_FOLLOW"
    # BALL = "BALL"
    # CRANE = "CRANE"
    # CHARGING = "CHARGING"
    # SLEEP = "SLEEP"


# Modes that allow motion commands
MOTION_MODES = frozenset({Mode.TELEOP, Mode.WANDER})


@dataclass(slots=True)
class DesiredTwist:
    v_mm_s: int = 0
    w_mrad_s: int = 0


@dataclass(slots=True)
class SpeedCap:
    """Describes a speed limitation and why it was applied."""

    scale: float = 1.0  # 0.0 to 1.0 multiplier
    reason: str = ""


@dataclass(slots=True)
class RobotState:
    """Aggregated snapshot of the entire robot state, rebuilt each tick."""

    mode: Mode = Mode.BOOT

    # Motion
    twist_cmd: DesiredTwist = field(default_factory=DesiredTwist)
    twist_capped: DesiredTwist = field(default_factory=DesiredTwist)

    # Reflex telemetry (latest)
    speed_l_mm_s: int = 0
    speed_r_mm_s: int = 0
    gyro_z_mrad_s: int = 0
    battery_mv: int = 0
    fault_flags: int = 0
    range_mm: int = 0
    range_status: int = RangeStatus.NOT_READY
    reflex_seq: int = 0
    reflex_rx_mono_ms: float = 0.0

    # Computed from wheel speeds
    v_meas_mm_s: float = 0.0
    w_meas_mrad_s: float = 0.0

    # Connection state
    reflex_connected: bool = False
    face_connected: bool = False
    planner_enabled: bool = False
    planner_connected: bool = False

    # Face telemetry
    face_mood: int = 0
    face_gesture: int = 0xFF  # 0xFF = none
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
    face_seq: int = 0
    face_rx_mono_ms: float = 0.0

    # Planner server
    planner_last_plan_mono_ms: float = 0.0
    planner_last_plan_actions: int = 0
    planner_last_error: str = ""
    planner_last_plan: list[dict] | None = None
    planner_active_skill: str = "patrol_drift"
    planner_event_count: int = 0
    planner_plan_dropped_stale: int = 0
    planner_plan_dropped_cooldown: int = 0
    planner_plan_dropped_out_of_order: int = 0
    planner_plan_dropped_duplicate: int = 0
    planner_speech_queue_depth: int = 0
    planner_say_requested: int = 0
    planner_say_enqueued: int = 0
    planner_say_dropped_reason: dict[str, int] = field(default_factory=dict)

    # Safety
    speed_caps: list[SpeedCap] = field(default_factory=list)

    # Vision
    clear_confidence: float = -1.0  # -1 = no data
    ball_confidence: float = 0.0
    ball_bearing_deg: float = 0.0
    vision_age_ms: float = -1.0
    vision_fps: float = 0.0

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
            "battery_mv": self.battery_mv,
            "fault_flags": self.fault_flags,
            "range_mm": self.range_mm,
            "range_status": self.range_status,
            "reflex_connected": self.reflex_connected,
            "face_connected": self.face_connected,
            "planner_enabled": self.planner_enabled,
            "planner_connected": self.planner_connected,
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
            "face_seq": self.face_seq,
            "face_rx_mono_ms": round(self.face_rx_mono_ms, 1),
            "planner_last_plan_mono_ms": round(self.planner_last_plan_mono_ms, 1),
            "planner_last_plan_actions": self.planner_last_plan_actions,
            "planner_last_error": self.planner_last_error,
            "planner_last_plan": self.planner_last_plan,
            "planner_active_skill": self.planner_active_skill,
            "planner_event_count": self.planner_event_count,
            "planner_plan_dropped_stale": self.planner_plan_dropped_stale,
            "planner_plan_dropped_cooldown": self.planner_plan_dropped_cooldown,
            "planner_plan_dropped_out_of_order": self.planner_plan_dropped_out_of_order,
            "planner_plan_dropped_duplicate": self.planner_plan_dropped_duplicate,
            "planner_speech_queue_depth": self.planner_speech_queue_depth,
            "planner_say_requested": self.planner_say_requested,
            "planner_say_enqueued": self.planner_say_enqueued,
            "planner_say_dropped_reason": dict(self.planner_say_dropped_reason),
            "speed_caps": [
                {"scale": c.scale, "reason": c.reason} for c in self.speed_caps
            ],
            "tick_dt_ms": round(self.tick_dt_ms, 2),
            "clear_conf": round(self.clear_confidence, 2),
            "ball_conf": round(self.ball_confidence, 2),
            "ball_bearing": round(self.ball_bearing_deg, 1),
            "vision_age_ms": round(self.vision_age_ms, 1),
            "vision_fps": round(self.vision_fps, 1),
        }
