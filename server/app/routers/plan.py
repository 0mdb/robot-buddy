"""POST /plan — generate a planner performance plan."""

from __future__ import annotations

import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.llm.base import LLMBusyError, LLMError, LLMTimeoutError, LLMUnavailableError
from app.llm.schemas import ModelPlan, PlanResponse, WorldState

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/plan", response_model=PlanResponse)
async def create_plan(
    state: WorldState, request: Request
) -> PlanResponse | JSONResponse:
    """Accept a world-state snapshot and return a bounded performance plan."""
    llm = request.app.state.llm
    gate = getattr(request.app.state, "plan_gate", None)

    if gate is not None and not await gate.try_acquire():
        return JSONResponse(
            {
                "error": "planner_busy",
                "detail": "planner overloaded; retry shortly",
            },
            status_code=429,
            headers={"Retry-After": "1"},
        )

    try:
        plan: ModelPlan = await llm.generate_plan(state)
    except LLMBusyError:
        return JSONResponse(
            {"error": "planner_busy", "detail": "llm backend saturated; retry shortly"},
            status_code=429,
            headers={"Retry-After": "1"},
        )
    except LLMTimeoutError:
        log.warning("LLM timed out generating plan")
        return JSONResponse(
            {"error": "llm_timeout", "detail": "Model took too long to respond"},
            status_code=504,
        )
    except httpx.TimeoutException:
        log.warning("LLM timed out generating plan")
        return JSONResponse(
            {"error": "llm_timeout", "detail": "Model took too long to respond"},
            status_code=504,
        )
    except LLMUnavailableError:
        log.error("Cannot reach LLM backend")
        return JSONResponse(
            {"error": "llm_unreachable", "detail": "Cannot connect to LLM backend"},
            status_code=502,
        )
    except httpx.ConnectError:
        log.error("Cannot reach LLM backend")
        return JSONResponse(
            {"error": "llm_unreachable", "detail": "Cannot connect to LLM backend"},
            status_code=502,
        )
    except LLMError as exc:
        log.error("LLM error: %s", exc)
        return JSONResponse(
            {"error": "llm_error", "detail": str(exc)},
            status_code=502,
        )
    finally:
        if gate is not None:
            await gate.release()

    return PlanResponse(
        plan_id=uuid.uuid4().hex,
        robot_id=state.robot_id,
        seq=state.seq,
        monotonic_ts_ms=state.monotonic_ts_ms,
        server_monotonic_ts_ms=int(time.monotonic() * 1000),
        actions=plan.actions,
        ttl_ms=plan.ttl_ms,
    )
