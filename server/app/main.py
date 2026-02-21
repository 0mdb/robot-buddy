"""Planner server entry point."""

from __future__ import annotations

import logging
import subprocess
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.admission import ConverseSessionRegistry, PlanAdmissionGate
from app.ai_runtime import debug_snapshot as ai_debug_snapshot, get_tts
from app.config import settings
from app.llm.base import PlannerLLMBackend
from app.llm.factory import create_llm_backend
from app.routers.converse import router as converse_router
from app.routers.plan import router as plan_router
from app.routers.tts import router as tts_router

log = logging.getLogger(__name__)


def _detect_free_vram_gb() -> float | None:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None

    for line in proc.stdout.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            return float(raw) / 1024.0
        except ValueError:
            continue
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop selected LLM backend + TTS runtime."""
    app.state.plan_gate = PlanAdmissionGate(settings.plan_max_inflight)
    app.state.converse_registry = ConverseSessionRegistry()
    app.state.performance_mode = bool(settings.performance_mode)
    app.state.resource_profile = (
        "performance" if settings.performance_mode else "conservative"
    )
    app.state.orpheus_enabled = False
    app.state.orpheus_vram_free_gb = None

    combined_gpu_budget = (
        settings.vllm_gpu_memory_utilization + settings.orpheus_gpu_memory_utilization
        if settings.llm_backend == "vllm"
        else settings.orpheus_gpu_memory_utilization
    )
    if combined_gpu_budget > settings.gpu_utilization_cap:
        raise ValueError(
            "Configured GPU budgets exceed cap: "
            f"{combined_gpu_budget:.2f} > {settings.gpu_utilization_cap:.2f}"
        )

    if settings.stt_device.lower() == "cuda" and settings.performance_mode:
        log.warning(
            "STT_DEVICE=cuda with PERFORMANCE_MODE=1 may increase GPU contention; "
            "recommended STT_DEVICE=cpu"
        )

    llm: PlannerLLMBackend = create_llm_backend()
    await llm.start()
    app.state.llm = llm

    healthy = await llm.health_check()
    model_available = True
    if healthy:
        if settings.llm_backend == "ollama":
            ensure = getattr(llm, "ensure_model_available", None)
            if callable(ensure):
                model_available = await ensure(
                    auto_pull=settings.auto_pull_ollama_model,
                    pull_timeout_s=settings.ollama_pull_timeout_s,
                )
            if not model_available:
                log.warning(
                    "Ollama is reachable but model %s is unavailable",
                    llm.model_name,
                )
        if settings.warmup_llm and model_available:
            log.info("%s backend reachable — warming model", llm.backend_name)
            await llm.warm()
        else:
            log.info("%s backend reachable — warm-up disabled", llm.backend_name)
    else:
        log.warning("%s backend not reachable at startup", llm.backend_name)

    # Orpheus warm-up is intentionally sequenced after planner LLM warm-up.
    tts = get_tts()
    if settings.performance_mode:
        free_vram_gb = _detect_free_vram_gb()
        app.state.orpheus_vram_free_gb = free_vram_gb
        if free_vram_gb is None:
            tts.set_orpheus_allowed(False, "unknown_free_vram")
            log.warning(
                "Performance mode requested but free VRAM is unknown; Orpheus disabled"
            )
        elif free_vram_gb < settings.orpheus_min_free_vram_gb:
            tts.set_orpheus_allowed(False, "low_free_vram")
            log.warning(
                "Performance mode requested but free VRAM %.2f GiB < %.2f GiB; Orpheus disabled",
                free_vram_gb,
                settings.orpheus_min_free_vram_gb,
            )
        else:
            tts.set_orpheus_allowed(True, "vram_budget_ok")
            await tts.warmup()
    else:
        tts.set_orpheus_allowed(False, "performance_mode_disabled")
    app.state.orpheus_enabled = bool(tts.orpheus_allowed)

    yield

    tts.close()
    await llm.close()


app = FastAPI(
    title="Robot Buddy Planner Server",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(plan_router)
app.include_router(converse_router)
app.include_router(tts_router)


@app.get("/health")
async def health():
    """Liveness / readiness check."""
    llm: PlannerLLMBackend = app.state.llm
    llm_ok = await llm.health_check()
    model_available = bool(llm_ok)
    if settings.llm_backend == "ollama" and llm_ok:
        model_available_fn = getattr(llm, "model_available", None)
        if callable(model_available_fn):
            model_available = await model_available_fn()
    status = "ok" if llm_ok else "degraded"
    plan_gate = getattr(app.state, "plan_gate", None)
    converse_registry = getattr(app.state, "converse_registry", None)
    llm_snapshot = llm.debug_snapshot()
    return JSONResponse(
        {
            "status": status,
            "model": llm.model_name,
            "llm_backend": llm.backend_name,
            "llm_model": llm.model_name,
            "llm_engine_loaded": bool(llm_snapshot.get("loaded", llm_ok)),
            "ollama": (llm.backend_name == "ollama" and llm_ok),
            "model_available": model_available,
            "auto_pull_ollama_model": settings.auto_pull_ollama_model,
            "resource_profile": getattr(app.state, "resource_profile", "conservative"),
            "performance_mode": bool(getattr(app.state, "performance_mode", False)),
            "orpheus_enabled": bool(getattr(app.state, "orpheus_enabled", False)),
            "orpheus_vram_free_gb": getattr(app.state, "orpheus_vram_free_gb", None),
            "gpu_budget": {
                "qwen_backend": llm.backend_name,
                "qwen_utilization": (
                    settings.vllm_gpu_memory_utilization
                    if llm.backend_name == "vllm"
                    else None
                ),
                "orpheus_utilization": settings.orpheus_gpu_memory_utilization,
                "combined_utilization": (
                    settings.orpheus_gpu_memory_utilization
                    + (
                        settings.vllm_gpu_memory_utilization
                        if llm.backend_name == "vllm"
                        else 0.0
                    )
                ),
                "cap": settings.gpu_utilization_cap,
            },
            "plan_admission": (
                plan_gate.snapshot()
                if plan_gate is not None
                else {
                    "max_inflight": settings.plan_max_inflight,
                    "inflight": 0,
                    "admitted": 0,
                    "rejected": 0,
                }
            ),
            "converse_sessions": (
                converse_registry.snapshot()
                if converse_registry is not None
                else {
                    "active_sessions": 0,
                    "registered": 0,
                    "preempted": 0,
                    "unregistered": 0,
                    "robots": [],
                }
            ),
            "ai": ai_debug_snapshot(),
            "llm": llm_snapshot,
        },
        status_code=200 if llm_ok else 503,
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
