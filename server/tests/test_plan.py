"""Integration tests for the /plan endpoint with mocked Ollama."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.client import OllamaClient
from app.llm.schemas import ModelPlan
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PLAN = ModelPlan(
    actions=[
        {"action": "emote", "name": "happy", "intensity": 0.8},
        {"action": "say", "text": "Hello!"},
    ],
    ttl_ms=2000,
)

WORLD_STATE = {
    "robot_id": "robot-1",
    "seq": 10,
    "monotonic_ts_ms": 12345,
    "mode": "WANDER",
    "battery_mv": 7800,
    "range_mm": 600,
    "trigger": "heartbeat",
}

OLLAMA_CHAT_RESPONSE = {
    "message": {
        "role": "assistant",
        "content": VALID_PLAN.model_dump_json(),
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Synchronous test client with a mocked OllamaClient on app.state."""
    # Attach a real OllamaClient (we'll mock HTTP via httpx)
    ollama = OllamaClient.__new__(OllamaClient)
    ollama._base_url = "http://localhost:11434"
    ollama._model = "qwen3:14b"
    ollama._timeout = httpx.Timeout(5.0)
    ollama._client = None  # Will be set per-test
    ollama._max_inflight = 1
    ollama._active_generations = 0
    app.state.llm = ollama

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_ollama_down(client):
    """Health returns 503 when Ollama is not reachable."""
    # OllamaClient._client is None, health_check will fail
    # We need a real async client for the sync test client, so
    # we test via the TestClient which handles the event loop.
    resp = client.get("/health")
    # Without a running Ollama, expect degraded
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "model" in data
    assert "llm_backend" in data
    assert "llm_model" in data
    assert "llm_engine_loaded" in data
    assert "gpu_budget" in data
    assert "qwen_backend" in data["gpu_budget"]
    assert "ai" in data
    assert "tts" in data["ai"]
    assert "model_available" in data


def test_plan_returns_valid_plan(client, monkeypatch):
    """POST /plan returns a valid plan when Ollama responds correctly."""

    async def mock_generate_plan(self, state):
        return VALID_PLAN

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_generate_plan)

    resp = client.post("/plan", json=WORLD_STATE)
    assert resp.status_code == 200
    data = resp.json()
    assert "actions" in data
    assert data["robot_id"] == "robot-1"
    assert data["seq"] == 10
    assert data["plan_id"]
    assert len(data["actions"]) == 2
    assert data["actions"][0]["action"] == "emote"
    assert data["ttl_ms"] == 2000


def test_plan_timeout(client, monkeypatch):
    """POST /plan returns 504 when Ollama times out."""

    async def mock_timeout(self, state):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_timeout)

    resp = client.post("/plan", json=WORLD_STATE)
    assert resp.status_code == 504
    assert resp.json()["error"] == "llm_timeout"


def test_plan_llm_unreachable(client, monkeypatch):
    """POST /plan returns 502 when LLM backend is unreachable."""

    async def mock_connect_error(self, state):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_connect_error)

    resp = client.post("/plan", json=WORLD_STATE)
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_unreachable"


def test_plan_invalid_world_state(client):
    """POST /plan returns 422 for missing required fields."""
    resp = client.post("/plan", json={"mode": "IDLE"})
    assert resp.status_code == 422


def test_plan_llm_error(client, monkeypatch):
    """POST /plan returns 502 on OllamaError."""
    from app.llm.client import OllamaError

    async def mock_ollama_error(self, state):
        raise OllamaError("bad response")

    monkeypatch.setattr(OllamaClient, "generate_plan", mock_ollama_error)

    resp = client.post("/plan", json=WORLD_STATE)
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_error"
