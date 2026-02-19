"""Main runtime tick loop — 50 Hz control, 20 Hz telemetry broadcast."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Callable

from supervisor.devices.audio_orchestrator import AudioOrchestrator
from supervisor.devices.expressions import (
    EMOTION_TO_FACE_MOOD,
    GESTURE_TO_FACE_ID,
    normalize_emotion_name,
    normalize_face_gesture_name,
)
from supervisor.devices.face_client import FaceClient
from supervisor.devices.planner_client import PlannerClient, PlannerError, PlannerPlan
from supervisor.devices.protocol import (
    FaceButtonEventType,
    FaceButtonId,
    FaceSystemMode,
    Fault,
)
from supervisor.devices.reflex_client import ReflexClient
from supervisor.inputs.camera_vision import VisionProcess
from supervisor.planner.event_bus import PlannerEventBus
from supervisor.planner.scheduler import PlannerScheduler
from supervisor.planner.skill_executor import SkillExecutor
from supervisor.planner.speech_policy import SpeechPolicy
from supervisor.planner.validator import PlannerValidator
from supervisor.state.datatypes import DesiredTwist, Mode, RobotState
from supervisor.state.policies import apply_safety
from supervisor.state.supervisor_sm import SupervisorSM

log = logging.getLogger(__name__)

TICK_HZ = 50
TICK_PERIOD_S = 1.0 / TICK_HZ
TELEMETRY_HZ = 20
_TELEM_EVERY_N = TICK_HZ // TELEMETRY_HZ  # broadcast every N ticks

_JITTER_WARN_MS = 5.0
_PLAN_PERIOD_S = 1.0
_PLAN_RETRY_S = 3.0


class Runtime:
    """Orchestrates the 50 Hz control loop."""

    def __init__(
        self,
        reflex: ReflexClient,
        on_telemetry: Callable[[RobotState], None] | None = None,
        vision: VisionProcess | None = None,
        face: FaceClient | None = None,
        planner: PlannerClient | None = None,
        audio: AudioOrchestrator | None = None,
        robot_id: str = "",
    ) -> None:
        self._reflex = reflex
        self._face = face
        self._vision = vision
        self._planner = planner
        self._audio = audio
        self._robot_id = robot_id.strip()
        self._sm = SupervisorSM()
        self._state = RobotState()
        self._teleop_twist = DesiredTwist()
        self._on_telemetry = on_telemetry
        self._running = False
        self._tick_count = 0
        self._last_tick_mono = 0.0
        self._planner_task: asyncio.Task[PlannerPlan] | None = None
        self._audio_ptt_task: asyncio.Task[None] | None = None
        self._planner_task_started_mono_ms = 0.0
        self._planner_req_seq = 0
        self._planner_last_accepted_seq = -1
        self._planner_seen_plan_ids: OrderedDict[str, float] = OrderedDict()
        self._planner_seen_plan_ids_max = 256
        self._next_plan_mono = 0.0
        self._last_face_system_mode: int | None = None
        self._last_face_listening: bool | None = None
        self._next_greet_allowed_mono_ms = 0.0
        self._greet_skill_until_mono_ms = 0.0
        self._planner_fail_face_cooldown_until_ms = 0.0

        self._event_bus = PlannerEventBus()
        self._skill_executor = SkillExecutor()
        self._planner_validator = PlannerValidator()
        self._planner_scheduler = PlannerScheduler()
        self._speech_policy = SpeechPolicy()
        self._speech_event_seq_cursor = 0

        if face is not None:
            face.subscribe_button(self._on_face_button)
            face.subscribe_touch(self._on_face_touch)

        if planner:
            self._state.planner_enabled = True

    @property
    def state(self) -> RobotState:
        return self._state

    @property
    def sm(self) -> SupervisorSM:
        return self._sm

    def set_teleop_twist(self, v_mm_s: int, w_mrad_s: int) -> None:
        """Set desired twist from teleop input (WebSocket or gamepad)."""
        self._teleop_twist.v_mm_s = v_mm_s
        self._teleop_twist.w_mrad_s = w_mrad_s

    async def run(self) -> None:
        self._running = True
        self._last_tick_mono = time.monotonic()
        log.info("runtime: starting %d Hz tick loop", TICK_HZ)

        while self._running:
            t0 = time.monotonic()
            dt_ms = (t0 - self._last_tick_mono) * 1000.0
            self._last_tick_mono = t0

            self._tick(t0, dt_ms)
            self._step_planner(t0)

            elapsed = time.monotonic() - t0
            sleep_s = max(0.0, TICK_PERIOD_S - elapsed)
            await asyncio.sleep(sleep_s)

    def stop(self) -> None:
        self._running = False
        if self._planner_task and not self._planner_task.done():
            self._planner_task.cancel()
        if self._audio_ptt_task and not self._audio_ptt_task.done():
            self._audio_ptt_task.cancel()

    def request_mode(self, target: Mode) -> tuple[bool, str]:
        return self._sm.request_mode(
            target, self._reflex.connected, self._state.fault_flags
        )

    def request_estop(self) -> None:
        self._reflex.send_estop()

    def request_clear(self) -> tuple[bool, str]:
        self._reflex.send_clear_faults()
        return self._sm.clear_error(self._reflex.connected, self._state.fault_flags)

    def debug_devices(self) -> dict:
        debug = {
            "reflex": self._reflex.debug_snapshot(),
            "face": {
                "enabled": self._face is not None,
                "connected": False,
            },
            "vision": {
                "enabled": self._vision is not None,
                "alive": self._vision.alive if self._vision else False,
                "fps": round(self._state.vision_fps, 1),
                "age_ms": round(self._state.vision_age_ms, 1),
                "clear_confidence": round(self._state.clear_confidence, 2),
            },
            "audio": {
                "enabled": self._audio is not None,
            },
            "tick_hz": TICK_HZ,
            "telemetry_hz": TELEMETRY_HZ,
        }
        if self._face is not None:
            debug["face"] = self._face.debug_snapshot()
        if self._audio is not None:
            debug["audio"] = self._audio.debug_snapshot()
        return debug

    def debug_planner(self) -> dict:
        return {
            "events": self._event_bus.snapshot(limit=100),
            "scheduler": self._planner_scheduler.snapshot(),
            "speech_policy": self._speech_policy.snapshot(),
            "say_counters": {
                "requested": self._state.planner_say_requested,
                "enqueued": self._state.planner_say_enqueued,
                "dropped_reason": dict(self._state.planner_say_dropped_reason),
            },
            "ordering": {
                "last_accepted_seq": self._planner_last_accepted_seq,
                "seen_plan_ids": len(self._planner_seen_plan_ids),
            },
            "audio": self._audio.debug_snapshot() if self._audio else {"enabled": False},
        }

    # -- tick ----------------------------------------------------------------

    def _tick(self, t0: float, dt_ms: float) -> None:
        s = self._state
        s.tick_mono_ms = t0 * 1000.0
        s.tick_dt_ms = dt_ms

        if dt_ms > (TICK_PERIOD_S * 1000.0 + _JITTER_WARN_MS):
            log.warning(
                "tick jitter: %.1f ms (target %.1f ms)", dt_ms, TICK_PERIOD_S * 1000.0
            )

        # 1. Snapshot reflex telemetry
        tel = self._reflex.telemetry
        s.reflex_connected = self._reflex.connected
        s.speed_l_mm_s = tel.speed_l_mm_s
        s.speed_r_mm_s = tel.speed_r_mm_s
        s.gyro_z_mrad_s = tel.gyro_z_mrad_s
        s.battery_mv = tel.battery_mv
        s.fault_flags = tel.fault_flags
        s.range_mm = tel.range_mm
        s.range_status = tel.range_status
        s.reflex_seq = tel.seq
        s.reflex_rx_mono_ms = tel.rx_mono_ms
        s.v_meas_mm_s = tel.v_meas_mm_s
        s.w_meas_mrad_s = tel.w_meas_mrad_s

        # 1a. Snapshot face telemetry
        if self._face:
            s.face_connected = self._face.connected
            if self._face.connected:
                ft = self._face.telemetry
                s.face_mood = ft.mood_id
                s.face_gesture = ft.active_gesture
                s.face_system_mode = ft.system_mode
                s.face_touch_active = ft.touch_active
                s.face_talking = ft.talking
                s.face_listening = ft.ptt_listening
                s.face_seq = ft.seq
                s.face_rx_mono_ms = ft.rx_mono_ms
                last_button = self._face.last_button
                if last_button is not None:
                    s.face_last_button_id = last_button.button_id
                    s.face_last_button_event = last_button.event_type
                    s.face_last_button_state = last_button.state
            else:
                s.face_touch_active = False
                s.face_talking = False
                s.face_listening = False

        self._sync_audio_ptt_from_face()

        # 1.5. Read latest vision snapshot (non-blocking)
        if self._vision:
            snap = self._vision.latest()
            if snap:
                s.clear_confidence = snap.clear_confidence
                s.ball_confidence = snap.ball_confidence
                s.ball_bearing_deg = snap.ball_bearing_deg
                s.vision_age_ms = s.tick_mono_ms - snap.timestamp_mono_ms
                s.vision_fps = snap.fps
            # If snap is None, keep previous values (vision_age_ms will grow stale)

        # 2. Edge-detect into event bus
        self._event_bus.ingest_state(s)
        s.planner_event_count = self._event_bus.event_count

        # 3. Update state machine
        s.mode = self._sm.update(s.reflex_connected, s.fault_flags)

        # 4. Get desired twist from active input/skill
        if s.mode == Mode.TELEOP:
            s.twist_cmd = DesiredTwist(
                self._teleop_twist.v_mm_s, self._teleop_twist.w_mrad_s
            )
        elif s.mode == Mode.WANDER:
            s.twist_cmd = self._skill_executor.step(
                s,
                active_skill=self._planner_scheduler.active_skill,
                recent_events=self._event_bus.latest(limit=20),
            )
        else:
            s.twist_cmd = DesiredTwist(0, 0)

        # 5. Apply safety policy
        s.twist_capped = apply_safety(s.twist_cmd, s)

        # 6. Send to reflex
        if s.reflex_connected:
            if s.twist_capped.v_mm_s == 0 and s.twist_capped.w_mrad_s == 0:
                # Still send zero twist to reset command watchdog
                self._reflex.send_twist(0, 0)
            else:
                self._reflex.send_twist(s.twist_capped.v_mm_s, s.twist_capped.w_mrad_s)

        # 7. Push system mode to face
        if self._face:
            if self._face.connected:
                if s.mode == Mode.BOOT:
                    desired_face_mode = int(FaceSystemMode.BOOTING)
                elif s.mode == Mode.ERROR:
                    desired_face_mode = int(FaceSystemMode.ERROR_DISPLAY)
                else:
                    desired_face_mode = int(FaceSystemMode.NONE)

                if desired_face_mode != self._last_face_system_mode:
                    self._face.send_system_mode(desired_face_mode)
                    self._last_face_system_mode = desired_face_mode
            else:
                self._last_face_system_mode = None

        # 8. Execute due planner actions
        self._execute_due_planner_actions()

        # 9. Event-driven deterministic speech overlay
        self._step_speech_policy()

        # 10. Mirror planner scheduler/audio state into telemetry payload
        if (
            self._planner_scheduler.active_skill == "greet_on_button"
            and s.tick_mono_ms >= self._greet_skill_until_mono_ms
        ):
            self._planner_scheduler.active_skill = "patrol_drift"

        s.planner_active_skill = self._planner_scheduler.active_skill
        s.planner_plan_dropped_stale = self._planner_scheduler.plan_dropped_stale
        s.planner_plan_dropped_cooldown = self._planner_scheduler.plan_dropped_cooldown
        if self._audio is not None:
            s.planner_speech_queue_depth = self._audio.speech_queue_depth

        # 11. Broadcast telemetry at decimated rate
        self._tick_count += 1
        if self._on_telemetry and (self._tick_count % _TELEM_EVERY_N == 0):
            self._on_telemetry(s)

    def _step_planner(self, t0: float) -> None:
        if not self._planner:
            return

        s = self._state

        if self._planner_task and self._planner_task.done():
            try:
                plan = self._planner_task.result()
                s.planner_connected = True
                s.planner_last_error = ""
                self._apply_planner_plan(plan)
                self._next_plan_mono = t0 + _PLAN_PERIOD_S
            except asyncio.CancelledError:
                self._next_plan_mono = t0 + _PLAN_RETRY_S
            except PlannerError as e:
                s.planner_connected = False
                s.planner_last_error = str(e)
                self._on_planner_unavailable(now_mono_ms=t0 * 1000.0)
                self._next_plan_mono = t0 + _PLAN_RETRY_S
                log.warning("planner: %s", e)
            except Exception as e:
                s.planner_connected = False
                s.planner_last_error = str(e)
                self._on_planner_unavailable(now_mono_ms=t0 * 1000.0)
                self._next_plan_mono = t0 + _PLAN_RETRY_S
                log.warning("planner: unexpected error: %s", e)
            finally:
                self._planner_task = None

        if self._planner_task is None and t0 >= self._next_plan_mono:
            req_seq = self._planner_req_seq
            self._planner_req_seq += 1
            world_state = self._build_world_state(req_seq=req_seq)
            self._planner_task_started_mono_ms = t0 * 1000.0
            self._planner_task = asyncio.create_task(self._planner.request_plan(world_state))

    def _build_world_state(self, *, req_seq: int) -> dict:
        s = self._state
        trigger = "ball_seen" if s.ball_confidence >= 0.7 else "heartbeat"
        recent_events = [e.type for e in self._event_bus.latest(limit=8)]
        return {
            "robot_id": self._robot_id,
            "seq": int(req_seq),
            "monotonic_ts_ms": int(s.tick_mono_ms),
            "mode": s.mode.value,
            "battery_mv": s.battery_mv,
            "range_mm": s.range_mm,
            "faults": self._fault_names(s.fault_flags),
            "clear_confidence": s.clear_confidence,
            "ball_detected": s.ball_confidence >= 0.5,
            "ball_bearing_deg": s.ball_bearing_deg,
            "speed_l_mm_s": s.speed_l_mm_s,
            "speed_r_mm_s": s.speed_r_mm_s,
            "v_capped": s.twist_capped.v_mm_s,
            "w_capped": s.twist_capped.w_mrad_s,
            "trigger": trigger,
            "recent_events": recent_events,
            "planner_active_skill": self._planner_scheduler.active_skill,
            "face_talking": s.face_talking,
            "face_listening": s.face_listening,
        }

    @staticmethod
    def _fault_names(flags: int) -> list[str]:
        names: list[str] = []
        for fault in Fault:
            if fault == Fault.NONE:
                continue
            if flags & int(fault):
                names.append(fault.name)
        return names

    def _apply_planner_plan(self, plan: PlannerPlan) -> None:
        s = self._state
        now_ms = time.monotonic() * 1000.0

        if plan.robot_id and self._robot_id and plan.robot_id != self._robot_id:
            s.planner_plan_dropped_out_of_order += 1
            log.warning(
                "planner: robot_id mismatch (expected=%s got=%s)",
                self._robot_id,
                plan.robot_id,
            )
            return

        if plan.seq < self._planner_last_accepted_seq:
            s.planner_plan_dropped_out_of_order += 1
            log.warning(
                "planner: dropping out-of-order plan seq=%d (last=%d)",
                plan.seq,
                self._planner_last_accepted_seq,
            )
            return

        self._evict_seen_plan_ids(now_ms)
        seen_until = self._planner_seen_plan_ids.get(plan.plan_id)
        if seen_until is not None and seen_until >= now_ms:
            s.planner_plan_dropped_duplicate += 1
            log.debug("planner: dropping duplicate plan_id=%s", plan.plan_id)
            return

        validated = self._planner_validator.validate(plan.actions, plan.ttl_ms)
        self._planner_last_accepted_seq = plan.seq
        self._remember_plan_id(plan.plan_id, now_ms + max(validated.ttl_ms, 500))
        s.planner_last_plan_mono_ms = now_ms
        s.planner_last_plan_actions = len(validated.actions)
        s.planner_last_plan = validated.actions

        if validated.dropped_actions:
            self._planner_scheduler.plan_dropped_cooldown += validated.dropped_actions

        self._planner_scheduler.schedule_plan(
            validated,
            now_mono_ms=now_ms,
            issued_mono_ms=self._planner_task_started_mono_ms,
        )

    def _on_planner_unavailable(self, *, now_mono_ms: float) -> None:
        dropped = self._planner_scheduler.clear_queued_actions()
        if dropped:
            self._planner_scheduler.plan_dropped_stale += dropped

        if self._audio is not None:
            asyncio.create_task(self._audio.cancel_planner_speech())

        if (
            self._face
            and self._face.connected
            and now_mono_ms >= self._planner_fail_face_cooldown_until_ms
        ):
            gesture_id = GESTURE_TO_FACE_ID.get("confused")
            if gesture_id is not None:
                self._face.send_gesture(gesture_id)
            self._planner_fail_face_cooldown_until_ms = now_mono_ms + 3000.0

    def _evict_seen_plan_ids(self, now_mono_ms: float) -> None:
        stale = [k for k, exp in self._planner_seen_plan_ids.items() if exp < now_mono_ms]
        for key in stale:
            self._planner_seen_plan_ids.pop(key, None)
        while len(self._planner_seen_plan_ids) > self._planner_seen_plan_ids_max:
            self._planner_seen_plan_ids.popitem(last=False)

    def _remember_plan_id(self, plan_id: str, expires_mono_ms: float) -> None:
        key = str(plan_id).strip()
        if not key:
            return
        self._planner_seen_plan_ids[key] = float(expires_mono_ms)
        self._planner_seen_plan_ids.move_to_end(key)
        while len(self._planner_seen_plan_ids) > self._planner_seen_plan_ids_max:
            self._planner_seen_plan_ids.popitem(last=False)

    def _execute_due_planner_actions(self) -> None:
        s = self._state
        face_locked = bool(s.face_listening or s.face_talking)
        actions = self._planner_scheduler.pop_due_actions(
            now_mono_ms=s.tick_mono_ms,
            face_locked=face_locked,
        )
        if not actions:
            return

        for action in actions:
            action_type = action.get("action")

            if action_type == "emote":
                if not self._face or not self._face.connected:
                    continue
                name = normalize_emotion_name(str(action.get("name", "")))
                if not name:
                    continue
                mood = EMOTION_TO_FACE_MOOD.get(name)
                if mood is None:
                    continue
                intensity = action.get("intensity", 0.7)
                if not isinstance(intensity, (int, float)):
                    intensity = 0.7
                self._face.send_state(
                    emotion_id=mood,
                    intensity=max(0.0, min(1.0, float(intensity))),
                )

            elif action_type == "gesture":
                if not self._face or not self._face.connected:
                    continue
                name = normalize_face_gesture_name(str(action.get("name", "")))
                if not name:
                    continue
                gesture_id = GESTURE_TO_FACE_ID.get(name)
                if gesture_id is not None:
                    self._face.send_gesture(gesture_id)

            elif action_type == "say":
                text = action.get("text")
                if isinstance(text, str) and text:
                    if not self._enqueue_say(text, source="planner"):
                        self._planner_scheduler.plan_dropped_cooldown += 1

    def _on_face_button(self, evt) -> None:
        self._event_bus.on_face_button(evt)
        if evt.button_id != int(FaceButtonId.ACTION):
            return
        if evt.event_type != int(FaceButtonEventType.CLICK):
            return

        now_ms = float(evt.timestamp_mono_ms)
        if now_ms < self._next_greet_allowed_mono_ms:
            return

        self._next_greet_allowed_mono_ms = now_ms + 5000.0
        self._greet_skill_until_mono_ms = now_ms + 1800.0
        routine = self._planner_validator.validate(
            [
                {"action": "skill", "name": "greet_on_button"},
                {"action": "emote", "name": "happy", "intensity": 0.8},
                {"action": "gesture", "name": "nod"},
                {"action": "say", "text": "Hi friend!"},
            ],
            ttl_ms=1600,
        )
        self._planner_scheduler.schedule_plan(
            routine,
            now_mono_ms=now_ms,
            issued_mono_ms=now_ms,
        )

    def _on_face_touch(self, evt) -> None:
        self._event_bus.on_face_touch(evt)

    def _sync_audio_ptt_from_face(self) -> None:
        if self._audio is None:
            return
        listening = bool(self._state.face_listening)
        if self._last_face_listening is None:
            self._last_face_listening = listening
            if listening:
                self._schedule_audio_ptt_sync(listening)
            return
        if listening == self._last_face_listening:
            return
        self._last_face_listening = listening
        self._schedule_audio_ptt_sync(listening)

    def _schedule_audio_ptt_sync(self, enabled: bool) -> None:
        if self._audio is None:
            return
        if self._audio_ptt_task and not self._audio_ptt_task.done():
            self._audio_ptt_task.cancel()
        task = asyncio.create_task(self._audio.set_ptt_enabled(enabled))
        self._audio_ptt_task = task
        task.add_done_callback(self._on_audio_ptt_task_done)

    def _on_audio_ptt_task_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.warning("audio ptt sync failed: %s", exc)

    def _step_speech_policy(self) -> None:
        s = self._state
        new_events = self._event_bus.events_since(self._speech_event_seq_cursor, limit=32)
        if not new_events:
            return
        self._speech_event_seq_cursor = int(new_events[-1].seq)

        intents, drops = self._speech_policy.generate(
            state=s,
            events=new_events,
            now_mono_ms=s.tick_mono_ms,
        )
        for reason in drops:
            self._record_say_drop(reason)
        for intent in intents:
            self._enqueue_say(intent.text, source="policy")

    def _enqueue_say(self, text: str, *, source: str) -> bool:
        s = self._state
        if not isinstance(text, str):
            self._record_say_drop(f"{source}_invalid_text")
            return False
        clean = text.strip()
        if not clean:
            self._record_say_drop(f"{source}_empty_text")
            return False

        s.planner_say_requested += 1
        if self._planner is not None and not s.planner_connected:
            self._record_say_drop(f"{source}_planner_unreachable")
            return False
        if self._audio is None:
            self._record_say_drop(f"{source}_audio_unavailable")
            return False
        if not self._audio.enqueue_speech(clean):
            self._record_say_drop(f"{source}_queue_full")
            return False

        s.planner_say_enqueued += 1
        return True

    def _record_say_drop(self, reason: str) -> None:
        if not reason:
            return
        s = self._state
        s.planner_say_dropped_reason[reason] = (
            s.planner_say_dropped_reason.get(reason, 0) + 1
        )
