"""Tests for runtime planner-to-face dispatch behavior."""

from __future__ import annotations

import time
from types import SimpleNamespace

from supervisor.devices.planner_client import PlannerPlan
from supervisor.devices.protocol import FaceButtonEventType, FaceButtonId, FaceGesture, FaceMood
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

    def subscribe_button(self, cb) -> None:
        del cb

    def subscribe_touch(self, cb) -> None:
        del cb


class _FakeAudio:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.speech_queue_depth = 0

    def enqueue_speech(self, text: str, *, emotion: str = "neutral") -> bool:
        del emotion
        self.said.append(text)
        return True

    def debug_snapshot(self) -> dict:
        return {"speech_queue_depth": len(self.said)}


def test_planner_plan_emote_and_gesture_dispatch_uses_canonical_mapping():
    face = _FakeFace()
    runtime = Runtime(reflex=_FakeReflex(), face=face)
    plan = PlannerPlan(
        actions=[
            {"action": "emote", "name": "tired", "intensity": 0.4},
            {"action": "gesture", "name": "head-shake"},
        ],
        ttl_ms=1000,
    )

    runtime._planner_task_started_mono_ms = time.monotonic() * 1000.0
    runtime._apply_planner_plan(plan)
    runtime._execute_due_planner_actions()

    assert len(face.state_calls) == 1
    assert face.state_calls[0]["emotion_id"] == int(FaceMood.SLEEPY)
    assert face.state_calls[0]["intensity"] == 0.4
    assert face.gesture_calls == [int(FaceGesture.HEADSHAKE)]


def test_planner_plan_face_actions_are_suppressed_while_listening_or_talking():
    face = _FakeFace()
    runtime = Runtime(reflex=_FakeReflex(), face=face)
    runtime.state.face_listening = True
    runtime.state.face_talking = True
    plan = PlannerPlan(
        actions=[
            {"action": "emote", "name": "happy", "intensity": 0.9},
            {"action": "gesture", "name": "wink_l"},
        ],
        ttl_ms=1000,
    )

    runtime._planner_task_started_mono_ms = time.monotonic() * 1000.0
    runtime._apply_planner_plan(plan)
    runtime._execute_due_planner_actions()

    assert face.state_calls == []
    assert face.gesture_calls == []


def test_action_button_triggers_greet_routine_with_cooldown():
    face = _FakeFace()
    audio = _FakeAudio()
    runtime = Runtime(reflex=_FakeReflex(), face=face, audio=audio)
    now_ms = time.monotonic() * 1000.0
    evt = SimpleNamespace(
        button_id=int(FaceButtonId.ACTION),
        event_type=int(FaceButtonEventType.CLICK),
        state=1,
        timestamp_mono_ms=now_ms,
    )

    runtime._on_face_button(evt)
    runtime.state.tick_mono_ms = now_ms
    runtime._execute_due_planner_actions()

    assert face.state_calls
    assert face.gesture_calls
    assert audio.said == ["Hi friend!"]

    runtime._on_face_button(evt)
    runtime._execute_due_planner_actions()
    assert audio.said == ["Hi friend!"]
