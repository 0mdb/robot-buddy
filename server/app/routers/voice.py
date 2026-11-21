"""Voice ID admin: what voiceprints are held, and forgetting them (the robot calls these
when a parent removes a member or forgets everyone). Keys are roster member ids only."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.voice.service import get_voice_service

router = APIRouter(prefix="/voice")


@router.get("/prints")
async def list_prints() -> JSONResponse:
    svc = get_voice_service()
    if svc is None:
        return JSONResponse({"enabled": False, "members": {}})
    return JSONResponse(
        {
            "enabled": True,
            "voice_id": svc.config.voice_id,
            "capture": svc.config.capture,
            "match_score": svc.config.match_score,
            "match_margin": svc.config.match_margin,
            "members": svc.prints.summary(),
            "clips": len(svc.store.clips()),
        }
    )


@router.delete("/prints/{member_id}")
async def forget_member(member_id: str) -> JSONResponse:
    svc = get_voice_service()
    if svc is None:
        return JSONResponse({"ok": True, "enabled": False})
    return JSONResponse({"ok": True, **svc.forget(member_id)})


@router.delete("/prints")
async def forget_all() -> JSONResponse:
    svc = get_voice_service()
    if svc is not None:
        svc.forget_all()
    return JSONResponse({"ok": True})
