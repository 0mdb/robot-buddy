"""Tests for canonical supervisor expression mappings."""

from __future__ import annotations

from supervisor.devices.expressions import (
    CANONICAL_EMOTIONS,
    CANONICAL_FACE_GESTURES,
    EMOTION_TO_FACE_MOOD,
    GESTURE_TO_FACE_ID,
    normalize_emotion_name,
    normalize_face_gesture_name,
)
from supervisor.devices.protocol import VALID_FACE_GESTURE_IDS, VALID_FACE_MOOD_IDS


def test_emotion_mapping_is_complete_and_exact():
    assert set(CANONICAL_EMOTIONS) == set(EMOTION_TO_FACE_MOOD)
    assert set(EMOTION_TO_FACE_MOOD.values()) == VALID_FACE_MOOD_IDS


def test_gesture_mapping_is_complete_and_exact():
    assert set(CANONICAL_FACE_GESTURES) == set(GESTURE_TO_FACE_ID)
    assert set(GESTURE_TO_FACE_ID.values()) == VALID_FACE_GESTURE_IDS


def test_alias_normalization():
    assert normalize_emotion_name("tired") == "sleepy"
    assert normalize_face_gesture_name("head-shake") == "headshake"
    assert normalize_face_gesture_name("x-eyes") == "x_eyes"
