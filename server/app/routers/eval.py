"""POST /eval/select_tool — run the tool-selection prompt once.

Thin wrapper used by the BFCL-style eval CLI (`python -m app.eval`). The
endpoint takes a single user utterance, runs it through the live vLLM
engine with the tool-selection system prompt, and returns the raw model
response + parsed {tool, args}. Scoring happens client-side in the CLI.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.eval.harness import (
    TOOL_SELECTION_JSON_SCHEMA,
    build_tool_selection_prompt,
    parse_tool_selection,
)
from app.llm.base import LLMBusyError, LLMError, LLMTimeoutError, LLMUnavailableError

log = logging.getLogger(__name__)

router = APIRouter()


class SelectToolRequest(BaseModel):
    user_text: str = Field(..., min_length=1, max_length=500)


@router.post("/eval/select_tool")
async def select_tool(body: SelectToolRequest, request: Request) -> JSONResponse:
    llm = request.app.state.llm
    system_prompt = build_tool_selection_prompt()

    # Prefer the backend's generate_json_once (vLLM path) — it applies the
    # tool-selection schema via structured outputs so the model cannot emit
    # non-JSON prose (which was one of the eval gate's failure modes before
    # the vLLM 0.19 structured-outputs upgrade).
    generate_json_once = getattr(llm, "generate_json_once", None)
    if generate_json_once is None:
        return JSONResponse(
            {
                "error": "backend_mismatch",
                "detail": "current backend lacks eval primitives",
            },
            status_code=501,
        )

    try:
        raw = await generate_json_once(
            system_prompt,
            body.user_text,
            schema=TOOL_SELECTION_JSON_SCHEMA,
            max_tokens=128,
            temperature=0.0,
            request_tag="eval-select-tool",
        )
    except LLMBusyError:
        return JSONResponse({"error": "llm_busy"}, status_code=429)
    except LLMTimeoutError:
        return JSONResponse({"error": "llm_timeout"}, status_code=504)
    except LLMUnavailableError:
        return JSONResponse({"error": "llm_unavailable"}, status_code=503)
    except LLMError as exc:
        return JSONResponse({"error": "llm_error", "detail": str(exc)}, status_code=500)

    parsed = parse_tool_selection(raw)
    return JSONResponse({"raw": raw, "parsed": parsed})
