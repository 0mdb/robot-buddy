from __future__ import annotations

from supervisor.planner.event_bus import PlannerEvent
from supervisor.planner.speech_policy import SpeechPolicy
from supervisor.state.datatypes import RobotState


def test_ball_event_generates_speech_intent():
    policy = SpeechPolicy()
    state = RobotState()
    events = [
        PlannerEvent(
            type="vision.ball_acquired",
            payload={"confidence": 0.8, "bearing_deg": 10.0},
            t_mono_ms=1000.0,
            seq=1,
        )
    ]

    intents, drops = policy.generate(state=state, events=events, now_mono_ms=1000.0)
    assert len(intents) == 1
    assert intents[0].source_event == "vision.ball_acquired"
    assert intents[0].text
    assert drops == []


def test_speech_policy_cooldown_suppresses_repeat():
    policy = SpeechPolicy()
    state = RobotState()
    events = [
        PlannerEvent(
            type="vision.ball_acquired",
            payload={"confidence": 0.8, "bearing_deg": 10.0},
            t_mono_ms=1000.0,
            seq=1,
        )
    ]

    intents_1, drops_1 = policy.generate(state=state, events=events, now_mono_ms=1000.0)
    intents_2, drops_2 = policy.generate(state=state, events=events, now_mono_ms=1200.0)

    assert len(intents_1) == 1
    assert drops_1 == []
    assert intents_2 == []
    assert drops_2 == ["policy_cooldown"]


def test_speech_policy_face_busy_suppresses_speech():
    policy = SpeechPolicy()
    state = RobotState(face_talking=True)
    events = [
        PlannerEvent(
            type="mode.changed",
            payload={"from": "IDLE", "to": "WANDER"},
            t_mono_ms=2000.0,
            seq=2,
        )
    ]

    intents, drops = policy.generate(state=state, events=events, now_mono_ms=2000.0)
    assert intents == []
    assert drops == ["policy_face_busy"]
