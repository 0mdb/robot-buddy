from __future__ import annotations

import json

import pytest

from jarvis.config import parse_device_tokens

from .conftest import AUTH, HA, OLLAMA, TOKEN, chat_reply, tool_call


def _audit(settings) -> list[dict]:
    path = settings.data_dir / "audit.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


# ── auth ────────────────────────────────────────────────────────────


def test_health_needs_no_auth_and_says_nothing_personal(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert set(r.json()) == {"ok", "model", "home_assistant"}


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        ({"X-Jarvis-User": "owner"}, 401),
        ({"Authorization": f"Bearer {TOKEN}"}, 403),
        (
            {
                "Authorization": "Bearer wrong-token-wrong-token",
                "X-Jarvis-User": "owner",
            },
            401,
        ),
        ({"Authorization": f"Bearer {TOKEN}", "X-Jarvis-User": "kid"}, 403),
        ({"Authorization": f"Bearer {TOKEN}", "X-Jarvis-User": "../owner"}, 403),
        ({"Authorization": f"Basic {TOKEN}", "X-Jarvis-User": "owner"}, 401),
    ],
)
def test_turn_refused_without_token_and_owner(client, settings, headers, status):
    r = client.post("/v1/turn", json={"text": "hi"}, headers=headers)
    assert r.status_code == status
    assert _audit(settings)[-1]["event"] == "refused"


def test_no_tokens_configured_refuses_everyone(tmp_path):
    from fastapi.testclient import TestClient

    from jarvis.main import create_app

    from .conftest import make_settings

    with TestClient(create_app(make_settings(tmp_path, device_tokens={}))) as c:
        assert c.post("/v1/turn", json={"text": "hi"}, headers=AUTH).status_code == 401


def test_device_tokens_parse_and_reject_short():
    assert parse_device_tokens("buddy=" + "a" * 16) == {"a" * 16: "buddy"}
    with pytest.raises(ValueError):
        parse_device_tokens("buddy=short")
    with pytest.raises(ValueError):
        parse_device_tokens("no-equals-sign-here-at-all")


# ── turns ───────────────────────────────────────────────────────────


def test_plain_turn_and_history(client, settings, httpx_mock):
    httpx_mock.add_response(url=f"{OLLAMA}/api/chat", json=chat_reply("Hello."))
    r = client.post("/v1/turn", json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["text"] == "Hello."
    assert r.json()["speak"] is True
    assert r.json()["scene"] is None

    h = client.get("/v1/history", headers=AUTH).json()
    assert [(x["user"], x["reply"]) for x in h] == [("hi", "Hello.")]

    # The next turn carries the previous one as context.
    httpx_mock.add_response(url=f"{OLLAMA}/api/chat", json=chat_reply("Again."))
    client.post("/v1/turn", json={"text": "again"}, headers=AUTH)
    sent = json.loads(httpx_mock.get_requests()[-1].content)
    roles = [m["role"] for m in sent["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert sent["model"] == "test-model"
    assert {t["function"]["name"] for t in sent["tools"]} == {"home_list", "home_state"}


def test_tool_loop_reads_home_assistant(client, settings, httpx_mock):
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat",
        json=chat_reply(tool_calls=[tool_call("home_state", entity_id="cover.garage")]),
    )
    httpx_mock.add_response(
        url=f"{HA}/api/states/cover.garage",
        json={
            "entity_id": "cover.garage",
            "state": "closed",
            "attributes": {"friendly_name": "Garage", "icon": "mdi:garage"},
        },
    )
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat", json=chat_reply("The garage is closed.")
    )

    r = client.post("/v1/turn", json={"text": "is the garage open?"}, headers=AUTH)
    assert r.json()["text"] == "The garage is closed."
    assert r.json()["tools_used"] == ["home_state"]

    second = json.loads(httpx_mock.get_requests()[-1].content)["messages"]
    tool_msg = second[-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_name"] == "home_state"
    assert json.loads(tool_msg["content"])["state"] == "closed"
    assert "icon" not in tool_msg["content"]

    calls = [a for a in _audit(settings) if a["event"] == "tool_call"]
    assert calls[-1]["tool"] == "home_state" and calls[-1]["ok"] is True
    assert calls[-1]["args"] == {"entity_id": "cover.garage"}


def test_unreadable_domain_never_reaches_home_assistant(client, settings, httpx_mock):
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat",
        json=chat_reply(
            tool_calls=[tool_call("home_state", entity_id="person.someone")]
        ),
    )
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat", json=chat_reply("I can't read that.")
    )
    r = client.post("/v1/turn", json={"text": "where is someone?"}, headers=AUTH)
    assert r.status_code == 200
    assert all(not str(req.url).startswith(HA) for req in httpx_mock.get_requests())
    calls = [a for a in _audit(settings) if a["event"] == "tool_call"]
    assert calls[-1]["ok"] is False


def test_home_assistant_is_only_ever_read(client, httpx_mock):
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat",
        json=chat_reply(tool_calls=[tool_call("home_list", domain="light")]),
    )
    httpx_mock.add_response(
        url=f"{HA}/api/states",
        json=[
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
            {"entity_id": "person.someone", "state": "home", "attributes": {}},
            {"entity_id": "lock.front", "state": "locked", "attributes": {}},
        ],
    )
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat", json=chat_reply("Kitchen light is on.")
    )
    client.post("/v1/turn", json={"text": "lights?"}, headers=AUTH)

    ha_reqs = [r for r in httpx_mock.get_requests() if str(r.url).startswith(HA)]
    assert ha_reqs and all(r.method == "GET" for r in ha_reqs)
    listed = json.loads(
        json.loads(httpx_mock.get_requests()[-1].content)["messages"][-1]["content"]
    )
    assert [e["entity_id"] for e in listed] == ["light.kitchen"]


def test_unknown_tool_and_runaway_loop_end_cleanly(client, settings, httpx_mock):
    loop = chat_reply(tool_calls=[tool_call("unlock_door")])
    for _ in range(settings.max_tool_rounds + 1):
        httpx_mock.add_response(url=f"{OLLAMA}/api/chat", json=loop)
    r = client.post("/v1/turn", json={"text": "unlock the door"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["text"]
    assert len(httpx_mock.get_requests()) == settings.max_tool_rounds + 1


def test_ollama_down_is_502_and_not_in_history(client, settings, httpx_mock):
    import httpx

    httpx_mock.add_exception(httpx.ConnectError("refused"), url=f"{OLLAMA}/api/chat")
    r = client.post("/v1/turn", json={"text": "hi"}, headers=AUTH)
    assert r.status_code == 502
    assert client.get("/v1/history", headers=AUTH).json() == []
    assert _audit(settings)[-1]["event"] == "turn_failed"


def test_personal_tool_makes_reply_screen_only(tmp_path, httpx_mock):
    from fastapi.testclient import TestClient

    from jarvis.agent import Agent
    from jarvis.main import create_app
    from jarvis.store import AuditLog
    from jarvis.tools import Tool, ToolRegistry

    from .conftest import make_settings

    async def balance(_args):
        return {"balance": 1}

    s = make_settings(tmp_path)
    tools = ToolRegistry(
        [Tool("balance", "account balance", {"type": "object"}, balance, personal=True)]
    )
    agent = Agent(s, tools, AuditLog(tmp_path))
    httpx_mock.add_response(
        url=f"{OLLAMA}/api/chat", json=chat_reply(tool_calls=[tool_call("balance")])
    )
    httpx_mock.add_response(url=f"{OLLAMA}/api/chat", json=chat_reply("One dollar."))
    with TestClient(create_app(s, agent=agent)) as c:
        r = c.post("/v1/turn", json={"text": "balance?"}, headers=AUTH)
    assert r.json()["speak"] is False


def test_data_files_are_private(client, settings, httpx_mock):
    httpx_mock.add_response(url=f"{OLLAMA}/api/chat", json=chat_reply("ok"))
    client.post("/v1/turn", json={"text": "hi"}, headers=AUTH)
    for p in (
        settings.data_dir / "audit.jsonl",
        settings.data_dir / "history" / "owner.jsonl",
    ):
        assert p.stat().st_mode & 0o077 == 0
