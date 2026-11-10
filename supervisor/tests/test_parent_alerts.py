"""Parent alerts: secrets and serious disclosures (operator decision 2026-11-10).

Synthetic phrases only; never a real child's words in tests.
"""

from __future__ import annotations

import asyncio
import json
import stat

import pytest
from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.messages.envelope import make_envelope
from supervisor.messages.types import (
    AI_CONVERSATION_ASSISTANT_TEXT,
    AI_CONVERSATION_TRANSCRIPTION,
)
from supervisor.personality import parent_alerts as pa
from supervisor.tests.test_api import FakeTick, FakeWorkers


def test_message_type_names_match_the_bus():
    assert pa.ParentAlerts.TRANSCRIPTION == AI_CONVERSATION_TRANSCRIPTION
    assert pa.ParentAlerts.ASSISTANT_TEXT == AI_CONVERSATION_ASSISTANT_TEXT


@pytest.mark.parametrize(
    "text,expected",
    [
        ("can you keep a secret", ["secret"]),
        ("promise you won't tell my mom and dad", ["secret"]),
        ("he said not to tell my mom", ["dont_tell"]),
        ("he said if I tell he'll do it more", ["dont_tell"]),
        ("a man at the park said he has puppies in his car", ["stranger"]),
        ("my friend in the game wants to meet up", ["stranger"]),
        ("my cousin touches me in a way I don't like", ["touch"]),
        ("I fell off the couch and my arm really hurts", ["hurt"]),
        ("a big kid on the bus pushes me every day", ["bullied"]),
    ],
)
def test_detects_secrets_and_disclosures(text, expected):
    assert pa.detect(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "why is the sky blue",
        "I'm sad today",  # ordinary sadness is not an alert (operator decision)
        "let's play hide and seek",
        "I'm a secret agent",
        "the fire truck was loud",
        "my teacher said I did great",
    ],
)
def test_quiet_on_ordinary_talk(text):
    assert pa.detect(text) == []


def _env(t, **payload):
    return make_envelope(t, src="ai", seq=0, payload=payload)


def _feed(alerts, child, reply, session="s1", turn=1):
    alerts.capture_envelope(
        _env(
            AI_CONVERSATION_TRANSCRIPTION, session_id=session, turn_id=turn, text=child
        )
    )
    alerts.capture_envelope(
        _env(
            AI_CONVERSATION_ASSISTANT_TEXT, session_id=session, turn_id=turn, text=reply
        )
    )


def test_alert_records_words_and_reply_privately(tmp_path):
    path = tmp_path / "parent_alerts.json"
    alerts = pa.ParentAlerts(path)
    _feed(
        alerts,
        "promise you won't tell my mom",
        "I can't promise that. Grown-ups need to know.",
    )
    _feed(alerts, "why is the sky blue", "Sunlight has every color.", turn=2)
    (a,) = alerts.store().alerts
    assert (
        a.categories == ["secret"] and a.child_text == "promise you won't tell my mom"
    )
    assert a.buddy_reply.startswith("I can't promise")
    assert not a.reviewed
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_disabled_inbox_records_nothing(tmp_path):
    path = tmp_path / "parent_alerts.json"
    store = pa.AlertStore.load(path)
    store.enabled = False
    store.save()
    alerts = pa.ParentAlerts(path)
    _feed(alerts, "can you keep a secret", "Grown-ups need to know.")
    assert alerts.store().alerts == []


def test_push_carries_category_and_time_never_words(tmp_path):
    sent: list[tuple[str, str]] = []

    async def push(title, message):
        sent.append((title, message))
        return True

    async def run():
        alerts = pa.ParentAlerts(tmp_path / "a.json", push=push)
        _feed(
            alerts,
            "my cousin touches me in a way I don't like",
            "Tell your mom or dad.",
        )
        _feed(
            alerts, "my cousin touches me again", "Tell your mom or dad.", turn=2
        )  # cooldown
        _feed(
            alerts, "can you keep a secret", "Grown-ups need to know.", turn=3
        )  # new category
        await asyncio.sleep(0)

    asyncio.run(run())
    assert len(sent) == 2
    assert "unwanted touching" in sent[0][1] and "cousin" not in sent[0][1]
    assert "keep a secret" in sent[1][1]
    assert all("Details are in Buddy's dashboard" in m for _, m in sent)


def test_push_failure_never_raises(tmp_path):
    async def push(title, message):
        raise RuntimeError("HA down")

    async def run():
        alerts = pa.ParentAlerts(tmp_path / "a.json", push=push)
        _feed(alerts, "can you keep a secret", "Grown-ups need to know.")
        await asyncio.sleep(0)
        return alerts.store().alerts

    # the task's exception is the push function's own; the tap and the inbox are unaffected
    assert len(asyncio.run(run())) == 1


def test_damaged_inbox_is_kept_aside(tmp_path):
    path = tmp_path / "parent_alerts.json"
    path.write_text("{not json")
    store = pa.AlertStore.load(path)
    assert store.alerts == [] and store.enabled
    assert list(tmp_path.glob("parent_alerts.json.damaged-*"))


def test_retention_cap(tmp_path):
    store = pa.AlertStore(tmp_path / "a.json")
    store.alerts = [
        pa.Alert(id=str(i), ts=1e12, categories=["secret"], child_text="x")
        for i in range(250)
    ]
    store.save()
    assert len(pa.AlertStore.load(tmp_path / "a.json").alerts) == pa.MAX_ALERTS


@pytest.mark.parametrize(
    "env,on",
    [
        ({}, False),
        ({"RB_HA_URL": "http://ha:8123", "RB_HA_TOKEN": "t"}, False),
        (
            {
                "RB_HA_URL": "http://ha:8123",
                "RB_HA_TOKEN": "t",
                "RB_HA_NOTIFY": "mobile_app_x",
            },
            True,
        ),
        (
            {
                "RB_HA_URL": "http://ha:8123",
                "RB_HA_TOKEN": "t",
                "RB_HA_NOTIFY": "notify.mobile_app_x",
            },
            True,
        ),
        (
            {
                "RB_HA_URL": "http://ha:8123",
                "RB_HA_TOKEN": "t",
                "RB_HA_NOTIFY": "../../api/x",
            },
            False,
        ),
    ],
)
def test_home_assistant_settings(env, on):
    assert (pa.home_assistant_push_from_env(env) is not None) is on


def test_api_inbox(tmp_path):
    alerts = pa.ParentAlerts(tmp_path / "parent_alerts.json")
    _feed(
        alerts,
        "a man at the park said come see his puppies",
        "Please don't go with him.",
    )
    app = create_app(
        FakeTick(),
        create_default_registry(),
        WsHub(),
        FakeWorkers(),
        parent_alerts=alerts,
    )
    c = TestClient(app)
    body = c.get("/api/parent-alerts").json()
    assert body["enabled"] and body["unreviewed"] == 1 and body["push"] is False
    (a,) = body["alerts"]
    assert "stranger" in a["summary"]
    assert (
        c.patch(f"/api/parent-alerts/{a['id']}", json={"reviewed": True}).json()[
            "unreviewed"
        ]
        == 0
    )
    assert (
        c.patch("/api/parent-alerts/nope", json={"reviewed": True}).status_code == 404
    )
    assert (
        c.put("/api/parent-alerts/enabled", json={"enabled": False}).json()["enabled"]
        is False
    )
    assert c.delete(f"/api/parent-alerts/{a['id']}").json()["alerts"] == []
    assert c.delete("/api/parent-alerts").status_code == 200
    raw = json.loads((tmp_path / "parent_alerts.json").read_text())
    assert raw["enabled"] is False and raw["alerts"] == []


@pytest.mark.asyncio
async def test_tick_loop_feeds_the_tap(tmp_path):
    """End to end inside the supervisor: worker events -> tick -> inbox."""
    from unittest.mock import AsyncMock, MagicMock

    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    alerts = pa.ParentAlerts(tmp_path / "parent_alerts.json")
    loop = TickLoop(reflex=None, face=None, workers=workers, parent_alerts=alerts)
    await loop.on_worker_event(
        "ai",
        _env(
            AI_CONVERSATION_TRANSCRIPTION,
            session_id="s",
            turn_id=3,
            text="can you keep a secret",
        ),
    )
    await loop.on_worker_event(
        "ai",
        _env(
            AI_CONVERSATION_ASSISTANT_TEXT,
            session_id="s",
            turn_id=3,
            text="Grown-ups need to know.",
        ),
    )
    await loop._tick()
    (a,) = alerts.store().alerts
    assert a.categories == ["secret"] and a.buddy_reply == "Grown-ups need to know."
