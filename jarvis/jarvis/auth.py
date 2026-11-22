"""Caller auth (docs/screen-ui-and-admin.md §6.1).

Every call carries a per-device token (``Authorization: Bearer <token>``) and the
identity of the adult the client has unlocked or recognised (``X-Jarvis-User``).
Jarvis refuses a call that lacks either, or names someone not in JARVIS_OWNERS.

The identity is asserted by the client; the trust rests on the device token.
Buddy's supervisor only sends it after PIN + face ID (§3) or voice ID.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from .config import IDENTITY_RE, Settings


@dataclass(frozen=True)
class Caller:
    device: str
    identity: str


def _match_token(presented: str, tokens: dict[str, str]) -> str | None:
    """Constant-time check against every known token; returns the device name."""
    device = None
    for token, name in tokens.items():
        if hmac.compare_digest(presented.encode(), token.encode()):
            device = name
    return device


def check_caller(
    settings: Settings, authorization: str | None, user: str | None
) -> Caller:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "device token required")
    device = _match_token(token.strip(), settings.device_tokens)
    if device is None:
        raise HTTPException(401, "unknown device token")
    identity = (user or "").strip().lower()
    if not identity:
        raise HTTPException(403, "identity required")
    if not IDENTITY_RE.match(identity) or identity not in settings.owners:
        raise HTTPException(403, "identity not allowed")
    return Caller(device=device, identity=identity)


async def require_caller(
    request: Request,
    authorization: str | None = Header(default=None),
    x_jarvis_user: str | None = Header(default=None),
) -> Caller:
    state = request.app.state
    try:
        return check_caller(state.settings, authorization, x_jarvis_user)
    except HTTPException as exc:
        state.audit.write(
            "refused",
            device=None,
            identity=(x_jarvis_user or "")[:32] or None,
            reason=exc.detail,
            path=request.url.path,
        )
        raise
