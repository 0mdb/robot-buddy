"""Async client for the external personality server API."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class PersonalityError(RuntimeError):
    """Raised when the personality server returns invalid or failed responses."""


@dataclass(slots=True)
class PersonalityPlan:
    actions: list[dict] = field(default_factory=list)
    ttl_ms: int = 0

    def to_dict(self) -> dict:
        return {"actions": self.actions, "ttl_ms": self.ttl_ms}


class PersonalityClient:
    """Minimal async wrapper around the personality server `/health` + `/plan`."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 2.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_s,
                transport=self._transport,
            )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        client = self._require_client()
        try:
            resp = await client.get("/health")
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    async def request_plan(self, world_state: dict) -> PersonalityPlan:
        client = self._require_client()
        try:
            resp = await client.post("/plan", json=world_state)
        except httpx.HTTPError as e:
            msg = str(e).strip() or e.__class__.__name__
            raise PersonalityError(f"request failed: {msg}") from e

        if resp.status_code != 200:
            detail = self._extract_error(resp)
            raise PersonalityError(f"/plan returned {resp.status_code}: {detail}")

        try:
            body = resp.json()
        except ValueError as e:
            raise PersonalityError("invalid JSON response from /plan") from e

        actions = body.get("actions")
        ttl_ms = body.get("ttl_ms", 0)

        if not isinstance(actions, list):
            raise PersonalityError("invalid /plan payload: missing actions list")

        clean_actions = [a for a in actions if isinstance(a, dict)]
        ttl_ms = ttl_ms if isinstance(ttl_ms, int) else 0
        return PersonalityPlan(actions=clean_actions, ttl_ms=ttl_ms)

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("personality client not started")
        return self._client

    @staticmethod
    def _extract_error(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict):
                for key in ("detail", "error"):
                    val = data.get(key)
                    if isinstance(val, str) and val:
                        return val
        except ValueError:
            pass
        text = resp.text.strip()
        return text[:160] if text else "unknown error"
