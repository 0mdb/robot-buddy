"""The tool-pass gate never skips a turn that needs a tool (app.llm.preamble)."""

from __future__ import annotations

import pytest

from app.eval.harness import NO_TOOL, SCENARIOS
from app.llm.preamble import needs_tool_pass

TOOL_TURNS = [s.user_text for s in SCENARIOS if s.expected_tool != NO_TOOL]


@pytest.mark.parametrize("text", TOOL_TURNS)
def test_every_tool_scenario_passes_the_gate(text: str) -> None:
    assert needs_tool_pass(text)


@pytest.mark.parametrize(
    "text",
    [
        "Yes it is!",
        "No, it doesn't.",
        "Is it big?",
        "Can we play twenty questions?",
        "Once there was a dragon and he was really big.",
        "Tell me a joke.",
        "Why is the sky blue?",
    ],
)
def test_ordinary_turns_skip_it(text: str) -> None:
    assert not needs_tool_pass(text)
