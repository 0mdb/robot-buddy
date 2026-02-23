"""Event bus with edge detection over runtime snapshots.

Adapted from v1 to accept split RobotState + WorldState.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from supervisor_v2.devices.protocol import (
    FaceButtonEventType,
    Fault,
    RangeStatus,
    TouchEventType,
)
from supervisor_v2.core.state import Mode, RobotState, WorldState


@dataclass(slots=True)
class PlannerEvent:
    type: str
    payload: dict
    t_mono_ms: float
    seq: int = 0


class PlannerEventBus:
    """Accumulates high-level events from raw telemetry transitions."""

    def __init__(
        self,
        *,
        max_events: int = 100,
        ball_acquire_conf: float = 0.60,
        ball_lost_conf: float = 0.35,
        ball_clear_min_conf: float = 0.20,
        obstacle_close_mm: int = 450,
        obstacle_clear_mm: int = 650,
        vision_stale_ms: float = 500.0,
    ) -> None:
        self._events: deque[PlannerEvent] = deque(maxlen=max_events)

        self._ball_visible = False
        self._obstacle_close = False
        self._vision_healthy: bool | None = None
        self._last_fault_flags = 0
        self._last_mode: Mode | None = None

        self._last_button_ts = -1.0
        self._last_touch_ts = -1.0

        self._ball_acquire_conf = ball_acquire_conf
        self._ball_lost_conf = ball_lost_conf
        self._ball_clear_min_conf = ball_clear_min_conf
        self._obstacle_close_mm = obstacle_close_mm
        self._obstacle_clear_mm = obstacle_clear_mm
        self._vision_stale_ms = vision_stale_ms
        self._next_seq = 1

    def emit(self, event_type: str, payload: dict, t_mono_ms: float) -> None:
        self._events.append(
            PlannerEvent(event_type, payload, t_mono_ms, seq=self._next_seq)
        )
        self._next_seq += 1

    def on_face_button(self, evt) -> None:
        """Accept FaceClient ButtonEvent callback payload."""
        if evt.timestamp_mono_ms <= self._last_button_ts:
            return
        self._last_button_ts = evt.timestamp_mono_ms
        event_name = {
            int(FaceButtonEventType.PRESS): "press",
            int(FaceButtonEventType.RELEASE): "release",
            int(FaceButtonEventType.TOGGLE): "toggle",
            int(FaceButtonEventType.CLICK): "click",
        }.get(evt.event_type, "unknown")
        self.emit(
            f"face.button.{event_name}",
            {
                "button_id": int(evt.button_id),
                "event_type": int(evt.event_type),
                "state": int(evt.state),
            },
            float(evt.timestamp_mono_ms),
        )

    def on_face_touch(self, evt) -> None:
        """Accept FaceClient TouchEvent callback payload."""
        if evt.timestamp_mono_ms <= self._last_touch_ts:
            return
        self._last_touch_ts = evt.timestamp_mono_ms
        event_name = {
            int(TouchEventType.PRESS): "press",
            int(TouchEventType.RELEASE): "release",
            int(TouchEventType.DRAG): "drag",
        }.get(evt.event_type, "unknown")
        self.emit(
            f"face.touch.{event_name}",
            {
                "event_type": int(evt.event_type),
                "x": int(evt.x),
                "y": int(evt.y),
            },
            float(evt.timestamp_mono_ms),
        )

    def ingest(self, robot: RobotState, world: WorldState) -> None:
        """Run edge detection against combined state."""
        now_ms = float(robot.tick_mono_ms)

        # Mode transitions
        if self._last_mode is None:
            self._last_mode = robot.mode
        elif robot.mode != self._last_mode:
            self.emit(
                "mode.changed",
                {"from": self._last_mode.value, "to": robot.mode.value},
                now_ms,
            )
            self._last_mode = robot.mode

        # Ball detection (vision fields now in WorldState)
        vision_age = world.vision_age_ms
        effective_ball_conf = (
            float(world.ball_confidence)
            if self._ball_signal_valid(robot, world, vision_age)
            else 0.0
        )

        if not self._ball_visible and effective_ball_conf >= self._ball_acquire_conf:
            self._ball_visible = True
            self.emit(
                "vision.ball_acquired",
                {
                    "confidence": round(effective_ball_conf, 3),
                    "bearing_deg": round(float(world.ball_bearing_deg), 1),
                },
                now_ms,
            )
        elif self._ball_visible and effective_ball_conf < self._ball_lost_conf:
            self._ball_visible = False
            self.emit(
                "vision.ball_lost",
                {"confidence": round(effective_ball_conf, 3)},
                now_ms,
            )

        # Obstacle detection
        obstacle_now = (
            robot.range_status == int(RangeStatus.OK)
            and robot.range_mm > 0
            and robot.range_mm < self._obstacle_close_mm
        )
        obstacle_clear_now = (
            robot.range_status != int(RangeStatus.OK)
            or robot.range_mm <= 0
            or robot.range_mm > self._obstacle_clear_mm
        )
        if not self._obstacle_close and obstacle_now:
            self._obstacle_close = True
            self.emit(
                "safety.obstacle_close",
                {"range_mm": int(robot.range_mm)},
                now_ms,
            )
        elif self._obstacle_close and obstacle_clear_now:
            self._obstacle_close = False
            self.emit(
                "safety.obstacle_cleared",
                {"range_mm": int(robot.range_mm)},
                now_ms,
            )

        # Vision staleness
        vision_healthy_now = vision_age >= 0 and vision_age <= self._vision_stale_ms
        if self._vision_healthy is None:
            self._vision_healthy = vision_healthy_now
        elif vision_healthy_now != self._vision_healthy:
            self._vision_healthy = vision_healthy_now
            self.emit(
                "vision.healthy" if vision_healthy_now else "vision.stale",
                {"vision_age_ms": round(float(vision_age), 1)},
                now_ms,
            )

        # Fault transitions
        if self._last_fault_flags == 0 and robot.fault_flags != 0:
            self.emit(
                "fault.raised",
                {
                    "flags": int(robot.fault_flags),
                    "faults": self._fault_names(robot.fault_flags),
                },
                now_ms,
            )
        elif self._last_fault_flags != 0 and robot.fault_flags == 0:
            self.emit(
                "fault.cleared",
                {
                    "flags": int(self._last_fault_flags),
                    "faults": self._fault_names(self._last_fault_flags),
                },
                now_ms,
            )
        self._last_fault_flags = int(robot.fault_flags)

    def latest(self, limit: int = 20) -> list[PlannerEvent]:
        if limit <= 0:
            return []
        return list(self._events)[-limit:]

    def events_since(self, seq: int, *, limit: int = 100) -> list[PlannerEvent]:
        if limit <= 0:
            return []
        start_seq = int(seq)
        events = [e for e in self._events if e.seq > start_seq]
        return events[-limit:]

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def last_seq(self) -> int:
        if not self._events:
            return 0
        return int(self._events[-1].seq)

    def snapshot(self, limit: int = 20) -> dict:
        return {
            "event_count": len(self._events),
            "events": [asdict(e) for e in self.latest(limit)],
        }

    @staticmethod
    def _fault_names(flags: int) -> list[str]:
        names: list[str] = []
        for fault in Fault:
            if fault == Fault.NONE:
                continue
            if flags & int(fault):
                names.append(fault.name)
        return names

    def _ball_signal_valid(
        self, robot: RobotState, world: WorldState, vision_age: float
    ) -> bool:
        vision_fresh = 0.0 <= vision_age <= self._vision_stale_ms
        clear_ok = (
            world.clear_confidence < 0.0
            or world.clear_confidence >= self._ball_clear_min_conf
        )
        return vision_fresh and clear_ok and int(robot.fault_flags) == 0
