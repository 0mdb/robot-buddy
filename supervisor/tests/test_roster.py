"""Household roster (SIM-INTERACTION I3, stage 3).

Synthetic names only. Never a real household's names in tests (repo rule).
"""

from __future__ import annotations

import stat
import time

import pytest
from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.messages.types import PERSONALITY_LLM_PROFILE
from supervisor.personality import roster as hh
from supervisor.tests.test_api import FakeTick, FakeWorkers
from supervisor.tests.test_personality_worker import _collect_sends, _make_worker

from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub


# ── Rules ───────────────────────────────────────────────────────────


def _family() -> hh.Roster:
    r = hh.Roster(enabled=True)
    r = hh.add_member(r, name="Test Kid A", kind="kid", age=7)
    r = hh.add_member(r, name="Test Kid B", kind="kid", age=5)
    r = hh.add_member(r, name="Test Parent", kind="adult")
    return hh.add_member(r, name="Test Dog", kind="animal")


def test_youngest_kid_age_and_hint_carry_no_names():
    r = _family()
    assert r.youngest_kid_age() == 5
    hint = r.audience_hint()
    assert hint == {
        "present": [{"kind": "unknown", "confidence": 0.0, "sources": []}],
        "speaking": 0,
        "household": {"youngest_kid_age": 5},
    }
    assert "Test" not in str(hint)
    assert not any(m.id in str(hint) for m in r.members)


def test_disabled_or_childless_roster_gives_no_hint():
    r = _family()
    assert hh.Roster(enabled=False, members=r.members).audience_hint() is None
    adults = hh.add_member(hh.Roster(enabled=True), name="Test Parent", kind="adult")
    assert adults.audience_hint() is None


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"name": "", "kind": "kid", "age": 5}, "name is required"),
        ({"name": "x" * 41, "kind": "kid", "age": 5}, "longer than"),
        ({"name": "A\x07B", "kind": "kid", "age": 5}, "control characters"),
        ({"name": "A", "kind": "robot"}, "kind must be"),
        ({"name": "A", "kind": "kid"}, "age is required"),
        ({"name": "A", "kind": "kid", "age": 30}, "1-17"),
        ({"name": "A", "kind": "kid", "age": True}, "whole number"),
        ({"name": "A", "kind": "adult", "age": 9}, "18-120"),
        ({"name": "A", "kind": "animal", "age": 3}, "no age"),
    ],
)
def test_validation(kwargs, msg):
    with pytest.raises(hh.RosterError, match=msg):
        hh.add_member(hh.Roster(), **kwargs)


def test_member_cap():
    r = hh.Roster()
    for i in range(hh.MAX_MEMBERS):
        r = hh.add_member(r, name=f"P{i}", kind="adult")
    with pytest.raises(hh.RosterError, match="at most"):
        hh.add_member(r, name="one more", kind="adult")


def test_update_and_remove():
    r = _family()
    kid = r.members[1]
    r = hh.update_member(r, kid.id, {"age": 6})
    assert r.youngest_kid_age() == 6
    with pytest.raises(hh.RosterError, match="cannot change"):
        hh.update_member(r, kid.id, {"id": "x"})
    with pytest.raises(KeyError):
        hh.update_member(r, "nope", {"age": 6})
    r = hh.remove_member(r, kid.id)
    assert r.youngest_kid_age() == 7


# ── Storage ─────────────────────────────────────────────────────────


def test_round_trip_is_private_and_unicode_safe(tmp_path):
    p = tmp_path / "household.toml"
    r = hh.add_member(_family(), name='Zoë "Z" O\'Neil', kind="kid", age=4)
    hh.save(p, r)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert hh.load(p) == r


def test_missing_file_is_disabled_and_damaged_file_is_refused(tmp_path):
    p = tmp_path / "household.toml"
    assert hh.load(p) == hh.Roster()
    p.write_text("enabled = true\n[[member]]\nname = 'no id'\nkind = 'kid'\nage = 5\n")
    assert hh.load(p) == hh.Roster()  # fail closed: not used
    with pytest.raises(hh.RosterError, match="damaged"):
        hh.load_strict(p)


def test_forget_everyone_removes_sidecars(tmp_path):
    p = tmp_path / "household.toml"
    hh.save(p, _family())
    (tmp_path / "household_voice").mkdir()
    (tmp_path / "household_voice" / "kid.npy").write_bytes(b"x")
    (tmp_path / "personality_memory.json").write_text("{}")
    hh.forget_everyone(p)
    assert not p.exists() and not (tmp_path / "household_voice").exists()
    assert (tmp_path / "personality_memory.json").exists()  # memory has its own delete


def test_roster_file_rereads_on_change(tmp_path):
    p = tmp_path / "household.toml"
    rf = hh.RosterFile(p)
    assert rf.get() == hh.Roster()
    hh.save(p, _family())
    assert rf.get().youngest_kid_age() == 5
    time.sleep(0.01)
    hh.save(p, hh.Roster(enabled=False, members=_family().members))
    import os

    os.utime(
        p, (time.time() + 5, time.time() + 5)
    )  # mtime resolution on some filesystems
    assert rf.get().youngest_kid_age() is None
    p.unlink()
    assert rf.get() == hh.Roster()


# ── HTTP API ────────────────────────────────────────────────────────


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "household.toml"
    app = create_app(
        FakeTick(),
        create_default_registry(),
        WsHub(),
        FakeWorkers(),
        household_path=path,
    )
    return TestClient(app), path


def test_api_off_by_default_then_enrol_see_delete(api):
    c, path = api
    assert c.get("/api/household").json() == {"enabled": False, "members": []}
    assert not path.exists()

    r = c.post(
        "/api/household/members", json={"name": "Test Kid", "kind": "kid", "age": 6}
    )
    assert r.status_code == 200
    (m,) = r.json()["members"]
    assert r.json()["enabled"] is False  # enrolling does not switch it on
    assert (
        c.put("/api/household/enabled", json={"enabled": True}).json()["enabled"]
        is True
    )

    r = c.patch(f"/api/household/members/{m['id']}", json={"age": 7})
    assert r.json()["members"][0]["age"] == 7
    assert c.delete(f"/api/household/members/{m['id']}").json()["members"] == []
    assert c.delete(f"/api/household/members/{m['id']}").status_code == 404


def test_api_validation_and_forget_everyone(api):
    c, path = api
    r = c.post("/api/household/members", json={"name": "Test Kid", "kind": "kid"})
    assert r.status_code == 422 and "age is required" in r.json()["reason"]
    assert c.put("/api/household/enabled", json={"enabled": "yes"}).status_code == 422
    c.post("/api/household/members", json={"name": "Test Parent", "kind": "adult"})
    assert path.exists()
    assert c.delete("/api/household").json() == {"enabled": False, "members": []}
    assert not path.exists()


def test_api_refuses_to_overwrite_a_damaged_roster(api):
    c, path = api
    path.write_text("this is not toml [[[")
    assert c.get("/api/household").status_code == 409
    r = c.post(
        "/api/household/members", json={"name": "Test Kid", "kind": "kid", "age": 6}
    )
    assert r.status_code == 422 and "damaged" in r.json()["reason"]
    assert path.read_text() == "this is not toml [[["
    assert c.delete("/api/household").status_code == 200  # forgetting always works


# ── Personality worker → profile message ────────────────────────────


def test_worker_sends_only_the_youngest_age(tmp_path):
    w = _make_worker()
    w._roster = hh.RosterFile(tmp_path / "household.toml")
    sends = _collect_sends(w)

    w._emit_llm_profile()
    assert "audience" not in sends[-1][1]  # no roster: today's message, unchanged

    hh.save(tmp_path / "household.toml", _family())
    w._emit_llm_profile()
    t, payload = sends[-1]
    assert t == PERSONALITY_LLM_PROFILE
    assert payload["audience"]["household"] == {"youngest_kid_age": 5}
    assert "Test" not in str(payload)
