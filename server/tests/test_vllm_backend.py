"""Unit tests for vLLM backend parsing, retry behavior, and chat templates."""

from __future__ import annotations

import pytest

from app.llm.conversation import ConversationHistory
from app.llm.model_config import resolve_template_config
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


# ── Existing plan/conversation tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_vllm_generate_plan_retries_on_bad_json():
    backend = VLLMBackend()
    calls = {"n": 0}

    async def _fake_generate_text(
        prompt: str, *, request_tag: str, **_kw: object
    ) -> str:
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
async def test_vllm_generate_plan_tolerates_trailing_text():
    backend = VLLMBackend()

    async def _fake_generate_text(
        prompt: str, *, request_tag: str, **_kw: object
    ) -> str:
        del prompt, request_tag
        return (
            '{"actions":[{"action":"say","text":"Hi"}],"ttl_ms":2000}\n'
            "extra trailing text"
        )

    backend._generate_text = _fake_generate_text  # type: ignore[method-assign]

    plan = await backend.generate_plan(_world_state())
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "say"


@pytest.mark.asyncio
async def test_vllm_generate_plan_uses_first_json_object():
    backend = VLLMBackend()

    async def _fake_generate_text(
        prompt: str, *, request_tag: str, **_kw: object
    ) -> str:
        del prompt, request_tag
        return (
            '{"actions":[{"action":"say","text":"Hi"}],"ttl_ms":2000}\n'
            '{"actions":[{"action":"say","text":"Ignore me"}],"ttl_ms":3000}'
        )

    backend._generate_text = _fake_generate_text  # type: ignore[method-assign]

    plan = await backend.generate_plan(_world_state())
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "say"


@pytest.mark.asyncio
async def test_vllm_generate_conversation_parses_response():
    backend = VLLMBackend()

    async def _fake_generate_text(
        prompt: str,
        *,
        request_tag: str,
        guided_json_schema: object = None,
        override_temperature: float | None = None,
        override_max_output_tokens: int | None = None,
    ) -> str:
        del prompt, request_tag, guided_json_schema
        del override_temperature, override_max_output_tokens
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


# ── Chat template tests ───────────────────────────────────────────────


class _MockTokenizer:
    """Records calls to apply_chat_template for assertion."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool = True,
        add_generation_prompt: bool = False,
        **kwargs: object,
    ) -> str:
        self.calls.append(
            {
                "messages": list(messages),
                "tokenize": tokenize,
                "add_generation_prompt": add_generation_prompt,
                **kwargs,
            }
        )
        # Return a ChatML-like string for testing.
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        if add_generation_prompt:
            parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)


class TestChatTemplate:
    """Chat template formatting for plan and conversation prompts."""

    def test_plan_prompt_uses_chat_template(self):
        backend = VLLMBackend()
        tok = _MockTokenizer()
        backend._tokenizer = tok
        backend._template_kwargs = {"_family": "qwen3"}

        messages = backend._build_plan_messages(_world_state())
        result = backend._apply_chat_template(messages)

        # Verify tokenizer was called once.
        assert len(tok.calls) == 1
        call = tok.calls[0]
        assert call["tokenize"] is False
        assert call["add_generation_prompt"] is True

        # Verify messages structure: system + user.
        msgs = call["messages"]
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "planner" in msgs[0]["content"].lower()
        assert msgs[1]["role"] == "user"
        assert "Mode: IDLE" in msgs[1]["content"]
        assert "valid JSON" in msgs[1]["content"]

        # Verify output has ChatML tokens.
        assert "<|im_start|>system" in result
        assert "<|im_start|>user" in result
        assert "<|im_start|>assistant" in result

    def test_conversation_prompt_uses_chat_template(self):
        backend = VLLMBackend()
        tok = _MockTokenizer()
        backend._tokenizer = tok
        backend._template_kwargs = {"_family": "qwen3"}

        history = ConversationHistory(max_turns=10)
        history.add_user("Why is the sky blue?")
        history.add_assistant("Because of scattering!", emotion="curious")
        history.add_user("Tell me more")

        messages = history.to_ollama_messages()
        result = backend._apply_chat_template(messages)

        assert len(tok.calls) == 1
        call = tok.calls[0]
        assert call["tokenize"] is False
        assert call["add_generation_prompt"] is True

        # Verify the messages contain system prompt + conversation turns.
        msgs = call["messages"]
        roles = [m["role"] for m in msgs]
        assert "system" in roles
        assert "user" in roles
        assert "assistant" in roles

        # Verify output format.
        assert "<|im_start|>system" in result
        assert "sky blue" in result

    def test_fallback_without_tokenizer(self):
        """When no tokenizer is loaded, the flat ROLE: format is used."""
        backend = VLLMBackend()
        assert backend._tokenizer is None

        messages = backend._build_plan_messages(_world_state())
        result = backend._apply_chat_template(messages)

        # Should use the flat legacy format.
        assert "SYSTEM:" in result
        assert "USER:" in result
        assert "ASSISTANT:" in result
        # Should NOT have ChatML tokens.
        assert "<|im_start|>" not in result

    def test_enable_thinking_passed_to_template(self):
        backend = VLLMBackend()
        tok = _MockTokenizer()
        backend._tokenizer = tok
        backend._template_kwargs = {
            "enable_thinking": False,
            "_family": "qwen3",
        }

        messages = [{"role": "user", "content": "hello"}]
        backend._apply_chat_template(messages)

        assert len(tok.calls) == 1
        assert tok.calls[0].get("enable_thinking") is False

    def test_enable_thinking_true_when_configured(self):
        backend = VLLMBackend()
        tok = _MockTokenizer()
        backend._tokenizer = tok
        backend._template_kwargs = {
            "enable_thinking": True,
            "_family": "qwen3",
        }

        messages = [{"role": "user", "content": "hello"}]
        backend._apply_chat_template(messages)

        assert tok.calls[0].get("enable_thinking") is True

    def test_unsupported_kwargs_fallback(self):
        """If template doesn't support kwargs, retry without them."""

        class _StrictTokenizer:
            def __init__(self) -> None:
                self.call_count = 0

            def apply_chat_template(
                self, messages, *, tokenize=True, add_generation_prompt=False, **kwargs
            ):
                self.call_count += 1
                if kwargs:
                    raise TypeError(
                        f"unexpected keyword argument: {list(kwargs.keys())}"
                    )
                return "fallback-output"

        backend = VLLMBackend()
        backend._tokenizer = _StrictTokenizer()
        backend._template_kwargs = {"enable_thinking": False, "_family": "test"}

        result = backend._apply_chat_template([{"role": "user", "content": "hi"}])

        assert result == "fallback-output"
        assert backend._tokenizer.call_count == 2  # first fails, retry succeeds


class TestPlanRepairLoop:
    """Verify the JSON repair loop appends a message, not a string suffix."""

    @pytest.mark.asyncio
    async def test_plan_repair_appends_message(self):
        backend = VLLMBackend()
        prompts_seen: list[str] = []
        calls = {"n": 0}

        async def _fake_generate_text(prompt: str, *, request_tag: str) -> str:
            del request_tag
            prompts_seen.append(prompt)
            calls["n"] += 1
            if calls["n"] == 1:
                return "not-json"
            return '{"actions":[{"action":"say","text":"retry"}],"ttl_ms":2000}'

        backend._generate_text = _fake_generate_text  # type: ignore[method-assign]

        plan = await backend.generate_plan(_world_state())
        assert calls["n"] == 2
        assert len(plan.actions) == 1

        # Second prompt should be longer than the first (repair message added).
        assert len(prompts_seen) == 2
        assert len(prompts_seen[1]) > len(prompts_seen[0])
        # The repair text should appear in the second prompt.
        assert "invalid" in prompts_seen[1].lower()


# ── Model config resolution tests ─────────────────────────────────────


class TestModelConfigResolution:
    """resolve_template_config matches model name patterns."""

    def test_qwen3_model_resolved(self):
        cfg = resolve_template_config("Qwen/Qwen3-8B-Instruct-AWQ")
        assert cfg.family == "qwen3"
        assert cfg.chat_template_kwargs.get("enable_thinking") is False

    def test_qwen2_model_resolved(self):
        cfg = resolve_template_config("Qwen/Qwen2.5-7B-Instruct")
        assert cfg.family == "qwen2"
        assert "enable_thinking" not in cfg.chat_template_kwargs

    def test_llama_model_resolved(self):
        cfg = resolve_template_config("meta-llama/Llama-3.2-3B-Instruct")
        assert cfg.family == "llama"

    def test_unknown_model_gets_default(self):
        cfg = resolve_template_config("some-custom/model-v1")
        assert cfg.family == "default"
        assert cfg.chat_template_kwargs == {}

    def test_case_insensitive(self):
        cfg = resolve_template_config("QWEN/QWEN3-8B")
        assert cfg.family == "qwen3"

    def test_debug_snapshot_includes_template_info(self):
        backend = VLLMBackend()
        backend._template_kwargs = {"_family": "qwen3"}
        snap = backend.debug_snapshot()
        assert snap["chat_template"] is False  # no tokenizer loaded
        assert snap["model_family"] == "qwen3"
