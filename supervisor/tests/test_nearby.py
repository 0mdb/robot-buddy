"""Governor layer 8: motion near people and animals (core/nearby.py)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.core import nearby
from supervisor.core.nearby import Member, limit
from supervisor.core.safety import apply_safety
from supervisor.core.state import DesiredTwist, Mode, RobotState, WorldState
from supervisor.tests.test_api import FakeTick, FakeWorkers


@pytest.fixture(autouse=True)
def _defaults():
    nearby.reset()
    yield
    nearby.reset()


def kid(range_mm: int, bearing: float = 0.0, conf: float = 1.0) -> Member:
    return Member("kid", range_mm, bearing, conf)


@pytest.mark.parametrize(
    "member,v,expect",
    [
        (kid(1400), 300, 120),  # inside 1.5 m of a child: 120 mm/s
        (kid(1600), 300, 300),  # outside: untouched
        (Member("adult", 900, 0.0), 300, 200),
        (Member("adult", 1100, 0.0), 300, 300),
        (Member("animal", 1400, 0.0), 300, 100),
        (Member("unknown", 1400, 0.0), 300, 120),  # unknown is a child
        (Member("adult", 900, 0.0, 0.3), 300, 120),  # unsure is a child
        (kid(1400), 80, 80),  # already slower than the cap: untouched
    ],
)
def test_caps_by_kind(member, v, expect):
    assert limit(v, [member])[0] == expect


def test_standoff_blocks_approach_but_not_retreat_or_passing():
    assert limit(150, [kid(700, 0.0)]) == (0, "nearby=kid@700mm"), (
        "ahead, inside 0.8 m: stop"
    )
    assert limit(-150, [kid(700, 0.0)])[0] == -120, (
        "backing away from it: allowed, capped"
    )
    assert limit(150, [kid(700, 120.0)])[0] == 120, (
        "off to the side: capped, not stopped"
    )
    assert limit(-150, [kid(700, 180.0)])[0] == 0, "reversing into a child behind: stop"


def test_the_most_restrictive_member_wins():
    v, why = limit(300, [Member("adult", 900, 0.0), Member("animal", 1400, 90.0)])
    assert (v, why) == (100, "nearby=animal@1400mm")


def test_tuning_cannot_cross_the_floor():
    nearby.set_tunable("kid_standoff_mm", 100)  # floor 500
    nearby.set_tunable("kid_cap_mm_s", 999)  # max 250
    assert nearby.current()["kid_standoff_mm"] == 500
    assert nearby.current()["kid_cap_mm_s"] == 250
    with pytest.raises(KeyError):
        nearby.set_tunable("kid_speed", 1)


def test_registry_exposes_the_floors():
    reg = create_default_registry()
    p = reg.get("nearby.kid_standoff_mm")
    assert p is not None and p.min == 500 and p.value == 800


def _world(members, age_ms: float = 0.0) -> WorldState:
    w = WorldState()
    w.audience = members
    w.audience_rx_mono_ms = time.monotonic() * 1000.0 - age_ms
    return w


def test_safety_applies_layer_8_and_records_the_reason():
    r = RobotState()
    r.mode = Mode.WANDER
    r.reflex_connected = True
    r.range_mm, r.range_status = 3000, 0
    out = apply_safety(DesiredTwist(300, 200), r, _world([kid(1200)]))
    assert out.v_mm_s == 120 and out.w_mrad_s == 200, (
        "only v is limited; turning stays free"
    )
    assert any(c.reason.startswith("nearby=kid") for c in r.speed_caps)


def test_an_old_estimate_expires():
    r = RobotState()
    r.mode = Mode.WANDER
    r.reflex_connected = True
    r.range_mm, r.range_status = 3000, 0
    out = apply_safety(
        DesiredTwist(300, 0), r, _world([kid(1200)], age_ms=nearby.HOLD_MS + 100)
    )
    assert out.v_mm_s == 300, "a stale estimate is dropped, not held forever"


def test_api_validates_and_feeds_the_tick():
    calls = []

    class Tick(FakeTick):
        def set_audience(self, members):
            calls.append(members)
            self.world.audience = members
            self.world.audience_rx_mono_ms = time.monotonic() * 1000.0

    tick = Tick()
    c = TestClient(create_app(tick, create_default_registry(), WsHub(), FakeWorkers()))
    ok = c.post(
        "/api/audience",
        json={
            "members": [
                {"kind": "kid", "range_mm": 900, "bearing_deg": 10, "confidence": 1}
            ]
        },
    )
    assert ok.status_code == 200 and calls[-1][0] == Member("kid", 900, 10.0, 1.0)
    assert c.get("/api/audience").json()["members"][0]["kind"] == "kid"
    assert (
        c.post("/api/audience", json={"members": [{"kind": "kid"}]}).status_code == 422
    )
    assert c.post("/api/audience", json={"members": "kid"}).status_code == 422
    c.post(
        "/api/audience",
        json={"members": [{"kind": "robot", "range_mm": 1, "bearing_deg": 0}]},
    )
    assert calls[-1][0].kind == "unknown", (
        "an unknown kind is kept as unknown (a child)"
    )


def test_hud_reason_is_nearby():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path.home() / "vantage/supervisor"))
    w = pytest.importorskip("vantage_wire")
    from supervisor.core.state import SpeedCap
    from supervisor.devices.vantage_adapter import _limit_from_caps

    reason, scale = _limit_from_caps([SpeedCap(0.4, "nearby=kid@900mm")])
    assert reason == w.Limit.NEARBY and 0 < scale < 255
