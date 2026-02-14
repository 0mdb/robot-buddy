"""Async client for the Ollama /api/chat endpoint."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.llm.prompts import SYSTEM_PROMPT, format_user_prompt
from app.llm.schemas import PlanResponse, WorldState

log = logging.getLogger(__name__)


class OllamaError(Exception):
    """Raised when the Ollama API returns an unexpected response."""


class OllamaClient:
    """Thin async wrapper around Ollama's chat completion API."""

    def __init__(
        self,
        base_url: str = settings.ollama_url,
        model: str = settings.model_name,
        timeout_s: float = settings.plan_timeout_s,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = httpx.Timeout(timeout_s, connect=5.0)
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable."""
        if self._client is None:
            return False
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def generate_plan(self, state: WorldState) -> PlanResponse:
        """Send world state to the LLM and return a validated plan.

        Raises:
            httpx.TimeoutException: if Ollama doesn't respond in time.
            httpx.ConnectError: if Ollama is unreachable.
            OllamaError: if the response is invalid or unparseable.
        """
        assert self._client is not None

        user_msg = format_user_prompt(state)

        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "format": PlanResponse.model_json_schema(),
            "options": {
                "temperature": settings.temperature,
                "num_ctx": settings.num_ctx,
            },
        }

        resp = await self._client.post("/api/chat", json=body)

        if resp.status_code != 200:
            raise OllamaError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        content = data.get("message", {}).get("content", "")

        if not content:
            raise OllamaError("Empty content in Ollama response")

        try:
            plan = PlanResponse.model_validate_json(content)
        except Exception as exc:
            raise OllamaError(f"Failed to parse plan: {exc}") from exc

        # Enforce max actions (defence in depth beyond schema max_length)
        plan.actions = plan.actions[: settings.max_actions]

        log.info(
            "Plan generated: %d actions, ttl=%d ms",
            len(plan.actions),
            plan.ttl_ms,
        )
        return plan

    async def warm(self, timeout_s: float = 120.0) -> None:
        """Send a trivial request to load the model into GPU memory."""
        assert self._client is not None
        log.info("Warming model %s (timeout %gs) ...", self._model, timeout_s)
        saved = self._client.timeout
        self._client.timeout = httpx.Timeout(timeout_s, connect=10.0)
        try:
            dummy = WorldState(
                mode="IDLE",
                battery_mv=8000,
                range_mm=1000,
                trigger="warmup",
            )
            await self.generate_plan(dummy)
            log.info("Model warm-up complete.")
        except Exception:
            log.warning("Model warm-up failed (server may still be loading).")
        finally:
            self._client.timeout = saved
