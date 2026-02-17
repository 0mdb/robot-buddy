"""Personality server entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.llm.client import OllamaClient
from app.routers.converse import router as converse_router
from app.routers.plan import router as plan_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the Ollama client and warm the model."""
    client = OllamaClient()
    await client.start()
    app.state.ollama = client

    healthy = await client.health_check()
    if healthy:
        log.info("Ollama is reachable — warming model")
        await client.warm()
    else:
        log.warning("Ollama is not reachable at %s", settings.ollama_url)

    yield

    await client.close()


app = FastAPI(
    title="Robot Buddy Personality Server",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(plan_router)
app.include_router(converse_router)


@app.get("/health")
async def health():
    """Liveness / readiness check."""
    client: OllamaClient = app.state.ollama
    ollama_ok = await client.health_check()
    status = "ok" if ollama_ok else "degraded"
    return JSONResponse(
        {
            "status": status,
            "model": settings.model_name,
            "ollama": ollama_ok,
        },
        status_code=200 if ollama_ok else 503,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
