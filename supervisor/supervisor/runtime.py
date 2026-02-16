"""Main runtime tick loop — 50 Hz control, 20 Hz telemetry broadcast."""

from __future__ import annotations

import asyncio
import logging
import time

from supervisor.devices.face_client import FaceClient
from supervisor.devices.personality_client import (
    PersonalityClient,
    PersonalityError,
    PersonalityPlan,
)
from supervisor.devices.protocol import FaceGesture, FaceMood, FaceSystemMode, Fault
from supervisor.devices.reflex_client import ReflexClient
from supervisor.inputs.camera_vision import VisionProcess
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

_EMOTE_TO_MOOD = {
    "neutral": int(FaceMood.DEFAULT),
    "curious": int(FaceMood.DEFAULT),
    "happy": int(FaceMood.HAPPY),
    "excited": int(FaceMood.HAPPY),
    "love": int(FaceMood.HAPPY),
    "surprised": int(FaceMood.HAPPY),
    "sad": int(FaceMood.TIRED),
    "sleepy": int(FaceMood.TIRED),
    "tired": int(FaceMood.TIRED),
    "scared": int(FaceMood.ANGRY),
    "angry": int(FaceMood.ANGRY),
}

_GESTURE_TO_ID = {
    "blink": int(FaceGesture.BLINK),
    "wink_l": int(FaceGesture.WINK_L),
    "wink_r": int(FaceGesture.WINK_R),
    "confused": int(FaceGesture.CONFUSED),
    "laugh": int(FaceGesture.LAUGH),
    "surprise": int(FaceGesture.SURPRISE),
    "heart": int(FaceGesture.HEART),
    "x_eyes": int(FaceGesture.X_EYES),
    "sleepy": int(FaceGesture.SLEEPY),
    "rage": int(FaceGesture.RAGE),
}


class Runtime:
    """Orchestrates the 50 Hz control loop."""

    def __init__(
        self,
        reflex: ReflexClient,
        on_telemetry: callable | None = None,
        vision: VisionProcess | None = None,
        face: FaceClient | None = None,
        personality: PersonalityClient | None = None,
    ) -> None:
        self._reflex = reflex
        self._face = face
        self._vision = vision
        self._personality = personality
        self._sm = SupervisorSM()
        self._state = RobotState()
        self._teleop_twist = DesiredTwist()
        self._on_telemetry = on_telemetry
        self._running = False
        self._tick_count = 0
        self._last_tick_mono = 0.0
        self._personality_task: asyncio.Task[PersonalityPlan] | None = None
        self._next_plan_mono = 0.0

        if personality:
            self._state.personality_enabled = True

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
            self._step_personality(t0)

            elapsed = time.monotonic() - t0
            sleep_s = max(0.0, TICK_PERIOD_S - elapsed)
            await asyncio.sleep(sleep_s)

    def stop(self) -> None:
        self._running = False
        if self._personality_task and not self._personality_task.done():
            self._personality_task.cancel()

    def request_mode(self, target: Mode) -> tuple[bool, str]:
        return self._sm.request_mode(
            target, self._reflex.connected, self._state.fault_flags
        )

    def request_estop(self) -> None:
        self._reflex.send_estop()

    def request_clear(self) -> tuple[bool, str]:
        self._reflex.send_clear_faults()
        return self._sm.clear_error(self._reflex.connected, self._state.fault_flags)

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
            ft = self._face.telemetry
            s.face_mood = ft.mood_id
            s.face_gesture = ft.active_gesture
            s.face_system_mode = ft.system_mode
            s.face_touch_active = ft.touch_active

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

        # 2. Update state machine
        s.mode = self._sm.update(s.reflex_connected, s.fault_flags)

        # 3. Get desired twist from active input
        if s.mode == Mode.TELEOP:
            s.twist_cmd = DesiredTwist(
                self._teleop_twist.v_mm_s, self._teleop_twist.w_mrad_s
            )
        elif s.mode == Mode.WANDER:
            # TODO: wander behavior
            s.twist_cmd = DesiredTwist(0, 0)
        else:
            s.twist_cmd = DesiredTwist(0, 0)

        # 4. Apply safety policy
        s.twist_capped = apply_safety(s.twist_cmd, s)

        # 5. Send to reflex
        if s.reflex_connected:
            if s.twist_capped.v_mm_s == 0 and s.twist_capped.w_mrad_s == 0:
                # Still send zero twist to reset command watchdog
                self._reflex.send_twist(0, 0)
            else:
                self._reflex.send_twist(s.twist_capped.v_mm_s, s.twist_capped.w_mrad_s)

        # 6. Push system mode to face
        if self._face and self._face.connected:
            if s.mode == Mode.BOOT:
                self._face.send_system_mode(FaceSystemMode.BOOTING)
            elif s.mode == Mode.ERROR:
                self._face.send_system_mode(FaceSystemMode.ERROR_DISPLAY)
            else:
                self._face.send_system_mode(FaceSystemMode.NONE)

        # 7. Broadcast telemetry at decimated rate
        self._tick_count += 1
        if self._on_telemetry and (self._tick_count % _TELEM_EVERY_N == 0):
            self._on_telemetry(s)

    def _step_personality(self, t0: float) -> None:
        if not self._personality:
            return

        s = self._state

        if self._personality_task and self._personality_task.done():
            try:
                plan = self._personality_task.result()
                s.personality_connected = True
                s.personality_last_error = ""
                self._apply_personality_plan(plan)
                self._next_plan_mono = t0 + _PLAN_PERIOD_S
            except asyncio.CancelledError:
                self._next_plan_mono = t0 + _PLAN_RETRY_S
            except PersonalityError as e:
                s.personality_connected = False
                s.personality_last_error = str(e)
                self._next_plan_mono = t0 + _PLAN_RETRY_S
                log.warning("personality: %s", e)
            except Exception as e:
                s.personality_connected = False
                s.personality_last_error = str(e)
                self._next_plan_mono = t0 + _PLAN_RETRY_S
                log.warning("personality: unexpected error: %s", e)
            finally:
                self._personality_task = None

        if self._personality_task is None and t0 >= self._next_plan_mono:
            world_state = self._build_world_state()
            self._personality_task = asyncio.create_task(
                self._personality.request_plan(world_state)
            )

    def _build_world_state(self) -> dict:
        s = self._state
        trigger = "ball_seen" if s.ball_confidence >= 0.7 else "heartbeat"
        return {
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

    def _apply_personality_plan(self, plan: PersonalityPlan) -> None:
        s = self._state
        s.personality_last_plan_mono_ms = time.monotonic() * 1000.0
        s.personality_last_plan_actions = len(plan.actions)

        if not self._face or not self._face.connected:
            return

        for action in plan.actions:
            action_type = action.get("action")

            if action_type == "emote":
                name = str(action.get("name", "")).lower()
                mood = _EMOTE_TO_MOOD.get(name)
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
                name = str(action.get("name", "")).lower()
                gesture_id = _GESTURE_TO_ID.get(name)
                if gesture_id is not None:
                    self._face.send_gesture(gesture_id)

            elif action_type == "say":
                text = action.get("text")
                if isinstance(text, str) and text:
                    log.info("personality say: %s", text[:120])
