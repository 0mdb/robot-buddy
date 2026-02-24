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
import math
import time
from collections import deque
from typing import Any, Callable

from supervisor.core.action_scheduler import ActionScheduler, PlanValidator
from supervisor.core.behavior_engine import BehaviorEngine
from supervisor.core.event_bus import PlannerEvent, PlannerEventBus
from supervisor.core.event_router import EventRouter
from supervisor.core.safety import apply_safety
from supervisor.core.skill_executor import SkillExecutor
from supervisor.core.speech_policy import SpeechPolicy
from supervisor.core.state import (
    DesiredTwist,
    Mode,
    RobotState,
    WorldState,
)
from supervisor.core.state_machine import SupervisorSM
from supervisor.core.worker_manager import WorkerManager
from supervisor.devices.expressions import (
    EMOTION_TO_FACE_MOOD,
    GESTURE_TO_FACE_ID,
    normalize_emotion_name,
    normalize_face_gesture_name,
)
from supervisor.devices.face_client import FaceClient
from supervisor.devices.protocol import (
    FaceButtonEventType,
    FaceButtonId,
    FaceSystemMode,
)
from supervisor.api.conversation_capture import ConversationCapture
from supervisor.devices.reflex_client import ReflexClient
from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    AI_CMD_END_CONVERSATION,
    AI_CMD_END_UTTERANCE,
    AI_CMD_SEND_PROFILE,
    AI_CMD_START_CONVERSATION,
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_GESTURE,
    CONV_SESSION_ENDED,
    CONV_SESSION_STARTED,
    EAR_CMD_PAUSE_VAD,
    EAR_CMD_RESUME_VAD,
    EAR_CMD_START_LISTENING,
    EAR_CMD_STOP_LISTENING,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_WAKE_WORD,
    PERSONALITY_EVENT_AI_EMOTION,
    PERSONALITY_EVENT_BUTTON_PRESS,
    PERSONALITY_EVENT_CONV_ENDED,
    PERSONALITY_EVENT_CONV_STARTED,
    PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
    PERSONALITY_EVENT_MEMORY_EXTRACT,
    PERSONALITY_EVENT_SPEECH_ACTIVITY,
    PERSONALITY_EVENT_SYSTEM_STATE,
    PERSONALITY_LLM_PROFILE,
    TTS_CMD_CANCEL,
    TTS_CMD_PLAY_CHIME,
    TTS_CMD_SPEAK,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_FINISHED,
    TTS_EVENT_STARTED,
)

# PE snapshot staleness threshold (spec §11.3: 3× worker tick rate)
_PE_STALE_MS = 3000.0

log = logging.getLogger(__name__)

TICK_HZ = 50
_TICK_PERIOD_S = 1.0 / TICK_HZ
_TELEM_EVERY_N = max(1, TICK_HZ // 20)  # 20 Hz telemetry
_PLAN_PERIOD_S = 5.0
_PLAN_RETRY_S = 5.0


class TickLoop:
    """The v2 50 Hz control loop."""

    # After TTS finishes, keep talking animation alive for this many ticks so it
    # trails OS/hardware audio buffer drain (~300 ms at 50 Hz).
    _POST_TALKING_GRACE_TICKS: int = 15

    def __init__(
        self,
        *,
        reflex: ReflexClient | None,
        face: FaceClient | None,
        workers: WorkerManager,
        on_telemetry: Callable[[dict], Any] | None = None,
        planner_enabled: bool = False,
        robot_id: str = "",
        low_battery_mv: int = 6400,
        conv_capture: ConversationCapture | None = None,
    ) -> None:
        self._reflex = reflex
        self._face = face
        self._workers = workers
        self._on_telemetry = on_telemetry
        self._low_battery_mv = low_battery_mv
        self._conv_capture = conv_capture

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

        # Conversation state machine
        from supervisor.core.conv_state import ConvStateTracker

        self._conv = ConvStateTracker()

        # Mood transition sequencer + guardrails (Phase 3)
        from supervisor.core.guardrails import Guardrails
        from supervisor.core.mood_sequencer import MoodSequencer

        self._mood_seq = MoodSequencer()
        self._guardrails = Guardrails()

        # Transition choreographer (Phase 4)
        from supervisor.core.conv_choreographer import ConvTransitionChoreographer

        self._conv_choreo = ConvTransitionChoreographer()

        # Emotion queuing (buffered during LISTENING/THINKING, applied on SPEAKING)
        self._queued_emotion: str = ""
        self._queued_intensity: float = 0.0

        # Face flags sent on reconnect
        self._face_flags_sent = False
        self._last_face_system_mode: int | None = None
        self._last_face_system_param: int = 0

        # Ticks remaining to hold talking animation after TTS_EVENT_FINISHED
        self._talking_grace_ticks: int = 0

        # PE system event forwarding state
        self._pe_boot_sent: bool = False
        self._pe_low_battery_sent: bool = False
        self._pe_prev_fault_flags: int = 0

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
            if self._conv_capture is not None:
                self._conv_capture.capture_envelope(env)

        # 1b. Update conversation state machine (auto-transitions, backchannel)
        self._conv.update(self.robot.tick_dt_ms)
        self.robot.face_conv_state = int(self._conv.state)
        self.robot.face_conv_timer_ms = self._conv.timer_ms

        # 2. MCU telemetry (already arriving via callbacks)
        self._snapshot_reflex()
        self._snapshot_face()

        # 3. Edge detection
        self._event_bus.ingest(self.robot, self.world)
        self.world.event_count = self._event_bus.event_count

        # 4. State machine
        prev_mode = self.robot.mode
        self.robot.mode = self._sm.update(
            self.robot.reflex_connected, self.robot.fault_flags
        )

        # 4b. Forward system events to personality worker
        self._forward_pe_system_events(prev_mode)

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
        self.robot.accel_x_mg = tel.accel_x_mg
        self.robot.accel_y_mg = tel.accel_y_mg
        self.robot.accel_z_mg = tel.accel_z_mg
        self.robot.battery_mv = tel.battery_mv
        self.robot.fault_flags = tel.fault_flags
        self.robot.range_mm = tel.range_mm
        self.robot.range_status = tel.range_status
        self.robot.reflex_seq = tel.seq
        self.robot.reflex_rx_mono_ms = tel.rx_mono_ms
        self.robot.v_meas_mm_s = tel.v_meas_mm_s
        self.robot.w_meas_mrad_s = tel.w_meas_mrad_s
        # Derived IMU values
        self.robot.tilt_angle_deg = math.degrees(
            math.atan2(tel.accel_x_mg, tel.accel_z_mg)
        )
        self.robot.accel_magnitude_mg = math.sqrt(
            tel.accel_x_mg**2 + tel.accel_y_mg**2 + tel.accel_z_mg**2
        )

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
            from supervisor.devices.protocol import FACE_FLAGS_ALL

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

    def _forward_pe_system_events(self, prev_mode: Mode) -> None:
        """Forward system state transitions to personality worker."""
        # Boot complete: BOOT → IDLE transition
        if (
            not self._pe_boot_sent
            and prev_mode == Mode.BOOT
            and self.robot.mode == Mode.IDLE
        ):
            self._pe_boot_sent = True
            asyncio.ensure_future(
                self._workers.send_to(
                    "personality",
                    PERSONALITY_EVENT_SYSTEM_STATE,
                    {"event": "boot"},
                )
            )

        # Battery events (gated to fire once per threshold crossing)
        if self.robot.battery_mv > 0:
            is_low = self.robot.battery_mv < self._low_battery_mv
            if is_low and not self._pe_low_battery_sent:
                self._pe_low_battery_sent = True
                asyncio.ensure_future(
                    self._workers.send_to(
                        "personality",
                        PERSONALITY_EVENT_SYSTEM_STATE,
                        {"event": "low_battery", "battery_mv": self.robot.battery_mv},
                    )
                )
            elif not is_low and self._pe_low_battery_sent:
                self._pe_low_battery_sent = False

        # Fault transitions
        if self.robot.fault_flags != self._pe_prev_fault_flags:
            new_faults = self.robot.fault_flags & ~self._pe_prev_fault_flags
            cleared_faults = self._pe_prev_fault_flags & ~self.robot.fault_flags
            self._pe_prev_fault_flags = self.robot.fault_flags

            if new_faults:
                asyncio.ensure_future(
                    self._workers.send_to(
                        "personality",
                        PERSONALITY_EVENT_SYSTEM_STATE,
                        {"event": "fault_raised", "flags": new_faults},
                    )
                )
            if cleared_faults:
                asyncio.ensure_future(
                    self._workers.send_to(
                        "personality",
                        PERSONALITY_EVENT_SYSTEM_STATE,
                        {"event": "fault_cleared", "flags": cleared_faults},
                    )
                )

    def _on_face_button(self, evt: Any) -> None:
        """Handle face button events for PTT, cancel, and greet."""
        from supervisor.devices.protocol import FaceConvState

        self._event_bus.on_face_button(evt)

        # Notify personality worker (L0-10 button press)
        if evt.event_type == int(FaceButtonEventType.CLICK):
            asyncio.ensure_future(
                self._workers.send_to(
                    "personality",
                    PERSONALITY_EVENT_BUTTON_PRESS,
                    {"button_id": evt.button_id},
                )
            )

        # PTT toggle
        if evt.button_id == int(FaceButtonId.PTT) and evt.event_type == int(
            FaceButtonEventType.TOGGLE
        ):
            ptt_on = bool(evt.state)
            self.world.ptt_active = ptt_on
            if ptt_on:
                self._start_conversation("ptt")
                self._conv.ptt_held = True
                self._conv.set_state(FaceConvState.ATTENTION)
            else:
                self._conv.ptt_held = False
                self._end_conversation()

        # ACTION click — context-gated: cancel during session, greet outside
        if evt.button_id == int(FaceButtonId.ACTION) and evt.event_type == int(
            FaceButtonEventType.CLICK
        ):
            if self._conv.session_active:
                # Cancel active conversation
                self._conv.set_state(FaceConvState.DONE)
                if self.world.session_id:
                    self._end_conversation()
            else:
                # Greet routine (only outside conversation)
                now_ms = time.monotonic() * 1000.0
                if now_ms - self._last_greet_ms > self._greet_debounce_ms:
                    self._last_greet_ms = now_ms
                    self._trigger_greet(now_ms)

    # ── Face composition (§8.2) ──────────────────────────────────

    def _handle_face_events(self, env: Envelope) -> None:
        """Buffer conversation emotion/gesture and handle ear/TTS events.

        Also drives ConvStateTracker transitions for conversation phase tracking.
        """
        from supervisor.devices.protocol import FaceConvState

        if env.type == AI_CONVERSATION_EMOTION:
            emotion = str(env.payload.get("emotion", ""))
            intensity = float(env.payload.get("intensity", 0.7))
            # Queue emotions during LISTENING/THINKING (spec §2.3 layer clamping)
            if self._conv.state in (
                FaceConvState.LISTENING,
                FaceConvState.PTT,
                FaceConvState.THINKING,
            ):
                self._queued_emotion = emotion
                self._queued_intensity = intensity
            else:
                self._conversation_emotion = emotion
                self._conversation_intensity = intensity
            # Forward to personality worker (PE spec §11.1)
            pe_payload: dict[str, object] = {
                "emotion": emotion,
                "intensity": intensity,
            }
            session_id = env.payload.get("session_id", "")
            if session_id:
                pe_payload["session_id"] = session_id
            turn_id = env.payload.get("turn_id")
            if turn_id is not None:
                pe_payload["turn_id"] = turn_id
            mood_reason = env.payload.get("mood_reason", "")
            if mood_reason:
                pe_payload["mood_reason"] = mood_reason
            asyncio.ensure_future(
                self._workers.send_to(
                    "personality",
                    PERSONALITY_EVENT_AI_EMOTION,
                    pe_payload,
                )
            )
        elif env.type == AI_CONVERSATION_GESTURE:
            self._conversation_gestures = list(env.payload.get("names", []))
        elif env.type == AI_CONVERSATION_DONE:
            self._conversation_emotion = ""
            self._conversation_intensity = 0.0
            self._conversation_gestures = []
            self._queued_emotion = ""
            self._queued_intensity = 0.0
            self._conv.set_state(FaceConvState.DONE)
            # Notify PE only if session still active (not already torn down by
            # PTT off or ACTION cancel, which emit conv_ended in _end_conversation)
            if self.world.session_id:
                asyncio.ensure_future(
                    self._workers.send_to(
                        "personality",
                        PERSONALITY_EVENT_CONV_ENDED,
                        {"session_id": self.world.session_id},
                    )
                )
            # If wake-word conversation, clean up session after response
            if self.world.conversation_trigger == "wake_word" and self.world.session_id:
                self._finish_session()

        # Guardrail events — session/daily time limits (PE spec S2 §9.3)
        elif env.type == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED:
            rule = str(env.payload.get("rule", ""))
            if rule == "session_time_limit" and self.world.session_id:
                # RS-1: end conversation with gentle redirect
                log.info("session time limit — ending conversation")
                asyncio.ensure_future(
                    self._enqueue_say(
                        "Hey, we've been chatting for a while! "
                        "Let's take a break and do something else for a bit.",
                        source="guardrail",
                        priority=1,
                    )
                )
                # Delay teardown to let the wind-down message play
                asyncio.ensure_future(self._delayed_end_conversation(4.0))
            elif rule in ("daily_time_limit", "daily_limit_blocked"):
                log.info("daily time limit — conversations blocked")

        # Personality LLM profile → enrich with turn context → forward to AI worker
        elif env.type == PERSONALITY_LLM_PROFILE:
            if self.world.session_id:
                profile = dict(env.payload)
                profile["turn_id"] = self.world.turn_id
                profile["session_id"] = self.world.session_id
                asyncio.ensure_future(
                    self._workers.send_to("ai", AI_CMD_SEND_PROFILE, profile)
                )

        # Memory extract from AI worker → forward to personality worker
        elif env.type == PERSONALITY_EVENT_MEMORY_EXTRACT:
            asyncio.ensure_future(
                self._workers.send_to(
                    "personality", PERSONALITY_EVENT_MEMORY_EXTRACT, env.payload
                )
            )

        # Ear worker events
        elif env.type == EAR_EVENT_WAKE_WORD:
            if not self.world.session_id and not self.world.speaking:
                self._start_conversation("wake_word")
                self._conv.set_state(FaceConvState.ATTENTION)

        elif env.type == EAR_EVENT_END_OF_UTTERANCE:
            if self.world.session_id and self.world.conversation_trigger == "wake_word":
                self._conv.set_state(FaceConvState.THINKING)
                # Signal end of speech, then wait for AI_CONVERSATION_DONE
                asyncio.ensure_future(
                    self._workers.send_to(
                        "ai",
                        AI_CMD_END_UTTERANCE,
                        {
                            "session_id": self.world.session_id,
                        },
                    )
                )
                asyncio.ensure_future(
                    self._workers.send_to("ear", EAR_CMD_STOP_LISTENING)
                )
                self.robot.face_listening = False

        # TTS events → conversation state transitions
        elif env.type == TTS_EVENT_STARTED:
            asyncio.ensure_future(self._workers.send_to("ear", EAR_CMD_PAUSE_VAD))
            asyncio.ensure_future(
                self._workers.send_to(
                    "personality",
                    PERSONALITY_EVENT_SPEECH_ACTIVITY,
                    {"speaking": True},
                )
            )
            if self._conv.session_active:
                self._conv.set_state(FaceConvState.SPEAKING)
                # Apply queued emotion now that we're speaking
                if self._queued_emotion:
                    self._conversation_emotion = self._queued_emotion
                    self._conversation_intensity = self._queued_intensity
                    self._queued_emotion = ""
                    self._queued_intensity = 0.0
        elif env.type in (TTS_EVENT_FINISHED, TTS_EVENT_CANCELLED):
            asyncio.ensure_future(self._workers.send_to("ear", EAR_CMD_RESUME_VAD))
            if env.type == TTS_EVENT_FINISHED:
                # Trail the talking animation to cover OS/hardware audio buffer drain.
                # CANCELLED stops immediately (user interrupted), so no grace needed.
                self._talking_grace_ticks = self._POST_TALKING_GRACE_TICKS
            if self._conv.session_active:
                if self.world.session_id:
                    # Multi-turn: return to LISTENING
                    self._conv.set_state(FaceConvState.LISTENING)
                else:
                    self._conv.set_state(FaceConvState.DONE)

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
            desired_param = 0
            if self.robot.mode == Mode.BOOT:
                desired_sys = int(FaceSystemMode.BOOTING)
            elif self.robot.mode == Mode.ERROR:
                desired_sys = int(FaceSystemMode.ERROR_DISPLAY)
            elif (
                self.robot.battery_mv > 0
                and self.robot.battery_mv < self._low_battery_mv
            ):
                desired_sys = int(FaceSystemMode.LOW_BATTERY)
                # Derive 0-255 battery fill level (2S LiPo: 6000mV empty, 8400mV full)
                fill = (self.robot.battery_mv - 6000) / (8400 - 6000)
                desired_param = max(0, min(255, int(fill * 255)))
            else:
                desired_sys = int(FaceSystemMode.NONE)
            if (
                desired_sys != self._last_face_system_mode
                or desired_param != self._last_face_system_param
            ):
                self._face.send_system_mode(desired_sys, desired_param)
                self._last_face_system_mode = desired_sys
                self._last_face_system_param = desired_param

        # Talking layer — driven by TTS energy with post-drain grace period.
        # Grace holds the animation alive for _POST_TALKING_GRACE_TICKS after
        # TTS_EVENT_FINISHED so it trails OS/hardware audio buffer drain.
        if self.world.speaking:
            self._face.send_talking(True, self.world.current_energy)
            self.robot.face_talking = True
            self.robot.face_talking_energy = self.world.current_energy
            self._talking_grace_ticks = 0
        elif self._talking_grace_ticks > 0:
            self._talking_grace_ticks -= 1
            self._face.send_talking(True, 0)
            self.robot.face_talking = True
            self.robot.face_talking_energy = 0
        elif self.robot.face_talking:
            self._face.send_talking(False, 0)
            self.robot.face_talking = False
            self.robot.face_talking_energy = 0

        # Skip auto-emotion when manual lock is on (dashboard control)
        if self.robot.face_manual_lock:
            self._conversation_gestures = []
            return

        # ── Conversation state effects ────────────────────────────
        conv_changed = self._conv.consume_changed()

        # Flag overrides on state transitions + send border state to MCU
        if conv_changed:
            flags = self._conv.get_flags()
            if flags != -1:
                self._face.send_flags(flags)
            self._face.send_conv_state(int(self._conv.state))
            self._conv_choreo.on_transition(self._conv.prev_state, self._conv.state)

        # Advance transition choreographer and dispatch actions
        choreo_actions = self._conv_choreo.update(self.robot.tick_dt_ms)
        choreo_mood_nudge: tuple[int, float] | None = None
        for action in choreo_actions:
            if action.kind == "gesture":
                gid = action.params.get("gesture_id")
                dur = action.params.get("duration_ms", 350)
                if isinstance(gid, int):
                    self._face.send_gesture(gid, int(dur))
            elif action.kind == "mood_nudge":
                choreo_mood_nudge = (
                    int(action.params["mood_id"]),
                    float(action.params["intensity"]),
                )

        # Gaze: choreographer ramp > conv_state override > default
        choreo_gaze = self._conv_choreo.get_gaze_override()
        if choreo_gaze is not None:
            scale = 127.0 / 32.0
            gaze: tuple[float, float] | None = (
                choreo_gaze[0] * scale,
                choreo_gaze[1] * scale,
            )
        else:
            gaze = self._conv.get_gaze_for_send()

        # Backchannel: NOD during LISTENING (skip if choreographer active)
        if self._conv.consume_nod() and not self._conv_choreo.active:
            nod_id = GESTURE_TO_FACE_ID.get("nod")
            if nod_id is not None:
                self._face.send_gesture(nod_id, 350)

        # ── Mood pipeline: determine → guardrail → sequence → send ────

        dt_s = self.robot.tick_dt_ms / 1000.0

        if not self._conv_choreo.suppress_mood_pipeline:
            # Step 1: Determine target mood.

            # Conversation phase clamping (face comm S2 §2.3; alignment §4.5):
            # During LISTENING/PTT force NEUTRAL@0.3, THINKING force THINKING@0.5.
            # This overrides PE snapshot and AI emotion — the face must reflect
            # the deterministic conversation phase, not the robot's affect.
            conv_clamp = self._conv.get_mood_hint()

            if conv_clamp is not None:
                target_mood, target_intensity = conv_clamp
            else:
                # Normal mood pipeline: PE snapshot (primary) or fallback.
                pe_age_ms = now_ms - self.world.personality_snapshot_ts_ms
                pe_fresh = (
                    self.world.personality_snapshot_ts_ms > 0
                    and pe_age_ms < _PE_STALE_MS
                )

                if pe_fresh:
                    # PRIMARY: read mood from personality worker snapshot
                    pe_norm = normalize_emotion_name(self.world.personality_mood)
                    target_mood = EMOTION_TO_FACE_MOOD.get(pe_norm or "", 0)
                    target_intensity = self.world.personality_intensity
                    # PE worker already enforced guardrails — skip tick-loop check
                else:
                    # FALLBACK: existing behavior (AI emotion > mood hint > NEUTRAL)
                    target_mood = 0  # FaceMood.NEUTRAL
                    target_intensity = 1.0
                    if self._conversation_emotion:
                        norm = normalize_emotion_name(self._conversation_emotion)
                        if norm:
                            resolved = EMOTION_TO_FACE_MOOD.get(norm)
                            if resolved is not None:
                                target_mood = resolved
                                target_intensity = self._conversation_intensity

                    # Apply tick-loop guardrails ONLY in fallback path
                    now_s = now_ms / 1000.0
                    target_mood, target_intensity = self._guardrails.check(
                        target_mood,
                        target_intensity,
                        conversation_active=self._conv.session_active,
                        now=now_s,
                    )

            # Step 3: Feed to mood sequencer
            self._mood_seq.request_mood(target_mood, target_intensity)
        else:
            # Choreographer suppressing mood pipeline — process mood nudge only
            if choreo_mood_nudge is not None:
                self._mood_seq.request_mood(*choreo_mood_nudge)

        # Step 4: Advance sequencer (always, even when suppressed)
        self._mood_seq.update(dt_s)

        # Step 5: Trigger BLINK gesture if sequencer requests it
        # (suppress if choreographer already fired a blink this transition)
        if self._mood_seq.consume_blink():
            if not self._conv_choreo.has_blink:
                blink_id = GESTURE_TO_FACE_ID.get("blink")
                if blink_id is not None:
                    self._face.send_gesture(blink_id, 180)

        # Step 6: Populate telemetry
        self.robot.face_seq_phase = int(self._mood_seq.phase)
        self.robot.face_seq_mood_id = self._mood_seq.mood_id
        self.robot.face_seq_intensity = self._mood_seq.intensity
        self.robot.face_choreo_active = self._conv_choreo.active

        # Step 7: Send SET_STATE when mood/intensity is changing
        if self._mood_seq.transitioning or self._mood_seq.consume_changed():
            gx = gaze[0] if gaze is not None else 0.0
            gy = gaze[1] if gaze is not None else 0.0
            self._face.send_state(
                self._mood_seq.mood_id,
                self._mood_seq.intensity,
                gaze_x=gx,
                gaze_y=gy,
            )
        elif gaze is not None:
            # No mood change but gaze override active (or choreographer ramping)
            self._face.send_state(
                self._mood_seq.mood_id,
                self._mood_seq.intensity,
                gaze_x=gaze[0],
                gaze_y=gaze[1],
            )

        # Gestures from AI worker
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
                "emotion": self.world.personality_mood,
                "source": source,
                "priority": priority,
            },
        )
        if sent:
            self.world.say_enqueued += 1
            self.world.speech_source = source
            self.world.speech_priority = priority

    def _apply_emote(self, action: dict) -> None:
        """Route planner emote action through PE as impulse (face comm S2 Layer 3).

        Face mood must come from PE snapshot, not bypass it directly.
        """
        name = normalize_emotion_name(str(action.get("name", "")))
        if not name:
            return
        intensity = float(action.get("intensity", 0.7))
        asyncio.ensure_future(
            self._workers.send_to(
                "personality",
                PERSONALITY_EVENT_AI_EMOTION,
                {"emotion": name, "intensity": intensity},
            )
        )

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

    def _start_conversation(self, trigger: str = "ptt") -> None:
        """Start a conversation (PTT button or wake word)."""
        if not self.world.both_audio_links_up:
            log.warning("cannot start conversation: audio links not up")
            return

        # Prevent double-start
        if self.world.session_id:
            return

        # RS-2: block new conversations when daily time limit reached
        if self.world.personality_daily_limit_reached:
            log.info("conversation blocked: daily time limit reached")
            return

        import uuid

        self.world.session_id = f"sess-{uuid.uuid4().hex[:12]}"
        self.world.turn_id = 1
        self.world.conversation_trigger = trigger

        # Notify dashboard conversation capture
        if self._conv_capture is not None:
            self._conv_capture.capture_event(
                CONV_SESSION_STARTED,
                {"session_id": self.world.session_id, "trigger": trigger},
            )

        # Tell AI worker to open WebSocket
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

        # Tell ear worker to start forwarding mic audio + VAD
        asyncio.ensure_future(self._workers.send_to("ear", EAR_CMD_START_LISTENING))

        # Notify personality worker
        asyncio.ensure_future(
            self._workers.send_to(
                "personality",
                PERSONALITY_EVENT_CONV_STARTED,
                {"session_id": self.world.session_id, "trigger": trigger},
            )
        )

        # Play acknowledgment chime for wake word
        if trigger == "wake_word":
            asyncio.ensure_future(
                self._workers.send_to("tts", TTS_CMD_PLAY_CHIME, {"chime": "listening"})
            )

        self.robot.face_listening = True

    def _end_conversation(self) -> None:
        """End a conversation (PTT off, ACTION cancel, or error teardown)."""
        # Notify PE immediately so affect recovery starts without waiting
        # for AI_CONVERSATION_DONE (which may be delayed or never arrive).
        if self.world.session_id:
            asyncio.ensure_future(
                self._workers.send_to(
                    "personality",
                    PERSONALITY_EVENT_CONV_ENDED,
                    {"session_id": self.world.session_id},
                )
            )
        asyncio.ensure_future(self._workers.send_to("ear", EAR_CMD_STOP_LISTENING))
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
        self._finish_session()

    async def _delayed_end_conversation(self, delay_s: float) -> None:
        """End conversation after a delay (allows wind-down speech to play)."""
        await asyncio.sleep(delay_s)
        if self.world.session_id:
            from supervisor.devices.protocol import FaceConvState

            self._conv.set_state(FaceConvState.DONE)
            self._end_conversation()

    def _finish_session(self) -> None:
        """Clean up conversation state (shared by PTT and wake word paths)."""
        if self._conv_capture is not None and self.world.session_id:
            self._conv_capture.capture_event(
                CONV_SESSION_ENDED,
                {"session_id": self.world.session_id},
            )
        self.world.session_id = ""
        self.world.turn_id = 0
        self.world.conversation_trigger = ""

    async def _request_plan(self, now_ms: float) -> None:
        """Send plan request to AI worker."""
        from supervisor.messages.types import AI_CMD_REQUEST_PLAN

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
