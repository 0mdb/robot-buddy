from __future__ import annotations

from supervisor.planner.scheduler import PlannerScheduler
from supervisor.planner.validator import PlannerValidator


def test_validator_clamps_and_filters_actions():
    validator = PlannerValidator()
    plan = validator.validate(
        actions=[
            {"action": "say", "text": "  hello  "},
            {"action": "emote", "name": "happy", "intensity": 3.2},
            {"action": "gesture", "name": " nod "},
            {"action": "skill", "name": "investigate_ball"},
            {"action": "skill", "name": "unsupported"},
            {"action": "unknown", "x": 1},
        ],
        ttl_ms=99999,
    )
    assert plan.ttl_ms == 5000
    assert len(plan.actions) == 4
    assert plan.actions[0]["text"] == "hello"
    assert plan.actions[1]["intensity"] == 1.0
    assert plan.dropped_actions == 2


def test_scheduler_drops_stale_and_applies_cooldowns():
    validator = PlannerValidator()
    sched = PlannerScheduler()
    valid = validator.validate(
        actions=[{"action": "say", "text": "hello"}],
        ttl_ms=1000,
    )
    sched.schedule_plan(valid, now_mono_ms=5000.0, issued_mono_ms=3000.0)
    assert sched.plan_dropped_stale == 1

    valid2 = validator.validate(
        actions=[{"action": "say", "text": "hello"}],
        ttl_ms=2000,
    )
    sched.schedule_plan(valid2, now_mono_ms=5000.0, issued_mono_ms=4500.0)
    first = sched.pop_due_actions(now_mono_ms=5000.0, face_locked=False)
    assert len(first) == 1

    sched.schedule_plan(valid2, now_mono_ms=5200.0, issued_mono_ms=5100.0)
    assert sched.plan_dropped_cooldown >= 1

