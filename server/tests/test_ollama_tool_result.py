"""Ollama path: a look() frame rides on the tool message as a base64 image."""

from __future__ import annotations

import base64

from PIL import Image

from app.llm.conversation import _ollama_image_messages


def test_image_parts_become_ollama_images() -> None:
    img = Image.new("RGB", (8, 8), (200, 0, 0))
    msgs = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [{"type": "text", "text": "Camera view:"}, {"type": "image"}],
        },
        {"role": "user", "content": "what is this?"},
    ]
    out = _ollama_image_messages(msgs, [img])
    assert out[0] == msgs[0] and out[2] == msgs[2]
    assert out[1]["content"] == "Camera view:"
    assert len(out[1]["images"]) == 1
    assert base64.b64decode(out[1]["images"][0])[:2] == b"\xff\xd8"  # a JPEG


def test_text_only_messages_pass_through() -> None:
    msgs = [{"role": "user", "content": "hi"}]
    assert _ollama_image_messages(msgs, []) == msgs
