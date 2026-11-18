"""Learning-game progress per child (personality/learning.py; docs/learning-games.md §2).

Synthetic ids and names only; never a real child's data in tests.
"""

from __future__ import annotations

import stat
from datetime import datetime

from fastapi.testclient import TestClient

from supervisor.api.http_server import create_app
from supervisor.api.param_registry import create_default_registry
from supervisor.api.ws_hub import WsHub
from supervisor.personality import learning as L
from supervisor.personality import roster as household
from supervisor.tests.test_api import FakeTick, FakeWorkers

DAY = 86400.0
T0 = datetime(2026, 11, 2, 15, 0).timestamp()  # local afternoon, so days don't wrap


def _play(store, kid, age, seed, right, *, step="G2", day=0, skill="add_sub_facts"):
    """One round of 5 at ``step``: ``right`` correct, the rest wrong."""
    changes = []
    for q in range(5):
        changes += store.record(
            kid,
            age,
            {
                "key": f"{seed}:rocket_math:{q}",
                "q": q,
                "game": "rocket_math",
                "skill": skill,
                "step": step,
                "item": f"What is {q} plus 1?",
                "expected": str(q + 1),
                "said": "x",
                "verdict": "right" if q < right else "wrong",
            },  # fmt: skip
            now=T0 + day * DAY + q,
        )
    return changes


def test_defaults_from_age(tmp_path):
    s = L.LearningStore(tmp_path / "p.json")
    assert s.learner("kid_a", 7) == {
        "base": "G2", "ceiling": "G3", "steps": {}, "confident": []}  # fmt: skip
    assert s.learner("kid_b", 5)["ceiling"] == "G1"
    assert s.step("kid_a", "add_sub_facts", 7) == "G2"


def test_mastery_needs_three_good_games_on_three_days(tmp_path):
    s = L.LearningStore(tmp_path / "p.json")
    assert _play(s, "kid_a", 7, 1, 5, day=0) == []
    assert _play(s, "kid_a", 7, 2, 4, day=0) == []  # same day: still one day
    assert _play(s, "kid_a", 7, 3, 2, day=1) == []  # a poor game doesn't count
    assert _play(s, "kid_a", 7, 4, 4, day=1) == []
    assert _play(s, "kid_a", 7, 5, 5, day=2) == ["add_sub_facts: G2 -> G3 (mastered)"]
    lr = s.learner("kid_a", 7)
    assert lr["steps"] == {"add_sub_facts": "G3"} and lr["confident"] == [
        "add_sub_facts"
    ]
    # At the ceiling (G3): mastery is noted, no step past it.
    for d in (3, 4, 5):
        assert _play(s, "kid_a", 7, 10 + d, 5, step="G3", day=d) == []
    assert s.step("kid_a", "add_sub_facts", 7) == "G3"


def test_parent_ceiling_is_lock_one(tmp_path):
    s = L.LearningStore(tmp_path / "p.json")
    s.set_ceiling("kid_a", "G2")
    for d in range(3):
        assert _play(s, "kid_a", 7, d, 5, day=d) == []
    assert s.step("kid_a", "add_sub_facts", 7) == "G2"
    s.set_ceiling("kid_a", "K")  # below the current step: capped
    assert s.step("kid_a", "add_sub_facts", 7) == "K"


def test_step_down_after_two_poor_games_and_incomplete_rounds_ignored(tmp_path):
    s = L.LearningStore(tmp_path / "p.json")
    s.record("kid_a", 7, {"key": "9:rocket_math:0", "q": 0, "game": "rocket_math",
                          "skill": "add_sub_facts", "step": "G2",
                          "verdict": "wrong"}, now=T0)  # fmt: skip
    assert _play(s, "kid_a", 7, 1, 1) == []
    assert _play(s, "kid_a", 7, 2, 2) == ["add_sub_facts: G2 -> G1 (stepped down)"]


def test_same_item_replaced_not_double_counted(tmp_path):
    s = L.LearningStore(tmp_path / "p.json")
    rec = {"key": "5:rocket_math:0", "q": 0, "game": "rocket_math",
           "skill": "add_sub_facts", "step": "G2", "verdict": "wrong"}  # fmt: skip
    s.record("kid_a", 7, rec, now=T0)
    s.record("kid_a", 7, rec | {"verdict": "right"}, now=T0 + 1)
    tries = s._member("kid_a")["attempts"]
    assert len(tries) == 1 and tries[0]["verdict"] == "right"


def test_bad_records_and_unknown_speaker_ignored(tmp_path):
    s = L.LearningStore(tmp_path / "p.json")
    assert s.record("", 7, {"key": "1:x:0", "q": 0, "game": "x", "skill": "s",
                            "step": "G2", "verdict": "right"}) == []  # fmt: skip
    assert s.record("kid_a", 7, {"key": "1:x:0", "q": 0, "game": "x", "skill": "s",
                                 "step": "G9", "verdict": "right"}) == []  # fmt: skip
    assert s.record("kid_a", 7, {"verdict": "right"}) == []
    assert not (tmp_path / "p.json").exists()


def test_file_private_reset_and_forget(tmp_path):
    p = tmp_path / "household_learning" / "progress.json"
    s = L.LearningStore(p)
    s.set_ceiling("kid_a", "G3")
    _play(s, "kid_a", 7, 1, 5)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    # Another instance (the HTTP server's) sees the same data.
    assert L.LearningStore(p).summary("kid_a", 7)["skills"][0]["games"]
    s.reset("kid_a")
    assert s.summary("kid_a", 7)["skills"] == [] and s.ceiling("kid_a", 7) == "G3"
    s.forget("kid_a")
    assert s.ceiling("kid_a", 7) == "G3" and s._member("kid_a") is None


def test_forget_everyone_removes_progress(tmp_path):
    roster_path = tmp_path / "household.toml"
    household.save(roster_path, household.Roster(enabled=True))
    p = L.default_path(roster_path)
    s = L.LearningStore(p)
    _play(s, "kid_a", 7, 1, 5)
    household.forget_everyone(roster_path)
    assert not p.exists() and s.learner("kid_a", 7)["steps"] == {}


def test_learning_api(tmp_path):
    roster_path = tmp_path / "household.toml"
    r = household.add_member(
        household.Roster(enabled=True), name="Kid A", kind="kid", age=7
    )
    r = household.add_member(r, name="Grown Up", kind="adult", age=40)
    household.save(roster_path, r)
    kid = next(m for m in r.members if m.kind == "kid")
    adult = next(m for m in r.members if m.kind == "adult")
    app = create_app(
        FakeTick(), create_default_registry(), WsHub(), FakeWorkers(),
        household_path=roster_path,
    )  # fmt: skip
    c = TestClient(app)
    body = c.get("/api/learning").json()
    assert [k["member_id"] for k in body["children"]] == [kid.id]
    assert (
        body["children"][0]["ceiling"] == "G3"
        and body["children"][0]["ceiling_is_default"]
    )
    assert [g["id"] for g in body["grades"]] == ["K", "G1", "G2", "G3"]
    got = c.put(f"/api/learning/{kid.id}/ceiling", json={"ceiling": "G2"}).json()
    assert got["ceiling"] == "G2" and not got["ceiling_is_default"]
    assert (
        c.put(f"/api/learning/{kid.id}/ceiling", json={"ceiling": "G7"}).status_code
        == 400
    )
    assert (
        c.put(f"/api/learning/{adult.id}/ceiling", json={"ceiling": "G2"}).status_code
        == 404
    )
    assert c.put(f"/api/learning/{kid.id}/ceiling", json={"ceiling": None}).json()[
        "ceiling_is_default"
    ]
    assert c.delete(f"/api/learning/{kid.id}").status_code == 200


def test_tick_loop_files_progress_only_under_a_recognised_child(tmp_path):
    import time as _time
    from unittest.mock import AsyncMock, MagicMock

    from supervisor.core.tick_loop import TickLoop
    from supervisor.personality.learning import LearningStore

    store = LearningStore(tmp_path / "household_learning" / "progress.json")
    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    loop = TickLoop(reflex=None, face=None, workers=workers, learning=store)
    loop.world.household_kinds = {"kid_a": "kid", "dad": "adult"}
    loop._household_ages = {"kid_a": 7}

    def see(*mids):
        loop.world.faces_held = [{"member_id": m, "range_mm": 800} for m in mids]
        loop.world.faces_seen_mono_ms = _time.monotonic() * 1000.0

    rec = {"key": "9:rocket_math:0", "q": 0, "game": "rocket_math",
           "skill": "add_sub_facts", "step": "G2", "item": "What is 2 plus 2?",
           "expected": "4", "answer": "4", "verdict": "right"}  # fmt: skip
    see("dad")  # a grown-up: no progress
    loop._record_practice(rec)
    see("kid_a", "dad")  # two faces: speaker unknown
    loop._record_practice(rec)
    assert store.summary("kid_a", 7)["skills"] == []
    see("kid_a")
    loop._record_practice(rec)
    assert store.summary("kid_a", 7)["skills"][0]["skill"] == "add_sub_facts"
    profile: dict = {}
    loop._add_learner(profile)
    assert profile["learner"]["base"] == "G2" and profile["learner"]["ceiling"] == "G3"
    assert "answer" not in str(profile)  # no attempts in the profile
