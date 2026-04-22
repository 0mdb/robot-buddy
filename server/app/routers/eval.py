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

from app.eval.harness import build_tool_selection_prompt, parse_tool_selection
from app.llm.base import LLMBusyError, LLMError, LLMTimeoutError, LLMUnavailableError

log = logging.getLogger(__name__)

router = APIRouter()


class SelectToolRequest(BaseModel):
    user_text: str = Field(..., min_length=1, max_length=500)


@router.post("/eval/select_tool")
async def select_tool(body: SelectToolRequest, request: Request) -> JSONResponse:
    llm = request.app.state.llm
    system_prompt = build_tool_selection_prompt()

    # We go straight through the low-level _generate_text helper so the eval
    # uses the same generation primitive as /plan and /converse — but with
    # the tool-selection system prompt and no extra schema plumbing. The
    # backend is private; this is intentionally a developer-only endpoint.
    generate_text = getattr(llm, "_generate_text", None)
    apply_template = getattr(llm, "_apply_chat_template", None)
    if generate_text is None or apply_template is None:
        return JSONResponse(
            {
                "error": "backend_mismatch",
                "detail": "current backend lacks eval primitives",
            },
            status_code=501,
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.user_text},
    ]
    prompt = apply_template(messages)

    try:
        raw = await generate_text(
            prompt,
            request_tag="eval-select-tool",
            # Small, focused output — tool selection + args, not a whole reply.
            override_max_output_tokens=128,
            override_temperature=0.0,
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
