"""Unit tests for vLLM backend parsing and retry behavior."""

from __future__ import annotations

import pytest

from app.llm.conversation import ConversationHistory
from app.llm.schemas import WorldState
from app.llm.vllm_backend import VLLMBackend


def _world_state() -> WorldState:
    return WorldState(
        robot_id="robot-1",
        seq=7,
        monotonic_ts_ms=1234,
        mode="IDLE",
        battery_mv=8000,
        range_mm=1000,
    )


@pytest.mark.asyncio
async def test_vllm_generate_plan_retries_on_bad_json():
    backend = VLLMBackend()
    calls = {"n": 0}

    async def _fake_generate_text(prompt: str, *, request_tag: str) -> str:
        del prompt, request_tag
        calls["n"] += 1
        if calls["n"] == 1:
            return "not-json"
        return '{"actions":[{"action":"say","text":"Hi"}],"ttl_ms":2000}'

    backend._generate_text = _fake_generate_text  # type: ignore[method-assign]

    plan = await backend.generate_plan(_world_state())
    assert calls["n"] == 2
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "say"


@pytest.mark.asyncio
async def test_vllm_generate_conversation_parses_response():
    backend = VLLMBackend()

    async def _fake_generate_text(prompt: str, *, request_tag: str) -> str:
        del prompt, request_tag
        return (
            '{"emotion":"excited","intensity":0.9,'
            '"text":"Hello there!","gestures":["nod"]}'
        )

    backend._generate_text = _fake_generate_text  # type: ignore[method-assign]
    history = ConversationHistory(max_turns=5)

    response = await backend.generate_conversation(history, "say hi")
    assert response.emotion == "excited"
    assert response.text == "Hello there!"
    assert response.gestures == ["nod"]
    assert history.turn_count == 1
