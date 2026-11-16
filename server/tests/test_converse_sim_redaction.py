"""Household names never reach an external API (operator, 2026-11-16)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.eval import converse_sim as cs


class _FakeMessages:
    def __init__(self) -> None:
        self.sent: dict[str, Any] = {}

    async def create(self, **kw: Any) -> Any:
        self.sent = kw
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")], stop_reason="end_turn"
        )


def test_names_are_redacted_before_the_claude_api() -> None:
    cs.set_external_redactions({"Kid A": "[child]", "Rex": "[pet]"})
    try:
        msgs = _FakeMessages()
        client = SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs))
        chat = cs.anthropic_chat(client=client)
        asyncio.run(
            chat(
                [
                    {"role": "system", "content": "Judge Buddy talking with Kid A."},
                    {"role": "user", "content": "kid a: can Rex play?"},
                    {"role": "assistant", "content": "Hi Kid A! Rex is napping."},
                ],
                None,
                0.0,
            )
        )
        blob = str(msgs.sent)
        assert "Kid A" not in blob and "kid a" not in blob and "Rex" not in blob
        assert "[child]" in blob and "[pet]" in blob
    finally:
        cs.set_external_redactions({})
