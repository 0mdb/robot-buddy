"""Tests for OllamaClient model availability + auto-pull behavior."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import settings
from app.llm.client import OllamaClient, OllamaError
from app.llm.schemas import WorldState


def _world_state() -> WorldState:
    return WorldState(mode="IDLE", battery_mv=8000, range_mm=1000)


def test_model_available_true_when_present_in_tags():
    async def _run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": "qwen2.5:3b"}]},
                )
            return httpx.Response(404, json={"error": "not found"})

        client = OllamaClient(
            base_url="http://ollama.local",
            model="qwen2.5:3b",
            transport=httpx.MockTransport(handler),
        )
        await client.start()
        try:
            assert await client.model_available()
        finally:
            await client.close()

    asyncio.run(_run())


def test_generate_plan_autopulls_missing_model_and_retries(monkeypatch):
    async def _run() -> None:
        calls = {"chat": 0, "pull": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                calls["chat"] += 1
                if calls["chat"] == 1:
                    return httpx.Response(
                        404,
                        json={"error": "model 'qwen2.5:3b' not found"},
                    )
                return httpx.Response(
                    200,
                    json={
                        "message": {
                            "content": (
                                '{"actions":[{"action":"say","text":"hi"}],"ttl_ms":2000}'
                            )
                        }
                    },
                )
            if request.url.path == "/api/tags":
                if calls["pull"] == 0:
                    return httpx.Response(200, json={"models": []})
                return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})
            if request.url.path == "/api/pull":
                calls["pull"] += 1
                return httpx.Response(200, json={"status": "success"})
            return httpx.Response(404, json={"error": "unknown route"})

        monkeypatch.setattr(settings, "auto_pull_ollama_model", True)
        monkeypatch.setattr(settings, "ollama_pull_timeout_s", 30.0)

        client = OllamaClient(
            base_url="http://ollama.local",
            model="qwen2.5:3b",
            transport=httpx.MockTransport(handler),
        )
        await client.start()
        try:
            plan = await client.generate_plan(_world_state())
            assert len(plan.actions) == 1
            assert plan.actions[0].action == "say"
            assert calls["pull"] == 1
            assert calls["chat"] == 2
        finally:
            await client.close()

    asyncio.run(_run())


def test_generate_plan_missing_model_errors_when_autopull_disabled(monkeypatch):
    async def _run() -> None:
        calls = {"pull": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                return httpx.Response(
                    404,
                    json={"error": "model 'qwen2.5:3b' not found"},
                )
            if request.url.path == "/api/pull":
                calls["pull"] += 1
                return httpx.Response(200, json={"status": "success"})
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": []})
            return httpx.Response(404, json={"error": "unknown route"})

        monkeypatch.setattr(settings, "auto_pull_ollama_model", False)

        client = OllamaClient(
            base_url="http://ollama.local",
            model="qwen2.5:3b",
            transport=httpx.MockTransport(handler),
        )
        await client.start()
        try:
            with pytest.raises(OllamaError):
                await client.generate_plan(_world_state())
            assert calls["pull"] == 0
        finally:
            await client.close()

    asyncio.run(_run())
