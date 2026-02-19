from __future__ import annotations

from supervisor.planner.event_bus import PlannerEventBus
from supervisor.state.datatypes import Mode, RobotState


def _state(**updates) -> RobotState:
    s = RobotState()
    for k, v in updates.items():
        setattr(s, k, v)
    return s


def test_ball_acquired_and_lost_edges():
    bus = PlannerEventBus()
    s = _state(mode=Mode.IDLE, tick_mono_ms=1000.0, ball_confidence=0.2)
    bus.ingest_state(s)
    assert bus.event_count == 0

    s.tick_mono_ms = 1200.0
    s.ball_confidence = 0.7
    s.ball_bearing_deg = 12.0
    bus.ingest_state(s)
    assert bus.latest(limit=1)[0].type == "vision.ball_acquired"

    s.tick_mono_ms = 1500.0
    s.ball_confidence = 0.1
    bus.ingest_state(s)
    assert bus.latest(limit=1)[0].type == "vision.ball_lost"


def test_mode_change_and_fault_edges():
    bus = PlannerEventBus()
    s = _state(mode=Mode.IDLE, tick_mono_ms=1000.0, fault_flags=0)
    bus.ingest_state(s)

    s.tick_mono_ms = 1100.0
    s.mode = Mode.WANDER
    bus.ingest_state(s)
    assert bus.latest(limit=1)[0].type == "mode.changed"

    s.tick_mono_ms = 1200.0
    s.fault_flags = 2
    bus.ingest_state(s)
    assert bus.latest(limit=1)[0].type == "fault.raised"

    s.tick_mono_ms = 1300.0
    s.fault_flags = 0
    bus.ingest_state(s)
    assert bus.latest(limit=1)[0].type == "fault.cleared"


def test_events_since_sequence_cursor():
    bus = PlannerEventBus()
    s = _state(mode=Mode.IDLE, tick_mono_ms=1000.0, ball_confidence=0.1)
    bus.ingest_state(s)

    s.tick_mono_ms = 1200.0
    s.ball_confidence = 0.8
    bus.ingest_state(s)
    first = bus.latest(limit=1)[0]

    s.tick_mono_ms = 1400.0
    s.ball_confidence = 0.1
    bus.ingest_state(s)

    newer = bus.events_since(first.seq)
    assert [e.type for e in newer] == ["vision.ball_lost"]
