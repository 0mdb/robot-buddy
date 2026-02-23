"""Ollama-backed implementation of the planner LLM backend interface."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.llm.base import (
    LLMBusyError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    PlannerLLMBackend,
)
from app.llm.conversation import (
    ConversationHistory,
    ConversationResponse,
    generate_conversation_response,
)
from app.llm.prompts import SYSTEM_PROMPT, format_user_prompt
from app.llm.schemas import ModelPlan, WorldState

log = logging.getLogger(__name__)


class OllamaBackend(PlannerLLMBackend):
    """Thin async wrapper around Ollama chat completion endpoints."""

    def __init__(
        self,
        base_url: str = settings.ollama_url,
        model: str = settings.model_name,
        timeout_s: float = settings.plan_timeout_s,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = httpx.Timeout(timeout_s, connect=5.0)
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

        self._max_inflight = max(1, int(settings.llm_max_inflight))
        self._active_generations = 0
        self._generation_lock = asyncio.Lock()

    @property
    def backend_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
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

    async def model_available(self) -> bool:
        """Return True if the configured model exists in Ollama tags."""
        if self._client is None:
            return False
        try:
            resp = await self._client.get("/api/tags")
        except httpx.HTTPError:
            return False
        if resp.status_code != 200:
            return False
        try:
            data = resp.json()
        except ValueError:
            return False

        names = self._extract_model_names(data)
        return any(self._model_matches(name, self._model) for name in names)

    async def ensure_model_available(
        self,
        *,
        auto_pull: bool,
        pull_timeout_s: float,
    ) -> bool:
        """Ensure model is available; optionally auto-pull if missing."""
        if await self.model_available():
            return True

        if not auto_pull:
            log.warning(
                "Ollama model %s not present and AUTO_PULL_OLLAMA_MODEL is disabled",
                self._model,
            )
            return False

        log.warning("Ollama model %s not found; pulling automatically...", self._model)
        pulled = await self._pull_model(timeout_s=pull_timeout_s)
        if not pulled:
            return False
        ready = await self.model_available()
        if ready:
            log.info("Ollama model %s is now available", self._model)
        else:
            log.error(
                "Ollama pull reported success but model %s is still unavailable",
                self._model,
            )
        return ready

    async def generate_plan(self, state: WorldState) -> ModelPlan:
        """Generate a planner ModelPlan from world state."""
        assert self._client is not None
        await self._acquire_generation_slot()
        try:
            user_msg = format_user_prompt(state)
            body = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "format": ModelPlan.model_json_schema(),
                "keep_alive": settings.plan_keep_alive,
                "options": {
                    "temperature": settings.temperature,
                    "num_ctx": settings.num_ctx,
                },
            }

            try:
                resp = await self._client.post("/api/chat", json=body)
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("llm_timeout") from exc
            except httpx.ConnectError as exc:
                raise LLMUnavailableError("ollama_unreachable") from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"request failed: {exc}") from exc

            if (
                self._is_model_not_found(resp)
                and settings.auto_pull_ollama_model
                and await self.ensure_model_available(
                    auto_pull=True, pull_timeout_s=settings.ollama_pull_timeout_s
                )
            ):
                log.info("Retrying /api/chat after auto-pulling model %s", self._model)
                resp = await self._client.post("/api/chat", json=body)

            if resp.status_code != 200:
                raise LLMError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                raise LLMError("Empty content in Ollama response")

            try:
                plan = ModelPlan.model_validate_json(content)
            except Exception as exc:
                raise LLMError(f"Failed to parse plan: {exc}") from exc

            plan.actions = plan.actions[: settings.max_actions]
            log.info(
                "Plan generated: %d actions, ttl=%d ms",
                len(plan.actions),
                plan.ttl_ms,
            )
            return plan
        finally:
            await self._release_generation_slot()

    async def generate_conversation(
        self,
        history: ConversationHistory,
        user_text: str,
    ) -> ConversationResponse:
        """Generate one conversation response turn."""
        assert self._client is not None
        await self._acquire_generation_slot()
        try:
            try:
                return await generate_conversation_response(
                    self._client, history, user_text
                )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("llm_timeout") from exc
            except httpx.ConnectError as exc:
                raise LLMUnavailableError("ollama_unreachable") from exc
        finally:
            await self._release_generation_slot()

    async def warm(self, timeout_s: float = 120.0) -> None:
        """Send a trivial request to load the model into GPU memory."""
        assert self._client is not None
        log.info("Warming model %s (timeout %gs) ...", self._model, timeout_s)
        saved = self._client.timeout
        self._client.timeout = httpx.Timeout(timeout_s, connect=10.0)
        try:
            dummy = WorldState(
                robot_id="warmup",
                seq=0,
                monotonic_ts_ms=0,
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

    def debug_snapshot(self) -> dict:
        return {
            "backend": self.backend_name,
            "model": self.model_name,
            "loaded": self._client is not None,
            "max_inflight": self._max_inflight,
            "active_generations": self._active_generations,
        }

    async def _acquire_generation_slot(self) -> None:
        async with self._generation_lock:
            if self._active_generations >= self._max_inflight:
                raise LLMBusyError("llm_busy")
            self._active_generations += 1

    async def _release_generation_slot(self) -> None:
        async with self._generation_lock:
            if self._active_generations > 0:
                self._active_generations -= 1

    async def _pull_model(self, *, timeout_s: float) -> bool:
        assert self._client is not None
        payloads = (
            {"model": self._model, "stream": False},
            {"name": self._model, "stream": False},
        )
        last_error = "unknown"
        timeout = httpx.Timeout(timeout_s, connect=10.0)

        for payload in payloads:
            try:
                resp = await self._client.post(
                    "/api/pull", json=payload, timeout=timeout
                )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue

            if resp.status_code == 200:
                return True

            detail = self._extract_error_text(resp)
            last_error = f"{resp.status_code}: {detail}"

        log.error("Failed to auto-pull Ollama model %s: %s", self._model, last_error)
        return False

    @staticmethod
    def _extract_model_names(data: object) -> set[str]:
        names: set[str] = set()
        if not isinstance(data, dict):
            return names
        models = data.get("models")
        if not isinstance(models, list):
            return names
        for item in models:
            if not isinstance(item, dict):
                continue
            for key in ("name", "model"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    names.add(val.strip())
        return names

    @staticmethod
    def _model_matches(candidate: str, requested: str) -> bool:
        if candidate == requested:
            return True
        if ":" not in requested and candidate == f"{requested}:latest":
            return True
        if ":" not in candidate and requested == f"{candidate}:latest":
            return True
        return False

    def _is_model_not_found(self, resp: httpx.Response) -> bool:
        if resp.status_code != 404:
            return False
        text = resp.text.lower()
        if "model" not in text or "not found" not in text:
            return False
        model_key = self._model.lower().split(":", 1)[0]
        return model_key in text

    @staticmethod
    def _extract_error_text(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, str) and err:
                    return err
                detail = data.get("detail")
                if isinstance(detail, str) and detail:
                    return detail
        except ValueError:
            pass
        text = resp.text.strip()
        return text[:200] if text else "unknown error"
