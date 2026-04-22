"""Tests for multimodal tool_result handling in ConversationHistory.to_ollama_messages.

When the preamble returns a ToolResult with images, the history renders a
user message with mixed text+image content blocks so the chat-template
processor can emit image placeholder tokens. Text-only tool_results keep
the existing plain-system-message behavior.
"""

from __future__ import annotations

from PIL import Image

from app.llm.conversation import ConversationHistory
from app.llm.preamble import ToolResult


def _red() -> Image.Image:
    return Image.new("RGB", (8, 8), "red")


class TestToOllamaMessagesMultimodal:
    def test_text_only_tool_result_uses_system_message(self):
        history = ConversationHistory(max_turns=4)
        history.add_user("remember my favorite color?")
        tr = ToolResult(text="[tool_result] get_memory → nothing stored", images=[])

        msgs = history.to_ollama_messages(tool_result=tr)

        # Find the injected system message.
        sys_msgs = [m for m in msgs if m["role"] == "system"]
        assert any("[tool_result]" in m["content"] for m in sys_msgs)
        # No message should have list-shaped content when no image.
        assert all(not isinstance(m["content"], list) for m in msgs)

    def test_image_tool_result_uses_user_message_with_blocks(self):
        history = ConversationHistory(max_turns=4)
        history.add_user("look at my drawing!")
        tr = ToolResult(
            text="[tool_result] look → ball_detected=false", images=[_red()]
        )

        msgs = history.to_ollama_messages(tool_result=tr)

        # Find the injected user message (not the history's add_user one).
        user_msgs = [m for m in msgs if m["role"] == "user"]
        mm_msgs = [m for m in user_msgs if isinstance(m["content"], list)]
        assert len(mm_msgs) == 1, (
            f"expected exactly one multimodal user msg, got {len(mm_msgs)}"
        )
        content = mm_msgs[0]["content"]
        # Text block first, image placeholder after.
        assert content[0] == {"type": "text", "text": tr.text}
        assert content[1] == {"type": "image"}

    def test_multiple_images_emit_multiple_placeholders(self):
        history = ConversationHistory(max_turns=4)
        history.add_user("show me what you see")
        tr = ToolResult(text="meta", images=[_red(), _red()])

        msgs = history.to_ollama_messages(tool_result=tr)
        mm_msgs = [
            m for m in msgs if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(mm_msgs) == 1
        # One text + two image placeholders.
        assert mm_msgs[0]["content"].count({"type": "image"}) == 2

    def test_no_tool_result_matches_prior_behavior(self):
        history = ConversationHistory(max_turns=4)
        history.add_user("hi buddy")
        msgs = history.to_ollama_messages()
        # No injected system/user message beyond history + system prompt.
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 1  # just the add_user turn
        assert user_msgs[0]["content"] == "hi buddy"

    def test_injection_precedes_last_user_turn(self):
        history = ConversationHistory(max_turns=4)
        history.add_user("look at my drawing!")
        tr = ToolResult(text="meta", images=[_red()])
        msgs = history.to_ollama_messages(tool_result=tr)

        # The injected multimodal message must come immediately before the
        # user's "look at my drawing!" turn, so the model grounds on it.
        user_indexes = [i for i, m in enumerate(msgs) if m["role"] == "user"]
        # Multimodal user (injected) should be earlier; plain text user last.
        assert len(user_indexes) == 2
        injected_idx, real_idx = user_indexes
        assert injected_idx < real_idx
        assert isinstance(msgs[injected_idx]["content"], list)
        assert msgs[real_idx]["content"] == "look at my drawing!"
