"""Tests for core modules: safety, state machine, event bus, scheduler, behavior."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.core.action_scheduler import (
    ActionScheduler,
    PlanValidator,
)
from supervisor.core.behavior_engine import BehaviorEngine
from supervisor.core.event_bus import PlannerEvent, PlannerEventBus
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
from supervisor.messages.types import TTS_CMD_CANCEL, TTS_CMD_SPEAK


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

    def test_error_auto_recovers_when_reflex_healthy(self):
        sm = SupervisorSM()
        sm.update(True, 0)
        # Reflex drops → ERROR
        mode = sm.update(reflex_connected=False, fault_flags=0)
        assert mode == Mode.ERROR
        # Reflex comes back, no faults → auto-clear to IDLE
        mode = sm.update(reflex_connected=True, fault_flags=0)
        assert mode == Mode.IDLE

    def test_error_persists_while_faults_active(self):
        sm = SupervisorSM()
        sm.update(True, 0)
        sm.update(True, Fault.ESTOP)
        # Reflex healthy but fault still latched → stay in ERROR
        mode = sm.update(reflex_connected=True, fault_flags=Fault.ESTOP)
        assert mode == Mode.ERROR

    def test_request_motion_rejected_when_power_critical(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        ok, reason = sm.request_mode(
            Mode.WANDER,
            reflex_connected=True,
            fault_flags=0,
            motion_blocked_by_power=True,
        )
        assert not ok
        assert "battery" in reason.lower()
        assert sm._mode == Mode.IDLE

    def test_request_idle_allowed_even_when_power_critical(self):
        # IDLE is the safe default; never refuse it.
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        sm.request_mode(Mode.WANDER, True, 0)
        ok, _ = sm.request_mode(
            Mode.IDLE,
            reflex_connected=True,
            fault_flags=0,
            motion_blocked_by_power=True,
        )
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

    def test_soc_critical_gate_zeros_motion(self):
        from supervisor.core.safety import configure_power_policy

        configure_power_policy(soc_critical_pct=10)
        r = RobotState(
            mode=Mode.TELEOP,
            reflex_connected=True,
            range_status=RangeStatus.OK,
            range_mm=2000,
        )
        r.power.soc_pct = 8
        w = WorldState()
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 0
        assert result.w_mrad_s == 0
        assert any("soc_critical" in cap.reason for cap in r.speed_caps)

    def test_soc_unknown_does_not_gate(self):
        # soc_pct = -1 means no fuel gauge; must not gate.
        from supervisor.core.safety import configure_power_policy

        configure_power_policy(soc_critical_pct=10)
        r = RobotState(
            mode=Mode.TELEOP,
            reflex_connected=True,
            range_status=RangeStatus.OK,
            range_mm=2000,
        )
        r.power.soc_pct = -1
        w = WorldState()
        result = apply_safety(DesiredTwist(100, 200), r, w)
        assert result.v_mm_s == 100
        assert result.w_mrad_s == 200


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

    def test_soc_warn_edge_fires_once(self):
        bus = PlannerEventBus(soc_warn_pct=25, soc_critical_pct=10)
        w = WorldState()

        r = RobotState(tick_mono_ms=100.0)
        r.power.soc_pct = 30
        bus.ingest(r, w)
        assert not any(e.type == "power.low_soc_raised" for e in bus.latest())

        r2 = RobotState(tick_mono_ms=200.0)
        r2.power.soc_pct = 22  # crosses warn threshold
        bus.ingest(r2, w)
        warn_events = [
            e
            for e in bus.latest()
            if e.type == "power.low_soc_raised" and e.payload["severity"] == "warn"
        ]
        assert len(warn_events) == 1

        # Hovering near threshold doesn't refire (hysteresis)
        r3 = RobotState(tick_mono_ms=300.0)
        r3.power.soc_pct = 20
        bus.ingest(r3, w)
        warn_events = [
            e
            for e in bus.latest()
            if e.type == "power.low_soc_raised" and e.payload["severity"] == "warn"
        ]
        assert len(warn_events) == 1

    def test_soc_critical_edge_fires_separately(self):
        bus = PlannerEventBus(soc_warn_pct=25, soc_critical_pct=10)
        w = WorldState()

        r = RobotState(tick_mono_ms=100.0)
        r.power.soc_pct = 22  # warn
        bus.ingest(r, w)
        r2 = RobotState(tick_mono_ms=200.0)
        r2.power.soc_pct = 8  # critical
        bus.ingest(r2, w)

        events = [e for e in bus.latest() if e.type == "power.low_soc_raised"]
        severities = [e.payload["severity"] for e in events]
        assert "warn" in severities
        assert "critical" in severities

    def test_soc_unknown_does_not_emit(self):
        bus = PlannerEventBus(soc_warn_pct=25, soc_critical_pct=10)
        w = WorldState()
        r = RobotState(tick_mono_ms=100.0)
        r.power.soc_pct = -1
        bus.ingest(r, w)
        assert not any(e.type == "power.low_soc_raised" for e in bus.latest())


# ── Action Scheduler ─────────────────────────────────────────────


class TestActionScheduler:
    def test_schedule_and_pop(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan = v.validate([{"action": "say", "text": "Hello"}], ttl_ms=2000)
        s.schedule_plan(plan, now_mono_ms=1000, issued_mono_ms=1000)
        due = s.pop_due_actions(now_mono_ms=1000, face_locked=False, hold_say=False)
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
        due = s.pop_due_actions(now_mono_ms=1000, face_locked=False, hold_say=False)
        assert len(due) == 0

    def test_ttl_expiry(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan = v.validate([{"action": "say", "text": "Hello"}], ttl_ms=500)
        s.schedule_plan(plan, now_mono_ms=1000, issued_mono_ms=1000)
        # Pop after TTL expires
        due = s.pop_due_actions(now_mono_ms=2000, face_locked=False, hold_say=False)
        assert len(due) == 0

    def test_cooldown(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan1 = v.validate([{"action": "say", "text": "A"}], ttl_ms=5000)
        s.schedule_plan(plan1, now_mono_ms=1000, issued_mono_ms=1000)
        s.pop_due_actions(now_mono_ms=1000, face_locked=False, hold_say=False)

        # Same type within cooldown (3s)
        plan2 = v.validate([{"action": "say", "text": "B"}], ttl_ms=5000)
        s.schedule_plan(plan2, now_mono_ms=2000, issued_mono_ms=2000)
        due = s.pop_due_actions(now_mono_ms=2000, face_locked=False, hold_say=False)
        assert len(due) == 0  # dropped by cooldown

    def test_hold_say_holds_planner_speech(self):
        s = ActionScheduler()
        v = PlanValidator()
        plan = v.validate(
            [
                {"action": "say", "text": "Hello"},
                {"action": "gesture", "name": "nod"},
            ],
            ttl_ms=2000,
        )
        s.schedule_plan(plan, now_mono_ms=1000, issued_mono_ms=1000)

        # During conversation, hold say actions (and continue dropping gestures when face is locked).
        due = s.pop_due_actions(now_mono_ms=1000, face_locked=True, hold_say=True)
        assert due == []

        # After conversation ends, the held say can run (gesture was dropped while locked).
        due2 = s.pop_due_actions(now_mono_ms=1000, face_locked=False, hold_say=False)
        assert len(due2) == 1
        assert due2[0]["action"] == "say"
        assert due2[0]["text"] == "Hello"


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

    async def test_ai_conversation_error_logged(self, caplog):
        router, _, _ = self._make_router()
        with caplog.at_level(logging.ERROR, logger="supervisor.core.event_router"):
            await router.route(
                "ai",
                Envelope(
                    type="ai.conversation.error",
                    src="ai",
                    seq=1,
                    t_ns=0,
                    payload={"error": "ws_connect_failed"},
                ),
            )

        assert any(
            r.levelno == logging.ERROR and "ws_connect_failed" in r.getMessage()
            for r in caplog.records
        )

    async def test_tts_event_error_logged_and_state_reset(self, caplog):
        router, world, _ = self._make_router()
        world.speaking = True
        world.current_energy = 123

        with caplog.at_level(logging.ERROR, logger="supervisor.core.event_router"):
            await router.route(
                "tts",
                Envelope(
                    type="tts.event.error",
                    src="tts",
                    seq=1,
                    t_ns=0,
                    payload={"error": "TTS HTTP 500"},
                ),
            )

        assert world.speaking is False
        assert world.current_energy == 0
        assert any(
            r.levelno == logging.ERROR and "TTS HTTP 500" in r.getMessage()
            for r in caplog.records
        )

    async def test_vision_lifecycle_error_logged(self, caplog):
        router, _, _ = self._make_router()
        with caplog.at_level(logging.ERROR, logger="supervisor.core.event_router"):
            await router.route(
                "vision",
                Envelope(
                    type="vision.lifecycle.error",
                    src="vision",
                    seq=1,
                    t_ns=0,
                    payload={"error": "camera disconnected"},
                ),
            )

        assert any(
            r.levelno == logging.ERROR and "camera disconnected" in r.getMessage()
            for r in caplog.records
        )

    async def test_unknown_lifecycle_error_logged_by_generic_handler(self, caplog):
        router, _, _ = self._make_router()
        with caplog.at_level(logging.ERROR, logger="supervisor.core.event_router"):
            await router.route(
                "mystery",
                Envelope(
                    type="mystery.lifecycle.error",
                    src="mystery",
                    seq=1,
                    t_ns=0,
                    payload={"error": "unexpected boom"},
                ),
            )

        assert any(
            r.levelno == logging.ERROR
            and "mystery.lifecycle.error" in r.getMessage()
            and "unexpected boom" in r.getMessage()
            for r in caplog.records
        )


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

    def test_teleop_twist_expires(self):
        """A client that stops sending must not leave the last twist latched."""
        skill = SkillExecutor()
        be = BehaviorEngine(skill, teleop_ttl_s=0.5)
        r = RobotState(mode=Mode.TELEOP)
        w = WorldState()

        be.set_teleop_twist(100, 200, now_s=1000.0)
        # Still fresh just inside the window.
        assert be.step(r, w, now_s=1000.4).v_mm_s == 100
        # Past it, the command is forgotten rather than held.
        stale = be.step(r, w, now_s=1000.6)
        assert stale.v_mm_s == 0
        assert stale.w_mrad_s == 0

    def test_teleop_recovers_after_expiry(self):
        """A fresh command after a stale gap is honoured immediately."""
        skill = SkillExecutor()
        be = BehaviorEngine(skill, teleop_ttl_s=0.5)
        r = RobotState(mode=Mode.TELEOP)
        w = WorldState()

        be.set_teleop_twist(100, 200, now_s=1000.0)
        assert be.step(r, w, now_s=1002.0).v_mm_s == 0
        be.set_teleop_twist(50, 60, now_s=1002.1)
        twist = be.step(r, w, now_s=1002.2)
        assert twist.v_mm_s == 50
        assert twist.w_mrad_s == 60

    def test_teleop_zero_before_any_command(self):
        """Entering TELEOP with no command yet must not move."""
        skill = SkillExecutor()
        be = BehaviorEngine(skill)
        twist = be.step(RobotState(mode=Mode.TELEOP), WorldState(), now_s=1000.0)
        assert twist.v_mm_s == 0
        assert twist.w_mrad_s == 0

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


# ── Conversation speech arbitration ──────────────────────────────


class TestConversationSpeechArbitration:
    def _make_tick_loop(self):
        from supervisor.core.tick_loop import TickLoop

        workers = MagicMock()
        workers.send_to = AsyncMock(return_value=True)
        loop = TickLoop(reflex=None, face=None, workers=workers)
        return loop

    @pytest.mark.asyncio
    async def test_speech_policy_suppressed_during_conversation(self):
        loop = self._make_tick_loop()
        loop.world.session_id = "sess-test"

        evt = PlannerEvent(
            "mode.changed",
            {"to": "WANDER"},
            1000.0,
        )
        await loop._emit_worker_actions(1000.0, [evt])

        speak_calls = [
            c
            for c in loop._workers.send_to.call_args_list
            if len(c.args) >= 2 and c.args[0] == "tts" and c.args[1] == TTS_CMD_SPEAK
        ]
        assert speak_calls == []

    @pytest.mark.asyncio
    async def test_start_conversation_preempts_planner_speech(self):
        loop = self._make_tick_loop()
        loop.world.speaking = True
        loop.world.speech_priority = 2  # planner

        loop._start_conversation("text")

        cancel_calls = [
            c
            for c in loop._workers.send_to.call_args_list
            if len(c.args) >= 2 and c.args[0] == "tts" and c.args[1] == TTS_CMD_CANCEL
        ]
        assert cancel_calls


class TestPlannerSkillReachesBehavior:
    """A planner `skill` action must reach WANDER (it was stored on the scheduler and never read)."""

    @pytest.mark.asyncio
    async def test_scheduled_skill_is_what_the_behavior_engine_sees(self):
        from supervisor.core.action_scheduler import ValidatedPlan
        from supervisor.core.tick_loop import TickLoop

        class _Reflex:
            connected = False

            def on_telemetry(self, cb):
                pass

            def __getattr__(self, name):
                return lambda *a, **k: None

        class _Workers:
            def __getattr__(self, name):
                return lambda *a, **k: None

        loop = TickLoop(reflex=_Reflex(), face=None, workers=_Workers())  # type: ignore[arg-type]
        seen: list[str] = []
        step = loop._behavior.step

        def spy(robot, world, recent):
            seen.append(world.active_skill)
            return step(robot, world, recent)

        loop._behavior.step = spy  # type: ignore[method-assign]
        plan = ValidatedPlan(
            actions=[{"action": "skill", "name": "scan_for_target"}], ttl_ms=2000
        )
        loop._scheduler.schedule_plan(plan, now_mono_ms=1000.0, issued_mono_ms=1000.0)
        await loop._tick()
        assert seen == ["scan_for_target"]

    @pytest.mark.asyncio
    async def test_greet_holds_then_patrol_resumes(self):
        from supervisor.core.tick_loop import TickLoop

        class _Stub:
            connected = False

            def on_telemetry(self, cb):
                pass

            def __getattr__(self, name):
                return lambda *a, **k: None

        loop = TickLoop(reflex=_Stub(), face=None, workers=_Stub())  # type: ignore[arg-type]
        loop.robot.tick_mono_ms = 10_000.0
        loop._trigger_greet(10_000.0)
        await loop._tick()
        assert loop.world.active_skill == "greet_on_button"
        loop.robot.tick_mono_ms = 10_000.0 + loop._greet_hold_ms + 1
        await loop._tick()
        assert loop.world.active_skill == "patrol_drift"


class TestObstacleEscape:
    """OBSTACLE alone must not trap the robot: reverse is allowed, capped (mirrors the reflex)."""

    def _robot(self, faults: int) -> RobotState:
        return RobotState(
            mode=Mode.WANDER, reflex_connected=True, fault_flags=faults, range_mm=214
        )

    def test_reverse_allowed_and_capped(self):
        from supervisor.core.safety import OBSTACLE_ESCAPE_MAX_MM_S

        r = self._robot(Fault.OBSTACLE)
        out = apply_safety(DesiredTwist(-120, 400), r, WorldState())
        assert out.v_mm_s < 0
        assert -out.v_mm_s <= OBSTACLE_ESCAPE_MAX_MM_S
        assert any(c.reason.endswith("escape") for c in r.speed_caps)

    def test_slow_reverse_still_records_the_gate(self):
        r = self._robot(Fault.OBSTACLE)
        apply_safety(DesiredTwist(-40, 0), r, WorldState())
        assert r.speed_caps[0].reason == "fault=0x0040 escape"

    @pytest.mark.parametrize("v,w", [(100, 0), (0, 400), (0, 0)])
    def test_forward_and_spin_stay_blocked(self, v, w):
        out = apply_safety(
            DesiredTwist(v, w), self._robot(Fault.OBSTACLE), WorldState()
        )
        assert (out.v_mm_s, out.w_mrad_s) == (0, 0)

    def test_any_other_fault_blocks_reverse(self):
        r = self._robot(Fault.OBSTACLE | Fault.STALL)
        out = apply_safety(DesiredTwist(-100, 0), r, WorldState())
        assert (out.v_mm_s, out.w_mrad_s) == (0, 0)

    def test_motion_mode_can_be_entered_with_only_obstacle(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        ok, _ = sm.request_mode(Mode.TELEOP, True, int(Fault.OBSTACLE))
        assert ok

    def test_motion_mode_refused_with_other_faults(self):
        sm = SupervisorSM()
        sm.update(reflex_connected=True, fault_flags=0)
        ok, why = sm.request_mode(Mode.TELEOP, True, int(Fault.OBSTACLE | Fault.TILT))
        assert not ok and "faults active" in why

    def test_wander_backs_away_while_latched_even_when_sonar_is_blind(self):
        from supervisor.core.skill_executor import SkillExecutor
        from supervisor.devices.protocol import RangeStatus

        sk = SkillExecutor(obstacle_escape_max_mm=400, obstacle_escape_max_ms=8000)
        r = self._robot(Fault.OBSTACLE)
        r.range_mm, r.range_status = (
            0,
            int(RangeStatus.TIMEOUT),
        )  # grazing wall: no echo
        r.tick_dt_ms = 20.0
        r.speed_l_mm_s = r.speed_r_mm_s = -100
        r.tick_mono_ms = 1000.0
        assert sk.step(r, active_skill="patrol_drift").v_mm_s < 0
        out = None
        for i in range(
            1, 300
        ):  # 100 mm/s for up to 6 s: the 400 mm bound ends it first
            r.tick_mono_ms = 1000.0 + 20 * i
            out = sk.step(r, active_skill="patrol_drift")
            if out == DesiredTwist(0, 0):
                break
        assert out == DesiredTwist(0, 0)
        assert 3900 <= r.tick_mono_ms - 1000.0 <= 4100
        r.fault_flags = 0
        r.range_status, r.range_mm = int(RangeStatus.OK), 2000
        assert (
            sk.step(r, active_skill="patrol_drift").v_mm_s > 0
        )  # released: patrol resumes


class TestNoProgress:
    """WANDER notices it is pushing something it cannot see, and backs off."""

    def test_commanded_but_wheels_still_triggers_one_retreat_cycle(self):
        from supervisor.core.skill_executor import SkillExecutor

        sk = SkillExecutor(no_progress_ms=1000)
        r = RobotState(
            mode=Mode.WANDER, reflex_connected=True, range_mm=0, range_status=1
        )
        r.twist_capped = DesiredTwist(40, -60)  # governed command was real...
        r.speed_l_mm_s = r.speed_r_mm_s = 0  # ...and nothing turns
        out = None
        for t in range(0, 1200, 20):
            r.tick_mono_ms = 5000.0 + t
            out = sk.step(r, active_skill="patrol_drift")
        assert out is not None and out.v_mm_s < 0, (
            "should be reversing after > 1 s stalled"
        )
        cycle = 900 + 1100 + 350
        r.speed_l_mm_s = r.speed_r_mm_s = -100  # it moves again
        r.tick_mono_ms = 5000.0 + 1200 + cycle + 50
        assert sk.step(r, active_skill="patrol_drift").v_mm_s > 0  # patrol resumes

    def test_moving_robot_never_triggers(self):
        from supervisor.core.skill_executor import SkillExecutor

        sk = SkillExecutor(no_progress_ms=1000)
        r = RobotState(
            mode=Mode.WANDER, reflex_connected=True, range_mm=2000, range_status=0
        )
        r.twist_capped = DesiredTwist(80, 120)
        r.speed_l_mm_s, r.speed_r_mm_s = 70, 90
        for t in range(0, 5000, 20):
            r.tick_mono_ms = 5000.0 + t
            assert sk.step(r, active_skill="patrol_drift").v_mm_s > 0

    def test_spin_in_place_that_does_not_turn_triggers(self):
        from supervisor.core.skill_executor import SkillExecutor

        sk = SkillExecutor(no_progress_ms=1000)
        r = RobotState(
            mode=Mode.WANDER, reflex_connected=True, range_mm=380, range_status=0
        )
        r.twist_capped = DesiredTwist(0, 200)
        r.speed_l_mm_s, r.speed_r_mm_s, r.gyro_z_mrad_s = (
            -14,
            0,
            5,
        )  # tracks barely, body not
        out = None
        for t in range(0, 1200, 20):
            r.tick_mono_ms = 5000.0 + t
            out = sk.step(r, active_skill="patrol_drift")
        assert out is not None and out.v_mm_s < 0

    def test_one_encoder_count_of_jitter_still_counts_as_stalled(self):
        from supervisor.core.skill_executor import SkillExecutor

        sk = SkillExecutor(no_progress_ms=1000)
        r = RobotState(
            mode=Mode.WANDER, reflex_connected=True, range_mm=0, range_status=1
        )
        r.twist_capped = DesiredTwist(40, -60)
        out = None
        for i, t in enumerate(range(0, 1200, 20)):
            r.speed_l_mm_s = 14 if i % 2 else 0
            r.tick_mono_ms = 5000.0 + t
            out = sk.step(r, active_skill="patrol_drift")
        assert out is not None and out.v_mm_s < 0


def test_escape_is_not_throttled_by_forward_range():
    from supervisor.core.safety import OBSTACLE_ESCAPE_MAX_MM_S

    r = RobotState(
        mode=Mode.WANDER,
        reflex_connected=True,
        fault_flags=Fault.OBSTACLE,
        range_mm=214,
    )
    out = apply_safety(DesiredTwist(-120, 400), r, WorldState())
    assert out.v_mm_s == -OBSTACLE_ESCAPE_MAX_MM_S
    assert not any(c.reason.startswith("range") for c in r.speed_caps)


class TestWanderTunables:
    def test_registry_defaults_are_the_code_defaults(self):
        from supervisor.api.param_registry import create_default_registry
        from supervisor.core.skill_executor import (
            WANDER_TUNABLES,
            wander_tunable_defaults,
        )

        reg = create_default_registry()
        defaults = wander_tunable_defaults()
        for name, (_kind, lo, hi, _step, _doc) in WANDER_TUNABLES.items():
            p = reg.get(f"wander.{name}")
            assert p is not None and p.default == defaults[name]
            assert lo <= defaults[name] <= hi, f"{name} default outside its bounds"

    def test_live_change_reaches_the_running_executor(self):
        from supervisor.api.param_registry import create_default_registry
        from supervisor.core.tick_loop import TickLoop

        class _Stub:
            connected = False

            def on_telemetry(self, cb):
                pass

            def __getattr__(self, name):
                return lambda *a, **k: None

        reg = create_default_registry()
        loop = TickLoop(reflex=_Stub(), face=None, workers=_Stub(), param_registry=reg)  # type: ignore[arg-type]
        ok, why = reg.set("wander.patrol_v_mm_s", 120)
        assert ok, why
        assert loop._skill._patrol_v_mm_s == 120
        ok, _ = reg.set("wander.patrol_v_mm_s", 900)  # outside the bounds
        assert not ok and loop._skill._patrol_v_mm_s == 120


# ── Relative heading from gyro_z ─────────────────────────────


class TestRelativeHeading:
    def _loop(self):
        from unittest.mock import AsyncMock, MagicMock

        from supervisor.core.tick_loop import TickLoop

        workers = MagicMock()
        workers.send_to = AsyncMock(return_value=True)
        return TickLoop(reflex=None, face=None, workers=workers)

    def test_turning_left_decreases_clockwise_heading(self):
        t = self._loop()
        t._integrate_heading(0, 0.0)
        for i in range(1, 51):  # 1 s at 50 Hz, 0.5 rad/s left (CCW positive)
            t._integrate_heading(500, i * 0.02)
        assert abs(t.robot.heading_rel_deg - (360.0 - 28.6479)) < 0.1

    def test_still_robot_does_not_creep(self):
        t = self._loop()
        t._integrate_heading(0, 0.0)
        for i in range(1, 500):
            t._integrate_heading(1, i * 0.02)  # 1 mrad/s of bias, under the deadband
        assert t.robot.heading_rel_deg == 0.0

    def test_a_telemetry_gap_is_not_a_turn(self):
        t = self._loop()
        t._integrate_heading(500, 0.0)
        t._integrate_heading(500, 10.0)  # 10 s gap: integrate at most 0.2 s
        assert abs((360.0 - t.robot.heading_rel_deg) - 5.7296) < 0.01
