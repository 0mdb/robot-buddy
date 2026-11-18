"""The robot's name reaches every model-facing prompt (app/llm/persona.py)."""

from __future__ import annotations

from app.llm.audience import available_profiles, load_profile
from app.llm.conversation import build_system_prompt
from app.llm.persona import IDENTITY, ROBOT_NAME
from app.llm.prompts import SYSTEM_PROMPT


def test_every_profile_prompt_names_the_robot() -> None:
    for pid in available_profiles():
        prompt = build_system_prompt(pid)
        assert f"You are {ROBOT_NAME}," in prompt, pid
        assert IDENTITY in prompt, pid
        assert "{name}" not in prompt, pid
        assert "Buddy" not in prompt, pid


def test_profile_examples_have_the_name_filled() -> None:
    for pid in available_profiles():
        for ex in load_profile(pid).examples:
            for v in ex.values():
                assert not (isinstance(v, str) and "{name}" in v), pid


def test_planner_prompt_names_the_robot() -> None:
    assert f"You are {ROBOT_NAME}," in SYSTEM_PROMPT
    assert "Buddy" not in SYSTEM_PROMPT
