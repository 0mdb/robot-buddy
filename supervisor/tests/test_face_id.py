"""Face recognition: gallery, identity tracker, enrollment, and where identities go.

Synthetic member ids only; no names anywhere (repo rule).
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.inputs.face_id import (
    DEFAULT_MODEL,
    MATCH_THRESHOLD,
    FaceEmbedder,
    FaceGallery,
    FaceIdTracker,
    gallery_path,
)
from supervisor.messages.types import VISION_FACE_ENROLL, VISION_FACE_FORGET
from supervisor.personality import roster as hh
from supervisor.tests.test_api import FakeTick, FakeWorkers


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(128).astype(np.float32)
    return v / np.linalg.norm(v)


def _near(v: np.ndarray, noise: float, seed: int) -> np.ndarray:
    w = v + noise * np.random.default_rng(seed).standard_normal(128).astype(np.float32)
    return w / np.linalg.norm(w)


# ── Gallery ──────────────────────────────────────────────────────


def test_gallery_round_trip_match_and_forget(tmp_path):
    g = FaceGallery(tmp_path / "household_faces" / "gallery.json")
    a, b = _unit(1), _unit(2)
    g.add("m_a", [a, _near(a, 0.1, 3)])
    g.add("m_b", [b])

    g2 = FaceGallery(g.path)
    g2.refresh()
    assert g2.counts() == {"m_a": 2, "m_b": 1}
    mid, sim = g2.match(_near(a, 0.2, 4))
    assert mid == "m_a" and sim >= MATCH_THRESHOLD
    mid, sim = g2.match(_unit(99))  # a stranger
    assert mid is None and sim < MATCH_THRESHOLD

    assert g2.forget("m_a") and not g2.forget("m_a")
    g.refresh()
    assert g.counts() == {"m_b": 1}


def test_gallery_keeps_newest_samples(tmp_path):
    g = FaceGallery(tmp_path / "g.json")
    g.add("m", [_unit(i) for i in range(30)])
    assert g.counts() == {"m": 20}


def test_gallery_missing_or_bad_file_is_empty(tmp_path):
    g = FaceGallery(tmp_path / "g.json")
    g.refresh()
    assert g.counts() == {}
    g.path.write_text("not json")
    g.refresh()
    assert g.counts() == {} and g.match(_unit(1))[0] is None


def test_gallery_lives_in_the_roster_sidecar(tmp_path):
    p = gallery_path(tmp_path / "household.toml")
    assert p == tmp_path / "household_faces" / "gallery.json"


def test_forget_everyone_removes_face_prints(tmp_path):
    roster = tmp_path / "household.toml"
    hh.save(roster, hh.add_member(hh.Roster(), name="Test Kid", kind="kid", age=6))
    FaceGallery(gallery_path(roster)).add("m", [_unit(1)])
    hh.forget_everyone(roster)
    assert not (tmp_path / "household_faces").exists()


# ── Tracker ──────────────────────────────────────────────────────


class FakeEmbedder:
    """Returns the embedding stored on the YuNet row's score slot index (row[15])."""

    available = True
    error = ""

    def __init__(self, table: dict[int, np.ndarray]):
        self.table = table
        self.calls = 0

    def embed(self, frame, row):
        self.calls += 1
        return self.table[int(row[15])]


def _pair(cx: float, who: int, score: float = 0.9, w: float = 0.2):
    face = {"cx": cx, "cy": 0.5, "w": w, "h": w, "score": score}
    row = np.zeros(16, np.float32)
    row[15] = who
    return face, row


FRAME = np.zeros((480, 640, 3), np.uint8)


def _tracker(tmp_path, table, id_hz=100.0):
    return FaceIdTracker(
        FakeEmbedder(table), FaceGallery(tmp_path / "g.json"), id_hz=id_hz
    )


def test_no_gallery_no_recognition(tmp_path):
    t = _tracker(tmp_path, {1: _unit(1)})
    (f,) = t.process([_pair(0.5, 1)], FRAME, 2.0, 1.0)
    assert f["member_id"] is None and t.embedder.calls == 0


def test_enroll_then_recognise(tmp_path):
    a = _unit(1)
    t = _tracker(tmp_path, {1: a, 2: _near(a, 0.15, 5)})
    t.start_enroll("m_a", 3, now=0.0)
    now = 0.0
    while t.enrolling:
        now += 0.3
        t.process([_pair(0.5, 1)], FRAME, 2.0, now)
    res = t.take_result()
    assert res == {"member_id": "m_a", "ok": True, "samples": 3, "error": ""}
    assert t.take_result() is None

    (f,) = t.process([_pair(0.5, 2)], FRAME, 2.0, now + 1.0)
    assert f["member_id"] == "m_a" and f["id_score"] >= MATCH_THRESHOLD


def test_enroll_needs_exactly_one_clear_face(tmp_path):
    t = _tracker(tmp_path, {1: _unit(1), 2: _unit(2)})
    t.start_enroll("m_a", 2, now=0.0)
    now = 0.0
    for _ in range(10):
        now += 0.3
        t.process([_pair(0.3, 1), _pair(0.7, 2)], FRAME, 2.0, now)  # two people
        t.process([_pair(0.5, 1, score=0.5)], FRAME, 2.0, now + 0.01)  # unclear
        t.process([_pair(0.5, 1, w=0.03)], FRAME, 2.0, now + 0.02)  # too far
    assert t.embedder.calls == 0
    t.process([], FRAME, 2.0, 100.0)  # past the timeout
    res = t.take_result()
    assert (
        res["ok"] is False
        and res["samples"] == 0
        and "single clear face" in res["error"]
    )


def test_identity_carries_between_recognitions(tmp_path):
    a = _unit(1)
    t = _tracker(tmp_path, {1: a}, id_hz=1.0)
    t.gallery.add("m_a", [a])
    t.process([_pair(0.50, 1)], FRAME, 2.0, 10.0)
    (f,) = t.process([_pair(0.52, 1)], FRAME, 2.0, 10.1)  # too soon to re-check
    assert f["member_id"] == "m_a" and t.embedder.calls == 1


def test_unidentified_face_is_checked_first(tmp_path):
    a, b = _unit(1), _unit(2)
    t = _tracker(tmp_path, {1: a, 2: b})
    t.gallery.add("m_a", [a])
    t.gallery.add("m_b", [b])
    t.process([_pair(0.2, 1)], FRAME, 2.0, 1.0)
    faces = t.process([_pair(0.2, 1), _pair(0.8, 2)], FRAME, 2.0, 2.0)
    assert [f["member_id"] for f in faces] == ["m_a", "m_b"]


def test_real_sface_same_face_matches_itself():
    emb = FaceEmbedder()
    if not emb.available:
        pytest.skip("SFace model not fetched (deploy/fetch_models.sh)")
    assert DEFAULT_MODEL.is_file()
    img = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    row = np.array(
        [200, 150, 120, 140, 230, 200, 290, 200, 260, 230, 235, 260, 285, 260, 0.9],
        np.float32,
    )
    e1, e2 = emb.embed(img, row), emb.embed(img, row)
    assert e1.shape == (128,) and float(e1 @ e2) == pytest.approx(1.0, abs=1e-4)


# ── Where identities go ──────────────────────────────────────────


def test_recognised_adult_gets_adult_limits_stranger_child():
    from supervisor.core.state import WorldState

    w = WorldState()
    w.household_kinds = {"m_adult": "adult"}
    w.faces_held = [
        {"cx": 0.4, "w": 0.2, "score": 0.9, "range_mm": 900, "member_id": "m_adult"},
        {"cx": 0.6, "w": 0.2, "score": 0.9, "range_mm": 900, "member_id": None},
    ]
    w.faces_seen_mono_ms = time.monotonic() * 1000.0
    kinds = sorted(m.policy_kind() for m in w.audience_now())
    assert kinds == ["adult", "kid"]


def test_person_identified_once_per_presence():
    from supervisor.core.event_bus import FACE_APPEAR_MS, FACE_LOST_MS, PlannerEventBus
    from supervisor.core.state import RobotState, WorldState

    bus, robot, world = PlannerEventBus(), RobotState(), WorldState()
    face = {"cx": 0.5, "w": 0.2, "range_mm": 900, "member_id": "m_a", "id_score": 0.6}

    def tick(t, faces):
        robot.tick_mono_ms = t
        world.faces = faces
        world.vision_rx_mono_ms = time.monotonic() * 1000.0
        bus.ingest(robot, world)

    tick(1000.0, [face])
    tick(1000.0 + FACE_APPEAR_MS, [face])
    tick(1100.0 + FACE_APPEAR_MS, [face])
    ids = [e for e in bus.latest(50) if e.type == "vision.person_identified"]
    assert len(ids) == 1 and ids[0].payload["member_id"] == "m_a"
    tick(2000.0 + FACE_APPEAR_MS + FACE_LOST_MS, [])  # gone
    tick(10_000.0, [face])
    tick(10_000.0 + FACE_APPEAR_MS, [face])
    ids = [e for e in bus.latest(50) if e.type == "vision.person_identified"]
    assert len(ids) == 2


# ── API ──────────────────────────────────────────────────────────


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "household.toml"
    tick, workers = FakeTick(), FakeWorkers()
    app = create_app(
        tick, create_default_registry(), WsHub(), workers, household_path=path
    )
    return TestClient(app), path, tick, workers


def test_enroll_unknown_member_is_404(api):
    c, *_ = api
    assert c.post("/api/household/members/nope/face", json={}).status_code == 404


def test_enroll_returns_the_worker_result(api):
    c, path, tick, workers = api
    r = c.post(
        "/api/household/members", json={"name": "Test Kid", "kind": "kid", "age": 6}
    )
    mid = r.json()["members"][0]["id"]

    orig = workers.send_to

    async def send_to(name, msg_type, payload=None):
        ok = await orig(name, msg_type, payload)
        if msg_type == VISION_FACE_ENROLL:  # the worker answers
            tick.world.face_enroll_result = {
                "member_id": mid,
                "ok": True,
                "samples": 8,
                "error": "",
            }
            tick.world.face_enroll_seq += 1
        return ok

    workers.send_to = send_to
    r = c.post(f"/api/household/members/{mid}/face", json={"samples": 8})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert (
        "vision",
        VISION_FACE_ENROLL,
        {"member_id": mid, "samples": 8},
    ) in workers._sent


def test_removing_a_member_forgets_their_face(api):
    c, path, tick, workers = api
    r = c.post(
        "/api/household/members", json={"name": "Test Kid", "kind": "kid", "age": 6}
    )
    mid = r.json()["members"][0]["id"]
    FaceGallery(gallery_path(path)).add(mid, [_unit(1)])
    assert c.get("/api/household/faces").json() == {"samples": {mid: 1}}
    c.delete(f"/api/household/members/{mid}")
    assert ("vision", VISION_FACE_FORGET, {"member_id": mid}) in workers._sent
