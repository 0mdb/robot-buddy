"""Async client for the external planner server API."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class PlannerError(RuntimeError):
    """Raised when the planner server returns invalid or failed responses."""


@dataclass(slots=True)
class PlannerPlan:
    actions: list[dict] = field(default_factory=list)
    ttl_ms: int = 0
    plan_id: str = ""
    robot_id: str = ""
    seq: int = 0
    monotonic_ts_ms: int = 0
    server_monotonic_ts_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "actions": self.actions,
            "ttl_ms": self.ttl_ms,
            "plan_id": self.plan_id,
            "robot_id": self.robot_id,
            "seq": self.seq,
            "monotonic_ts_ms": self.monotonic_ts_ms,
            "server_monotonic_ts_ms": self.server_monotonic_ts_ms,
        }


class PlannerClient:
    """Minimal async wrapper around the planner server `/health` + `/plan`."""

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

    async def request_plan(self, world_state: dict) -> PlannerPlan:
        client = self._require_client()
        try:
            resp = await client.post("/plan", json=world_state)
        except httpx.HTTPError as e:
            msg = str(e).strip() or e.__class__.__name__
            raise PlannerError(f"request failed: {msg}") from e

        if resp.status_code != 200:
            detail = self._extract_error(resp)
            raise PlannerError(f"/plan returned {resp.status_code}: {detail}")

        try:
            body = resp.json()
        except ValueError as e:
            raise PlannerError("invalid JSON response from /plan") from e

        actions = body.get("actions")
        ttl_ms = body.get("ttl_ms", 0)

        if not isinstance(actions, list):
            raise PlannerError("invalid /plan payload: missing actions list")
        plan_id = body.get("plan_id")
        robot_id = body.get("robot_id")
        seq = body.get("seq")
        mono = body.get("monotonic_ts_ms")
        server_mono = body.get("server_monotonic_ts_ms")

        if not isinstance(plan_id, str) or not plan_id.strip():
            raise PlannerError("invalid /plan payload: missing plan_id")
        if not isinstance(robot_id, str) or not robot_id.strip():
            raise PlannerError("invalid /plan payload: missing robot_id")
        if not isinstance(seq, int):
            raise PlannerError("invalid /plan payload: missing seq")
        if not isinstance(mono, int):
            raise PlannerError("invalid /plan payload: missing monotonic_ts_ms")
        if not isinstance(server_mono, int):
            raise PlannerError("invalid /plan payload: missing server_monotonic_ts_ms")

        clean_actions = [a for a in actions if isinstance(a, dict)]
        ttl_ms = ttl_ms if isinstance(ttl_ms, int) else 0
        return PlannerPlan(
            actions=clean_actions,
            ttl_ms=ttl_ms,
            plan_id=plan_id.strip(),
            robot_id=robot_id.strip(),
            seq=seq,
            monotonic_ts_ms=mono,
            server_monotonic_ts_ms=server_mono,
        )

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("planner client not started")
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
