"""Canonical expression and gesture vocabularies for server LLM contracts."""

from __future__ import annotations

from typing import Final


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


FACE_GESTURES: Final[tuple[str, ...]] = (
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

BODY_GESTURES: Final[tuple[str, ...]] = (
    "look_at",
    "spin",
    "back_up",
)

GESTURE_ALIASES: Final[dict[str, str]] = {
    "head_shake": "headshake",
    "head-shake": "headshake",
    "xeyes": "x_eyes",
    "x-eyes": "x_eyes",
}


def normalize_emotion_name(name: str) -> str | None:
    key = name.strip().lower()
    key = EMOTION_ALIASES.get(key, key)
    return key if key in CANONICAL_EMOTIONS else None


def normalize_gesture_name(name: str, *, allow_body: bool) -> str | None:
    key = name.strip().lower()
    key = GESTURE_ALIASES.get(key, key)
    allowed = FACE_GESTURES + BODY_GESTURES if allow_body else FACE_GESTURES
    return key if key in allowed else None
