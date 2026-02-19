"""Tests for /converse robot session ownership and preemption."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.admission import ConverseSessionRegistry
from app.routers.converse import router as converse_router


class _FakeLLM:
    async def generate_conversation(self, history, user_text):
        del history, user_text
        return None


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(converse_router)
    app.state.converse_registry = ConverseSessionRegistry()
    app.state.llm = _FakeLLM()
    return app


def test_converse_requires_robot_id():
    app = _make_app()
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/converse"):
                pass
    assert exc.value.code == 4400


def test_converse_same_robot_preempts_older_session():
    app = _make_app()
    with TestClient(app) as client:
        with client.websocket_connect("/converse?robot_id=robot-1") as ws1:
            assert ws1.receive_json()["type"] == "listening"

            with client.websocket_connect("/converse?robot_id=robot-1") as ws2:
                assert ws2.receive_json()["type"] == "listening"
                with pytest.raises(WebSocketDisconnect) as exc:
                    ws1.receive_json()
                assert exc.value.code == 4001
