"""Event bus with edge detection over runtime snapshots."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from supervisor.devices.protocol import (
    FaceButtonEventType,
    Fault,
    RangeStatus,
    TouchEventType,
)
from supervisor.state.datatypes import Mode, RobotState


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

    def ingest_state(self, state: RobotState) -> None:
        """Run edge detection against latest aggregated RobotState."""
        now_ms = float(state.tick_mono_ms)

        if self._last_mode is None:
            self._last_mode = state.mode
        elif state.mode != self._last_mode:
            self.emit(
                "mode.changed",
                {"from": self._last_mode.value, "to": state.mode.value},
                now_ms,
            )
            self._last_mode = state.mode

        effective_ball_conf = (
            float(state.ball_confidence) if self._ball_signal_valid(state) else 0.0
        )

        if not self._ball_visible and effective_ball_conf >= self._ball_acquire_conf:
            self._ball_visible = True
            self.emit(
                "vision.ball_acquired",
                {
                    "confidence": round(effective_ball_conf, 3),
                    "bearing_deg": round(float(state.ball_bearing_deg), 1),
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

        obstacle_now = (
            state.range_status == int(RangeStatus.OK)
            and state.range_mm > 0
            and state.range_mm < self._obstacle_close_mm
        )
        obstacle_clear_now = (
            state.range_status != int(RangeStatus.OK)
            or state.range_mm <= 0
            or state.range_mm > self._obstacle_clear_mm
        )
        if not self._obstacle_close and obstacle_now:
            self._obstacle_close = True
            self.emit(
                "safety.obstacle_close",
                {"range_mm": int(state.range_mm)},
                now_ms,
            )
        elif self._obstacle_close and obstacle_clear_now:
            self._obstacle_close = False
            self.emit(
                "safety.obstacle_cleared",
                {"range_mm": int(state.range_mm)},
                now_ms,
            )

        vision_healthy_now = (
            state.vision_age_ms >= 0 and state.vision_age_ms <= self._vision_stale_ms
        )
        if self._vision_healthy is None:
            self._vision_healthy = vision_healthy_now
        elif vision_healthy_now != self._vision_healthy:
            self._vision_healthy = vision_healthy_now
            self.emit(
                "vision.healthy" if vision_healthy_now else "vision.stale",
                {"vision_age_ms": round(float(state.vision_age_ms), 1)},
                now_ms,
            )

        if self._last_fault_flags == 0 and state.fault_flags != 0:
            self.emit(
                "fault.raised",
                {
                    "flags": int(state.fault_flags),
                    "faults": self._fault_names(state.fault_flags),
                },
                now_ms,
            )
        elif self._last_fault_flags != 0 and state.fault_flags == 0:
            self.emit(
                "fault.cleared",
                {
                    "flags": int(self._last_fault_flags),
                    "faults": self._fault_names(self._last_fault_flags),
                },
                now_ms,
            )
        self._last_fault_flags = int(state.fault_flags)

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

    def _ball_signal_valid(self, state: RobotState) -> bool:
        vision_fresh = 0.0 <= state.vision_age_ms <= self._vision_stale_ms
        clear_ok = (
            state.clear_confidence < 0.0
            or state.clear_confidence >= self._ball_clear_min_conf
        )
        return vision_fresh and clear_ok and int(state.fault_flags) == 0
