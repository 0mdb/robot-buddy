"""Tests for PlannerClient."""

from __future__ import annotations

import asyncio

import httpx

from supervisor.devices.planner_client import PlannerClient, PlannerError


def test_health_check_ok() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    async def run() -> None:
        client = PlannerClient("http://planner.local", transport=httpx.MockTransport(handler))
        await client.start()
        assert await client.health_check() is True
        await client.stop()

    asyncio.run(run())


def test_health_check_handles_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async def run() -> None:
        client = PlannerClient("http://planner.local", transport=httpx.MockTransport(handler))
        await client.start()
        assert await client.health_check() is False
        await client.stop()

    asyncio.run(run())


def test_request_plan_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/plan"
        body = request.read().decode("utf-8")
        assert '"mode":"IDLE"' in body
        return httpx.Response(
            200,
            json={
                "actions": [{"action": "emote", "name": "happy", "intensity": 0.8}],
                "ttl_ms": 1500,
                "plan_id": "p1",
                "robot_id": "robot-1",
                "seq": 7,
                "monotonic_ts_ms": 1234,
                "server_monotonic_ts_ms": 1240,
            },
        )

    async def run() -> None:
        client = PlannerClient("http://planner.local", transport=httpx.MockTransport(handler))
        await client.start()
        plan = await client.request_plan({"mode": "IDLE"})
        await client.stop()

        assert len(plan.actions) == 1
        assert plan.actions[0]["action"] == "emote"
        assert plan.ttl_ms == 1500
        assert plan.plan_id == "p1"
        assert plan.robot_id == "robot-1"
        assert plan.seq == 7

    asyncio.run(run())


def test_request_plan_raises_on_http_error_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "llm_error"})

    async def run() -> None:
        client = PlannerClient("http://planner.local", transport=httpx.MockTransport(handler))
        await client.start()
        try:
            await client.request_plan({"mode": "IDLE"})
        except PlannerError as e:
            assert "/plan returned 502" in str(e)
        else:
            raise AssertionError("expected PlannerError")
        finally:
            await client.stop()

    asyncio.run(run())


def test_request_plan_raises_on_bad_payload() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ttl_ms": 2000})

    async def run() -> None:
        client = PlannerClient("http://planner.local", transport=httpx.MockTransport(handler))
        await client.start()
        try:
            await client.request_plan({"mode": "IDLE"})
        except PlannerError as e:
            assert "actions list" in str(e)
        else:
            raise AssertionError("expected PlannerError")
        finally:
            await client.stop()

    asyncio.run(run())


def test_request_plan_raises_when_metadata_missing() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "actions": [{"action": "say", "text": "hello"}],
                "ttl_ms": 2000,
            },
        )

    async def run() -> None:
        client = PlannerClient("http://planner.local", transport=httpx.MockTransport(handler))
        await client.start()
        try:
            await client.request_plan({"mode": "IDLE"})
        except PlannerError as e:
            assert "plan_id" in str(e)
        else:
            raise AssertionError("expected PlannerError")
        finally:
            await client.stop()

    asyncio.run(run())
