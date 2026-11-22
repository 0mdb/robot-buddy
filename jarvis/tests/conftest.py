from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.config import Settings
from jarvis.main import create_app

TOKEN = "t" * 24
OLLAMA = "http://ollama.test"
HA = "http://ha.test"


def make_settings(tmp_path: Path, **over) -> Settings:
    base = {
        "data_dir": tmp_path,
        "device_tokens": {TOKEN: "cli"},
        "owners": ("owner",),
        "ollama_url": OLLAMA,
        "model": "test-model",
        "ha_url": HA,
        "ha_token": "ha-token",
        "ha_domains": ("light", "cover", "sensor"),
    }
    base.update(over)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Jarvis-User": "owner"}


def chat_reply(content: str = "", tool_calls: list | None = None) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"message": msg, "done": True}


def tool_call(name: str, **args) -> dict:
    return {"function": {"name": name, "arguments": args}}
