"""The robot's name as the language models know it.

One place, so it can change later: ``ROBOT_NAME`` in the server's environment (default
"Alexa", 2026-11-18: the wake word is "alexa", so the family already calls her that). The
project and code keep calling the robot Buddy; only what the models read and say uses this.
"""

from __future__ import annotations

import os

ROBOT_NAME = os.environ.get("ROBOT_NAME", "").strip() or "Alexa"

# Said once in every system prompt, right after the intro.
IDENTITY = (
    f"Your name is {ROBOT_NAME}, and you are a girl robot (she/her). When someone says"
    f' "{ROBOT_NAME}", they are talking to you. You are not a smart speaker or a shopping'
    " assistant: you are this family's own little robot."
)


def with_name(text: str) -> str:
    """Fill ``{name}`` in profile text (intros, examples)."""
    return text.replace("{name}", ROBOT_NAME)
