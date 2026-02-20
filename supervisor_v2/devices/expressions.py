"""Canonical supervisor-side mappings for face emotions and gestures."""

from __future__ import annotations

from typing import Final

from supervisor_v2.devices.protocol import FaceGesture, FaceMood


CANONICAL_EMOTIONS: Final[tuple[str, ...]] = (
    "neutral",
    "happy",
    "excited",
    "curious",
    "sad",
    "scared",
    "angry",
    "surprised",
    "sleepy",
    "love",
    "silly",
    "thinking",
)

EMOTION_ALIASES: Final[dict[str, str]] = {
    "tired": "sleepy",
}

EMOTION_TO_FACE_MOOD: Final[dict[str, int]] = {
    "neutral": int(FaceMood.NEUTRAL),
    "happy": int(FaceMood.HAPPY),
    "excited": int(FaceMood.EXCITED),
    "curious": int(FaceMood.CURIOUS),
    "sad": int(FaceMood.SAD),
    "scared": int(FaceMood.SCARED),
    "angry": int(FaceMood.ANGRY),
    "surprised": int(FaceMood.SURPRISED),
    "sleepy": int(FaceMood.SLEEPY),
    "love": int(FaceMood.LOVE),
    "silly": int(FaceMood.SILLY),
    "thinking": int(FaceMood.THINKING),
}

FACE_MOOD_TO_EMOTION: Final[dict[int, str]] = {
    v: k for k, v in EMOTION_TO_FACE_MOOD.items()
}


CANONICAL_FACE_GESTURES: Final[tuple[str, ...]] = (
    "blink",
    "wink_l",
    "wink_r",
    "confused",
    "laugh",
    "surprise",
    "heart",
    "x_eyes",
    "sleepy",
    "rage",
    "nod",
    "headshake",
    "wiggle",
)

GESTURE_ALIASES: Final[dict[str, str]] = {
    "head_shake": "headshake",
    "head-shake": "headshake",
    "xeyes": "x_eyes",
    "x-eyes": "x_eyes",
}

GESTURE_TO_FACE_ID: Final[dict[str, int]] = {
    "blink": int(FaceGesture.BLINK),
    "wink_l": int(FaceGesture.WINK_L),
    "wink_r": int(FaceGesture.WINK_R),
    "confused": int(FaceGesture.CONFUSED),
    "laugh": int(FaceGesture.LAUGH),
    "surprise": int(FaceGesture.SURPRISE),
    "heart": int(FaceGesture.HEART),
    "x_eyes": int(FaceGesture.X_EYES),
    "sleepy": int(FaceGesture.SLEEPY),
    "rage": int(FaceGesture.RAGE),
    "nod": int(FaceGesture.NOD),
    "headshake": int(FaceGesture.HEADSHAKE),
    "wiggle": int(FaceGesture.WIGGLE),
}


def normalize_emotion_name(name: str) -> str | None:
    key = name.strip().lower()
    key = EMOTION_ALIASES.get(key, key)
    return key if key in EMOTION_TO_FACE_MOOD else None


def normalize_face_gesture_name(name: str) -> str | None:
    key = name.strip().lower()
    key = GESTURE_ALIASES.get(key, key)
    return key if key in GESTURE_TO_FACE_ID else None
