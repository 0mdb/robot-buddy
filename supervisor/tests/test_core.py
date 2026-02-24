"""Tests for core modules: safety, state machine, event bus, scheduler, behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.core.action_scheduler import (
    ActionScheduler,
    PlanValidator,
)
from supervisor.core.behavior_engine import BehaviorEngine
from supervisor.core.event_bus import PlannerEventBus
from supervisor.core.event_router import EventRouter
from supervisor.core.safety import apply_safety
from supervisor.core.skill_executor import SkillExecutor
from supervisor.core.state import (
    DesiredTwist,
    Mode,
    RobotState,
    WorldState,
)
from supervisor.core.state_machine import SupervisorSM
from supervisor.devices.protocol import Fault, RangeStatus
from supervisor.messages.envelope import Envelope


# ── State Machine ────────────────────────────────────────────────


class TestStateMachine:
    def test_boot_to_idle(self):
        sm = SupervisorSM()
        mode = sm.update(reflex_connected=True, fault_flags=0)
        assert mode == Mode.IDLE

    def test_stays_boot_without_reflex(self):
        sm = SupervisorSM()
        mode = sm.update(reflex_connected=False, fault_flags=0)
        assert mode == Mode.BOOT

    def test_idle_to_wander(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        ok, msg = sm.request_mode(Mode.WANDER, True, 0)
        assert ok
        assert sm._mode == Mode.WANDER

    def test_fault_triggers_error(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        mode = sm.update(reflex_connected=True, fault_flags=Fault.ESTOP)
        assert mode == Mode.ERROR

    def test_clear_error(self):
        sm = SupervisorSM()
        sm.update(True, 0)
        sm.update(True, Fault.ESTOP)
        ok, msg = sm.clear_error(True, 0)
        assert ok


# ── Safety Policies ──────────────────────────────────────────────


class TestSafety:
    def test_mode_gate(self):
        r = RobotState(mode=Mode.IDLE, reflex_connected=True)
        w = WorldState()
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 0
        assert result.w_mrad_s == 0

    def test_passthrough_in_teleop(self):
        r = RobotState(
            mode=Mode.TELEOP,
            reflex_connected=True,
            range_status=RangeStatus.OK,
            range_mm=2000,
        )
        w = WorldState()
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 100
        assert result.w_mrad_s == 200

    def test_fault_gate(self):
        r = RobotState(mode=Mode.TELEOP, reflex_connected=True, fault_flags=Fault.ESTOP)
        w = WorldState()
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 0

    def test_range_close_cap(self):
        r = RobotState(
            mode=Mode.TELEOP,
            reflex_connected=True,
            range_status=RangeStatus.OK,
            range_mm=250,
        )
        w = WorldState()
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 25  # 25% of 100

    def test_vision_stale_cap(self):
        r = RobotState(
            mode=Mode.TELEOP,
            reflex_connected=True,
            range_status=RangeStatus.OK,
            range_mm=2000,
        )
        w = WorldState(clear_confidence=0.9, vision_rx_mono_ms=1.0)
        # vision_age_ms will be huge since rx_mono_ms is near zero
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 50  # 50% vision stale cap


# ── Event Bus ────────────────────────────────────────────────────


class TestEventBus:
    def test_mode_change_event(self):
        bus = PlannerEventBus()
        r1 = RobotState(mode=Mode.BOOT, tick_mono_ms=100.0)
        w = WorldState()
        bus.ingest(r1, w)

        r2 = RobotState(mode=Mode.IDLE, tick_mono_ms=200.0)
        bus.ingest(r2, w)

        events = bus.latest()
        assert any(e.type == "mode.changed" for e in events)

    def test_fault_raised_event(self):
        bus = PlannerEventBus()
        r1 = RobotState(tick_mono_ms=100.0)
        w = WorldState()
        bus.ingest(r1, w)

        r2 = RobotState(fault_flags=Fault.ESTOP, tick_mono_ms=200.0)
        bus.ingest(r2, w)

        events = bus.latest()
        assert any(e.type == "fault.raised" for e in events)

    def test_obstacle_hysteresis(self):
        bus = PlannerEventBus()
        w = WorldState()

        # Close: range < 450
        bus.ingest(
            RobotState(range_status=RangeStatus.OK, range_mm=400, tick_mono_ms=100), w
        )
        events = bus.latest()
        assert any(e.type == "safety.obstacle_close" for e in events)

        # Still close at 500 (not cleared — needs > 650)
        bus.ingest(
            RobotState(range_status=RangeStatus.OK, range_mm=500, tick_mono_ms=200), w
        )
        events = bus.latest()
        assert not any(e.type == "safety.obstacle_cleared" for e in events)

        # Cleared at 700
        bus.ingest(
            RobotState(range_status=RangeStatus.OK, range_mm=700, tick_mono_ms=300), w
        )
        events = bus.latest()
        assert any(e.type == "safety.obstacle_cleared" for e in events)


# ── Action Scheduler ─────────────────────────────────────────────


class TestActionScheduler:
    def test_schedule_and_pop(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan = v.validate([{"action": "say", "text": "Hello"}], ttl_ms=2000)
        s.schedule_plan(plan, now_mono_ms=1000, issued_mono_ms=1000)
        due = s.pop_due_actions(now_mono_ms=1000, face_locked=False)
        assert len(due) == 1
        assert due[0]["text"] == "Hello"

    def test_skill_updates_immediately(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan = v.validate(
            [{"action": "skill", "name": "investigate_ball"}], ttl_ms=2000
        )
        s.schedule_plan(plan, now_mono_ms=1000, issued_mono_ms=1000)
        assert s.active_skill == "investigate_ball"
        # Skills are not queued
        due = s.pop_due_actions(now_mono_ms=1000, face_locked=False)
        assert len(due) == 0

    def test_ttl_expiry(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan = v.validate([{"action": "say", "text": "Hello"}], ttl_ms=500)
        s.schedule_plan(plan, now_mono_ms=1000, issued_mono_ms=1000)
        # Pop after TTL expires
        due = s.pop_due_actions(now_mono_ms=2000, face_locked=False)
        assert len(due) == 0

    def test_cooldown(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan1 = v.validate([{"action": "say", "text": "A"}], ttl_ms=5000)
        s.schedule_plan(plan1, now_mono_ms=1000, issued_mono_ms=1000)
        s.pop_due_actions(now_mono_ms=1000, face_locked=False)

        # Same type within cooldown (3s)
        plan2 = v.validate([{"action": "say", "text": "B"}], ttl_ms=5000)
        s.schedule_plan(plan2, now_mono_ms=2000, issued_mono_ms=2000)
        due = s.pop_due_actions(now_mono_ms=2000, face_locked=False)
        assert len(due) == 0  # dropped by cooldown


# ── Plan Validator ───────────────────────────────────────────────


class TestPlanValidator:
    def test_validates_good_actions(self):
        v = PlanValidator()
        plan = v.validate(
            [
                {"action": "say", "text": "Hi"},
                {"action": "emote", "name": "happy", "intensity": 0.8},
                {"action": "gesture", "name": "nod"},
                {"action": "skill", "name": "patrol_drift"},
            ],
            ttl_ms=2000,
        )
        assert len(plan.actions) == 4
        assert plan.dropped_actions == 0

    def test_drops_invalid(self):
        v = PlanValidator()
        plan = v.validate(
            [
                {"action": "say"},  # no text
                {"action": "unknown"},  # bad action type
                {"action": "skill", "name": "hax"},  # not in ALLOWED_SKILLS
            ],
            ttl_ms=2000,
        )
        assert len(plan.actions) == 0
        assert plan.dropped_actions == 3

    def test_clamps_ttl(self):
        v = PlanValidator()
        plan = v.validate([], ttl_ms=99999)
        assert plan.ttl_ms == 5000  # clamped to max


# ── Event Router ─────────────────────────────────────────────────


class TestEventRouter:
    def _make_router(self):
        w = WorldState()
        s = ActionScheduler()
        v = PlanValidator()
        return EventRouter(w, s, v), w, s

    async def test_vision_snapshot(self):
        router, world, _ = self._make_router()
        env = Envelope(
            type="vision.detection.snapshot",
            src="vision",
            seq=1,
            t_ns=0,
            payload={
                "clear_confidence": 0.8,
                "ball_confidence": 0.5,
                "ball_bearing_deg": -5.0,
                "fps": 30.0,
                "frame_seq": 42,
            },
        )
        await router.route("vision", env)
        assert world.clear_confidence == 0.8
        assert world.ball_confidence == 0.5
        assert world.vision_frame_seq == 42

    async def test_tts_started_finished(self):
        router, world, _ = self._make_router()

        await router.route(
            "tts",
            Envelope(
                type="tts.event.started",
                src="tts",
                seq=1,
                t_ns=0,
                payload={"ref_seq": 5, "text": "Hello"},
            ),
        )
        assert world.speaking

        await router.route(
            "tts",
            Envelope(
                type="tts.event.finished",
                src="tts",
                seq=2,
                t_ns=0,
                payload={"ref_seq": 5},
            ),
        )
        assert not world.speaking

    async def test_plan_dedup(self):
        router, world, sched = self._make_router()
        plan_env = Envelope(
            type="ai.plan.received",
            src="ai",
            seq=1,
            t_ns=0,
            payload={
                "plan_id": "abc123",
                "plan_seq": 1,
                "actions": [{"action": "say", "text": "Hi"}],
                "ttl_ms": 2000,
            },
        )
        await router.route("ai", plan_env)
        assert world.plan_dropped_duplicate == 0

        # Same plan_id again
        plan_env2 = Envelope(
            type="ai.plan.received",
            src="ai",
            seq=2,
            t_ns=0,
            payload={
                "plan_id": "abc123",
                "plan_seq": 2,
                "actions": [{"action": "say", "text": "Hi again"}],
                "ttl_ms": 2000,
            },
        )
        await router.route("ai", plan_env2)
        assert world.plan_dropped_duplicate == 1

    async def test_audio_link_state(self):
        router, world, _ = self._make_router()
        await router.route(
            "tts",
            Envelope(
                type="system.audio.link_up",
                src="tts",
                seq=1,
                t_ns=0,
                payload={"socket": "mic"},
            ),
        )
        assert world.mic_link_up
        assert not world.spk_link_up

        await router.route(
            "ai",
            Envelope(
                type="system.audio.link_up",
                src="ai",
                seq=1,
                t_ns=0,
                payload={"socket": "spk"},
            ),
        )
        assert world.both_audio_links_up


# ── Behavior Engine ──────────────────────────────────────────────


class TestBehaviorEngine:
    def test_teleop_passthrough(self):
        skill = SkillExecutor()
        be = BehaviorEngine(skill)
        be.set_teleop_twist(100, 200)
        r = RobotState(mode=Mode.TELEOP)
        w = WorldState()
        twist = be.step(r, w)
        assert twist.v_mm_s == 100
        assert twist.w_mrad_s == 200

    def test_idle_zero(self):
        skill = SkillExecutor()
        be = BehaviorEngine(skill)
        r = RobotState(mode=Mode.IDLE)
        w = WorldState()
        twist = be.step(r, w)
        assert twist.v_mm_s == 0
        assert twist.w_mrad_s == 0

    def test_wander_returns_nonzero(self):
        skill = SkillExecutor()
        be = BehaviorEngine(skill)
        r = RobotState(
            mode=Mode.WANDER,
            tick_mono_ms=1000.0,
            range_status=RangeStatus.OK,
            range_mm=2000,
        )
        w = WorldState(active_skill="patrol_drift")
        twist = be.step(r, w)
        # Patrol drift should produce some motion
        assert twist.v_mm_s != 0 or twist.w_mrad_s != 0


# ── Prosody routing (B5) ───────────────────────────────────────


class TestProsodyRouting:
    """_enqueue_say should forward world.personality_mood as TTS emotion."""

    def _make_tick_loop(self):
        from supervisor.core.tick_loop import TickLoop

        workers = MagicMock()
        workers.send_to = AsyncMock(return_value=True)
        loop = TickLoop(reflex=None, face=None, workers=workers)
        return loop

    @pytest.mark.asyncio
    async def test_default_mood_is_neutral(self):
        loop = self._make_tick_loop()
        await loop._enqueue_say("hello")
        loop._workers.send_to.assert_called_once()
        payload = loop._workers.send_to.call_args[0][2]
        assert payload["emotion"] == "neutral"

    @pytest.mark.asyncio
    async def test_forwards_personality_mood(self):
        loop = self._make_tick_loop()
        loop.world.personality_mood = "excited"
        await loop._enqueue_say("wow!")
        payload = loop._workers.send_to.call_args[0][2]
        assert payload["emotion"] == "excited"

    @pytest.mark.asyncio
    async def test_sad_mood_forwarded(self):
        loop = self._make_tick_loop()
        loop.world.personality_mood = "sad"
        await loop._enqueue_say("oh no")
        payload = loop._workers.send_to.call_args[0][2]
        assert payload["emotion"] == "sad"
