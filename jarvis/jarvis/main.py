"""HTTP API.

    GET  /health      no auth; says whether it is up, never anything personal
    POST /v1/turn     {text} -> {text, speak, scene, tools_used, latency_ms}
    GET  /v1/tools    the caller's tool list with tiers
    GET  /v1/history  the caller's own recent turns

``scene`` is always null until the scene protocol exists (learning-games.md §9).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .agent import Agent, LlmError
from .auth import Caller, require_caller
from .config import Settings, load_settings
from .ha import HomeAssistantReader
from .store import AuditLog, History
from .tools import ToolRegistry, home_assistant_tools

log = logging.getLogger("jarvis")

CallerDep = Annotated[Caller, Depends(require_caller)]


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TurnOut(BaseModel):
    text: str
    speak: bool
    scene: dict[str, Any] | None = None
    tools_used: list[str]
    latency_ms: int


def create_app(settings: Settings | None = None, agent: Agent | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        ha = None
        tools = ToolRegistry()
        if settings.ha_enabled:
            ha = HomeAssistantReader(
                settings.ha_url,
                settings.ha_token,
                settings.ha_domains,
                settings.ha_timeout_s,
            )
            tools = ToolRegistry(home_assistant_tools(ha))
        audit = AuditLog(settings.data_dir)
        app.state.settings = settings
        app.state.audit = audit
        app.state.history = History(settings.data_dir)
        app.state.agent = agent or Agent(settings, tools, audit)
        if not settings.device_tokens or not settings.owners:
            log.warning(
                "JARVIS_DEVICE_TOKENS or JARVIS_OWNERS empty: every call will be refused"
            )
        log.info(
            "jarvis up: model=%s ollama=%s ha=%s tools=%s",
            settings.model,
            settings.ollama_url,
            "on" if ha else "off",
            [t.name for t in app.state.agent.tools.list()],
        )
        yield
        await app.state.agent.aclose()
        if ha is not None:
            await ha.aclose()

    app = FastAPI(title="jarvis", lifespan=lifespan)

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        s: Settings = request.app.state.settings
        return {"ok": True, "model": s.model, "home_assistant": s.ha_enabled}

    @app.post("/v1/turn", response_model=TurnOut)
    async def turn(body: TurnIn, request: Request, caller: CallerDep) -> TurnOut:
        st = request.app.state
        s: Settings = st.settings
        history = st.history.recent(
            caller.identity, s.history_turns, within_s=s.history_window_s
        )
        try:
            result = await st.agent.turn(
                body.text,
                identity=caller.identity,
                device=caller.device,
                history=history,
            )
        except LlmError as exc:
            log.error("turn failed: %s", exc)
            st.audit.write(
                "turn_failed",
                device=caller.device,
                identity=caller.identity,
                error=str(exc),
            )
            raise HTTPException(502, "language model unavailable") from exc
        st.history.append(
            caller.identity,
            body.text,
            result.text,
            device=caller.device,
            tools=result.tools_used,
            speak=result.speak,
        )
        st.audit.write(
            "turn",
            device=caller.device,
            identity=caller.identity,
            tools=result.tools_used,
            speak=result.speak,
            latency_ms=result.latency_ms,
        )
        return TurnOut(
            text=result.text,
            speak=result.speak,
            tools_used=result.tools_used,
            latency_ms=result.latency_ms,
        )

    @app.get("/v1/tools")
    async def tools(request: Request, caller: CallerDep) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "tier": t.tier,
                "personal": t.personal,
                "description": t.description,
            }
            for t in request.app.state.agent.tools.list()
        ]

    @app.get("/v1/history")
    async def history(
        request: Request,
        caller: CallerDep,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
    ) -> list[dict[str, Any]]:
        return request.app.state.history.recent(caller.identity, limit)

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = load_settings()
    uvicorn.run(
        create_app(settings), host=settings.host, port=settings.port, log_level="info"
    )


if __name__ == "__main__":
    main()
