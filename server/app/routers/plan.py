"""POST /plan — generate a personality performance plan."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.llm.client import OllamaError
from app.llm.schemas import PlanResponse, WorldState

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/plan", response_model=PlanResponse)
async def create_plan(
    state: WorldState, request: Request
) -> PlanResponse | JSONResponse:
    """Accept a world-state snapshot and return a bounded performance plan."""
    client = request.app.state.ollama

    try:
        plan = await client.generate_plan(state)
    except httpx.TimeoutException:
        log.warning("Ollama timed out generating plan")
        return JSONResponse(
            {"error": "llm_timeout", "detail": "Model took too long to respond"},
            status_code=504,
        )
    except httpx.ConnectError:
        log.error("Cannot reach Ollama")
        return JSONResponse(
            {"error": "ollama_unreachable", "detail": "Cannot connect to Ollama"},
            status_code=502,
        )
    except OllamaError as exc:
        log.error("Ollama error: %s", exc)
        return JSONResponse(
            {"error": "llm_error", "detail": str(exc)},
            status_code=502,
        )

    return plan
