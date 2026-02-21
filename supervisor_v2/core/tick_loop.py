"""50 Hz control loop — replaces v1 runtime.py.

Each tick:
1. Drain worker events (non-blocking from worker_manager)
2. Read MCU telemetry (same as v1)
3. Edge detection (event_bus.ingest)
4. State machine update
5. Behavior engine: pick twist source
6. Safety policies (7-layer)
7. Emit outputs: MCU commands + worker actions
8. Broadcast telemetry at 20 Hz
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable

from supervisor_v2.core.action_scheduler import ActionScheduler, PlanValidator
from supervisor_v2.core.behavior_engine import BehaviorEngine
from supervisor_v2.core.event_bus import PlannerEvent, PlannerEventBus
from supervisor_v2.core.event_router import EventRouter
from supervisor_v2.core.safety import apply_safety
from supervisor_v2.core.skill_executor import SkillExecutor
from supervisor_v2.core.speech_policy import SpeechPolicy
from supervisor_v2.core.state import (
    DesiredTwist,
    Mode,
    RobotState,
    WorldState,
)
from supervisor_v2.core.state_machine import SupervisorSM
from supervisor_v2.core.worker_manager import WorkerManager
from supervisor_v2.devices.expressions import (
    EMOTION_TO_FACE_MOOD,
    GESTURE_TO_FACE_ID,
    normalize_emotion_name,
    normalize_face_gesture_name,
)
from supervisor_v2.devices.face_client import FaceClient
from supervisor_v2.devices.protocol import (
    FaceButtonEventType,
    FaceButtonId,
    FaceSystemMode,
)
from supervisor_v2.devices.reflex_client import ReflexClient
from supervisor_v2.messages.envelope import Envelope
from supervisor_v2.messages.types import (
    AI_CMD_END_CONVERSATION,
    AI_CMD_START_CONVERSATION,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_GESTURE,
    AI_CONVERSATION_DONE,
    TTS_CMD_CANCEL,
    TTS_CMD_SPEAK,
    TTS_CMD_START_MIC,
    TTS_CMD_STOP_MIC,
)

log = logging.getLogger(__name__)

TICK_HZ = 50
_TICK_PERIOD_S = 1.0 / TICK_HZ
_TELEM_EVERY_N = max(1, TICK_HZ // 20)  # 20 Hz telemetry
_PLAN_PERIOD_S = 5.0
_PLAN_RETRY_S = 5.0


class TickLoop:
    """The v2 50 Hz control loop."""

    def __init__(
        self,
        *,
        reflex: ReflexClient | None,
        face: FaceClient | None,
        workers: WorkerManager,
        on_telemetry: Callable[[dict], Any] | None = None,
        planner_enabled: bool = False,
        robot_id: str = "",
    ) -> None:
        self._reflex = reflex
        self._face = face
        self._workers = workers
        self._on_telemetry = on_telemetry

        # State
        self.robot = RobotState()
        self.world = WorldState(planner_enabled=planner_enabled)

        # Subsystems
        self._sm = SupervisorSM()
        self._event_bus = PlannerEventBus()
        self._skill = SkillExecutor()
        self._behavior = BehaviorEngine(self._skill)
        self._validator = PlanValidator()
        self._scheduler = ActionScheduler()
        self._speech_policy = SpeechPolicy()
        self._event_router = EventRouter(self.world, self._scheduler, self._validator)

        # Teleop
        self._teleop_twist = DesiredTwist()

        # Tick state
        self._tick_seq = 0
        self._telem_counter = 0
        self._running = False

        # Recent worker events for this tick (buffered by on_worker_event)
        self._pending_events: deque[tuple[str, Envelope]] = deque()

        # Conversation face state
        self._conversation_emotion: str = ""
        self._conversation_intensity: float = 0.0
        self._conversation_gestures: list[str] = []

        # Planner state
        self._robot_id = robot_id
        self._last_plan_request_ms = 0.0

        # Button debounce
        self._last_greet_ms = 0.0
        self._greet_debounce_ms = 5000.0

        # Face flags sent on reconnect
        self._face_flags_sent = False
        self._last_face_system_mode: int | None = None

        # Wire MCU callbacks
        if self._reflex:
            self._reflex.on_telemetry(self._on_reflex_telemetry)
        if self._face:
            self._face.subscribe_button(self._on_face_button)
            self._face.subscribe_touch(self._event_bus.on_face_touch)

    # ── Public API ───────────────────────────────────────────────

    async def run(self) -> None:
        """Run the tick loop until stopped."""
        self._running = True
        t_prev = time.monotonic()
        log.info("tick loop started at %d Hz", TICK_HZ)

        try:
            while self._running:
                t0 = time.monotonic()
                dt = t0 - t_prev
                t_prev = t0

                self.robot.tick_mono_ms = t0 * 1000.0
                self.robot.tick_dt_ms = dt * 1000.0

                await self._tick()

                elapsed = time.monotonic() - t0
                sleep_s = _TICK_PERIOD_S - elapsed
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            log.info("tick loop stopped")

    def stop(self) -> None:
        self._running = False

    def set_teleop_twist(self, v_mm_s: int, w_mrad_s: int) -> None:
        self._behavior.set_teleop_twist(v_mm_s, w_mrad_s)

    def request_mode(self, target: str) -> tuple[bool, str]:
        target_mode = Mode(target)
        return self._sm.request_mode(
            target_mode,
            self.robot.reflex_connected,
            self.robot.fault_flags,
        )

    def clear_error(self) -> tuple[bool, str]:
        # Send CLEAR_FAULTS to MCU to actually clear hardware fault flags
        if self._reflex and self._reflex.connected:
            self._reflex.send_clear_faults()

        return self._sm.clear_error(
            self.robot.reflex_connected,
            self.robot.fault_flags,
        )

    async def on_worker_event(self, worker_name: str, env: Envelope) -> None:
        """Called by worker_manager when a worker sends an event."""
        self._pending_events.append((worker_name, env))

    # ── Debug ────────────────────────────────────────────────────

    def debug_planner(self) -> dict:
        return {
            "scheduler": self._scheduler.snapshot(),
            "event_bus": self._event_bus.snapshot(),
            "speech_policy": self._speech_policy.snapshot(),
        }

    def debug_devices(self) -> dict:
        result: dict[str, Any] = {}
        if self._reflex:
            result["reflex"] = self._reflex.debug_snapshot()
        if self._face:
            result["face"] = self._face.debug_snapshot()
        result["workers"] = self._workers.worker_snapshot()
        return result

    # ── Tick implementation ──────────────────────────────────────

    async def _tick(self) -> None:
        now_ms = self.robot.tick_mono_ms
        self._tick_seq += 1

        # 1. Drain worker events
        while self._pending_events:
            worker_name, env = self._pending_events.popleft()
            await self._event_router.route(worker_name, env)
            self._handle_face_events(env)

        # 2. MCU telemetry (already arriving via callbacks)
        self._snapshot_reflex()
        self._snapshot_face()

        # 3. Edge detection
        self._event_bus.ingest(self.robot, self.world)
        self.world.event_count = self._event_bus.event_count

        # 4. State machine
        self.robot.mode = self._sm.update(
            self.robot.reflex_connected, self.robot.fault_flags
        )

        # 5. Behavior engine — pick twist
        recent = self._event_bus.latest(10)
        desired = self._behavior.step(self.robot, self.world, recent)
        self.robot.twist_cmd = desired

        # 6. Safety policies
        capped = apply_safety(desired, self.robot, self.world)
        self.robot.twist_capped = capped

        # 7. Emit outputs
        self._emit_mcu(capped, now_ms)
        await self._emit_worker_actions(now_ms, recent)

        # 8. Telemetry broadcast
        self._telem_counter += 1
        if self._telem_counter >= _TELEM_EVERY_N:
            self._telem_counter = 0
            self._broadcast_telemetry()

    # ── MCU telemetry callbacks ──────────────────────────────────

    def _on_reflex_telemetry(self, tel: Any) -> None:
        self.robot.speed_l_mm_s = tel.speed_l_mm_s
        self.robot.speed_r_mm_s = tel.speed_r_mm_s
        self.robot.gyro_z_mrad_s = tel.gyro_z_mrad_s
        self.robot.battery_mv = tel.battery_mv
        self.robot.fault_flags = tel.fault_flags
        self.robot.range_mm = tel.range_mm
        self.robot.range_status = tel.range_status
        self.robot.reflex_seq = tel.seq
        self.robot.reflex_rx_mono_ms = tel.rx_mono_ms
        self.robot.v_meas_mm_s = tel.v_meas_mm_s
        self.robot.w_meas_mrad_s = tel.w_meas_mrad_s

    def _snapshot_reflex(self) -> None:
        self.robot.reflex_connected = self._reflex.connected if self._reflex else False

    def _snapshot_face(self) -> None:
        if not self._face:
            self.robot.face_connected = False
            return

        self.robot.face_connected = self._face.connected

        if self._face.connected and not self._face_flags_sent:
            self._face_flags_sent = True
            # Send default flags on reconnect
            from supervisor_v2.devices.protocol import FACE_FLAGS_ALL

            self._face.send_flags(FACE_FLAGS_ALL)

        tel = self._face.telemetry
        if tel:
            self.robot.face_mood = tel.mood_id
            self.robot.face_gesture = tel.active_gesture
            self.robot.face_system_mode = tel.system_mode
            self.robot.face_touch_active = tel.touch_active
            self.robot.face_seq = tel.seq
            self.robot.face_rx_mono_ms = tel.rx_mono_ms

        # Sync face button state
        btn = self._face.last_button
        if btn:
            self.robot.face_last_button_id = btn.button_id
            self.robot.face_last_button_event = btn.event_type
            self.robot.face_last_button_state = btn.state

    def _on_face_button(self, evt: Any) -> None:
        """Handle face button events for PTT and greet."""
        self._event_bus.on_face_button(evt)

        # PTT toggle
        if evt.button_id == int(FaceButtonId.PTT) and evt.event_type == int(
            FaceButtonEventType.TOGGLE
        ):
            ptt_on = bool(evt.state)
            self.world.ptt_active = ptt_on
            if ptt_on:
                self._start_conversation()
            else:
                self._end_conversation()

        # ACTION click — greet routine
        if evt.button_id == int(FaceButtonId.ACTION) and evt.event_type == int(
            FaceButtonEventType.CLICK
        ):
            now_ms = time.monotonic() * 1000.0
            if now_ms - self._last_greet_ms > self._greet_debounce_ms:
                self._last_greet_ms = now_ms
                self._trigger_greet(now_ms)

    # ── Face composition (§8.2) ──────────────────────────────────

    def _handle_face_events(self, env: Envelope) -> None:
        """Buffer conversation emotion/gesture for face composition."""
        if env.type == AI_CONVERSATION_EMOTION:
            self._conversation_emotion = str(env.payload.get("emotion", ""))
            self._conversation_intensity = float(env.payload.get("intensity", 0.7))
        elif env.type == AI_CONVERSATION_GESTURE:
            self._conversation_gestures = list(env.payload.get("names", []))
        elif env.type == AI_CONVERSATION_DONE:
            self._conversation_emotion = ""
            self._conversation_intensity = 0.0
            self._conversation_gestures = []

    # ── Output emission ──────────────────────────────────────────

    def _emit_mcu(self, capped: DesiredTwist, now_ms: float) -> None:
        """Send commands to MCUs."""
        # Reflex: send twist every tick (even zero to reset CMD_TIMEOUT watchdog)
        if self._reflex and self._reflex.connected:
            self._reflex.send_twist(capped.v_mm_s, capped.w_mrad_s)

        if not self._face or not self._face.connected:
            self._last_face_system_mode = None
            return

        # Face system mode overlay — send only on change, skip when manual lock
        if not self.robot.face_manual_lock:
            if self.robot.mode == Mode.BOOT:
                desired_sys = int(FaceSystemMode.BOOTING)
            elif self.robot.mode == Mode.ERROR:
                desired_sys = int(FaceSystemMode.ERROR_DISPLAY)
            else:
                desired_sys = int(FaceSystemMode.NONE)
            if desired_sys != self._last_face_system_mode:
                self._face.send_system_mode(desired_sys, 0)
                self._last_face_system_mode = desired_sys

        # Talking layer — driven by TTS energy
        if self.world.speaking:
            self._face.send_talking(True, self.world.current_energy)
            self.robot.face_talking = True
            self.robot.face_talking_energy = self.world.current_energy
        elif self.robot.face_talking:
            self._face.send_talking(False, 0)
            self.robot.face_talking = False
            self.robot.face_talking_energy = 0

        # Skip auto-emotion when manual lock is on (dashboard control)
        if self.robot.face_manual_lock:
            self._conversation_gestures = []
            return

        # Conversation layer — emotion and gesture from AI worker
        if self._conversation_emotion:
            norm = normalize_emotion_name(self._conversation_emotion)
            if norm:
                mood_id = EMOTION_TO_FACE_MOOD.get(norm)
                if mood_id is not None:
                    self._face.send_state(mood_id, self._conversation_intensity)

        for g in self._conversation_gestures:
            norm_g = normalize_face_gesture_name(g)
            if norm_g:
                gid = GESTURE_TO_FACE_ID.get(norm_g)
                if gid is not None:
                    self._face.send_gesture(gid, 500)
        self._conversation_gestures = []

    async def _emit_worker_actions(
        self, now_ms: float, recent: list[PlannerEvent]
    ) -> None:
        """Send actions to workers: speech, plan execution."""
        # Execute due planner actions
        face_locked = (
            self.robot.face_talking
            or self.robot.face_listening
            or self.robot.face_manual_lock
        )
        due = self._scheduler.pop_due_actions(
            now_mono_ms=now_ms, face_locked=face_locked
        )

        for action in due:
            action_type = action.get("action", "")
            if action_type == "say":
                await self._enqueue_say(
                    action.get("text", ""), source="planner", priority=2
                )
            elif action_type == "emote":
                self._apply_emote(action)
            elif action_type == "gesture":
                self._apply_gesture(action)

        # Speech policy (deterministic, idle-priority speech)
        intents, drops = self._speech_policy.generate(
            state=self.robot,
            events=recent,
            now_mono_ms=now_ms,
        )
        for intent in intents:
            await self._enqueue_say(intent.text, source="speech_policy", priority=3)

        # Periodic plan requests
        if (
            self.world.planner_enabled
            and self.world.planner_connected
            and now_ms - self._last_plan_request_ms > _PLAN_PERIOD_S * 1000
        ):
            self._last_plan_request_ms = now_ms
            await self._request_plan(now_ms)

    async def _enqueue_say(
        self, text: str, source: str = "planner", priority: int = 2
    ) -> None:
        """Send speech to TTS worker via speech arbitration (§8.1)."""
        self.world.say_requested += 1

        # Speech arbitration: check if current speech has higher priority
        if self.world.speaking and priority >= self.world.speech_priority:
            self.world.say_dropped_reason[
                f"preempted_by_p{self.world.speech_priority}"
            ] = (
                self.world.say_dropped_reason.get(
                    f"preempted_by_p{self.world.speech_priority}", 0
                )
                + 1
            )
            return

        # If lower priority speech is active, cancel it
        if self.world.speaking and priority < self.world.speech_priority:
            await self._workers.send_to("tts", TTS_CMD_CANCEL)

        sent = await self._workers.send_to(
            "tts",
            TTS_CMD_SPEAK,
            {
                "text": text,
                "emotion": "neutral",
                "source": source,
                "priority": priority,
            },
        )
        if sent:
            self.world.say_enqueued += 1
            self.world.speech_source = source
            self.world.speech_priority = priority

    def _apply_emote(self, action: dict) -> None:
        """Apply a planner emote action to the face."""
        if not self._face or not self._face.connected:
            return
        name = normalize_emotion_name(str(action.get("name", "")))
        if not name:
            return
        mood_id = EMOTION_TO_FACE_MOOD.get(name)
        if mood_id is None:
            return
        intensity = float(action.get("intensity", 0.7))
        self._face.send_state(mood_id, intensity)

    def _apply_gesture(self, action: dict) -> None:
        """Apply a planner gesture action to the face."""
        if not self._face or not self._face.connected:
            return
        name = normalize_face_gesture_name(str(action.get("name", "")))
        if not name:
            return
        gid = GESTURE_TO_FACE_ID.get(name)
        if gid is None:
            return
        self._face.send_gesture(gid, 500)

    def _trigger_greet(self, now_ms: float) -> None:
        """ACTION button greet routine."""
        self._scheduler.active_skill = "greet_on_button"
        if self._face and self._face.connected:
            mood_id = EMOTION_TO_FACE_MOOD.get("excited", 2)
            self._face.send_state(mood_id, 0.8)
            gid = GESTURE_TO_FACE_ID.get("nod", 10)
            self._face.send_gesture(gid, 500)

    # ── Conversation control ─────────────────────────────────────

    def _start_conversation(self) -> None:
        """Start a PTT conversation."""
        if not self.world.both_audio_links_up:
            log.warning("cannot start conversation: audio links not up")
            return

        import uuid

        self.world.session_id = f"sess-{uuid.uuid4().hex[:12]}"
        self.world.turn_id = 1

        # Fire-and-forget async sends
        asyncio.ensure_future(
            self._workers.send_to(
                "ai",
                AI_CMD_START_CONVERSATION,
                {
                    "session_id": self.world.session_id,
                    "turn_id": self.world.turn_id,
                },
            )
        )
        asyncio.ensure_future(self._workers.send_to("tts", TTS_CMD_START_MIC))
        self.robot.face_listening = True

    def _end_conversation(self) -> None:
        """End a PTT conversation."""
        asyncio.ensure_future(self._workers.send_to("tts", TTS_CMD_STOP_MIC))
        asyncio.ensure_future(
            self._workers.send_to(
                "ai",
                AI_CMD_END_CONVERSATION,
                {
                    "session_id": self.world.session_id,
                },
            )
        )
        self.robot.face_listening = False
        self.world.session_id = ""
        self.world.turn_id = 0

    async def _request_plan(self, now_ms: float) -> None:
        """Send plan request to AI worker."""
        from supervisor_v2.messages.types import AI_CMD_REQUEST_PLAN

        world_dict = {
            "robot_id": self._robot_id,
            "mode": self.robot.mode.value,
            "battery_mv": self.robot.battery_mv,
            "range_mm": self.robot.range_mm,
            "faults": [],
            "ball_detected": self.world.ball_confidence > 0.3,
            "ball_confidence": round(self.world.ball_confidence, 2),
            "ball_bearing_deg": round(self.world.ball_bearing_deg, 1),
            "vision_age_ms": round(self.world.vision_age_ms, 1),
            "speed_l_mm_s": self.robot.speed_l_mm_s,
            "speed_r_mm_s": self.robot.speed_r_mm_s,
            "trigger": "periodic",
            "recent_events": [e.type for e in self._event_bus.latest(5)],
            "planner_active_skill": self.world.active_skill,
            "face_talking": self.robot.face_talking,
            "face_listening": self.robot.face_listening,
        }
        await self._workers.send_to(
            "ai", AI_CMD_REQUEST_PLAN, {"world_state": world_dict}
        )

    # ── Telemetry ────────────────────────────────────────────────

    def _broadcast_telemetry(self) -> None:
        if not self._on_telemetry:
            return
        combined = self.robot.to_dict()
        combined.update(self.world.to_dict())
        combined["worker_health"] = self._workers.worker_snapshot()
        self._on_telemetry(combined)
