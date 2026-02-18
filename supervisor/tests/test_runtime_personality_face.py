"""Tests for runtime personality-to-face dispatch behavior."""

from __future__ import annotations

from supervisor.devices.personality_client import PersonalityPlan
from supervisor.devices.protocol import FaceGesture, FaceMood
from supervisor.runtime import Runtime


class _FakeReflex:
    connected = True


class _FakeFace:
    def __init__(self) -> None:
        self.connected = True
        self.state_calls: list[dict] = []
        self.gesture_calls: list[int] = []

    def send_state(self, **kwargs) -> None:
        self.state_calls.append(kwargs)

    def send_gesture(self, gesture_id: int, duration_ms: int = 0) -> None:
        del duration_ms
        self.gesture_calls.append(gesture_id)


def test_personality_plan_emote_and_gesture_dispatch_uses_canonical_mapping():
    face = _FakeFace()
    runtime = Runtime(reflex=_FakeReflex(), face=face)
    plan = PersonalityPlan(
        actions=[
            {"action": "emote", "name": "tired", "intensity": 0.4},
            {"action": "gesture", "name": "head-shake"},
        ],
        ttl_ms=1000,
    )

    runtime._apply_personality_plan(plan)

    assert len(face.state_calls) == 1
    assert face.state_calls[0]["emotion_id"] == int(FaceMood.SLEEPY)
    assert face.state_calls[0]["intensity"] == 0.4
    assert face.gesture_calls == [int(FaceGesture.HEADSHAKE)]


def test_personality_plan_face_actions_are_suppressed_while_listening_or_talking():
    face = _FakeFace()
    runtime = Runtime(reflex=_FakeReflex(), face=face)
    runtime.state.face_listening = True
    runtime.state.face_talking = True
    plan = PersonalityPlan(
        actions=[
            {"action": "emote", "name": "happy", "intensity": 0.9},
            {"action": "gesture", "name": "wink_l"},
        ],
        ttl_ms=1000,
    )

    runtime._apply_personality_plan(plan)

    assert face.state_calls == []
    assert face.gesture_calls == []
