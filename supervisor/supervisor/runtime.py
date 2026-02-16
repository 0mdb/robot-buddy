"""Main runtime tick loop — 50 Hz control, 20 Hz telemetry broadcast."""

from __future__ import annotations

import asyncio
import logging
import time

from supervisor.devices.reflex_client import ReflexClient
from supervisor.inputs.camera_vision import VisionProcess
from supervisor.state.datatypes import DesiredTwist, Mode, RobotState
from supervisor.state.policies import SafetyConfig, apply_safety
from supervisor.state.supervisor_sm import SupervisorSM

log = logging.getLogger(__name__)

TICK_HZ = 50
TICK_PERIOD_S = 1.0 / TICK_HZ
TELEMETRY_HZ = 20
_TELEM_EVERY_N = TICK_HZ // TELEMETRY_HZ  # broadcast every N ticks

_JITTER_WARN_MS = 5.0


class Runtime:
    """Orchestrates the 50 Hz control loop."""

    def __init__(
        self,
        reflex: ReflexClient,
        on_telemetry: callable | None = None,
        vision: VisionProcess | None = None,
        param_registry: object | None = None,
    ) -> None:
        self._reflex = reflex
        self._vision = vision
        self._registry = param_registry
        self._sm = SupervisorSM()
        self._state = RobotState()
        self._teleop_twist = DesiredTwist()
        self._on_telemetry = on_telemetry
        self._running = False
        self._tick_count = 0
        self._last_tick_mono = 0.0

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

            elapsed = time.monotonic() - t0
            sleep_s = max(0.0, TICK_PERIOD_S - elapsed)
            await asyncio.sleep(sleep_s)

    def stop(self) -> None:
        self._running = False

    def request_mode(self, target: Mode) -> tuple[bool, str]:
        return self._sm.request_mode(
            target, self._reflex.connected, self._state.fault_flags
        )

    def request_estop(self) -> None:
        self._reflex.send_estop()

    def request_clear(self) -> tuple[bool, str]:
        self._reflex.send_clear_faults()
        return self._sm.clear_error(self._reflex.connected, self._state.fault_flags)

    def _build_safety_config(self) -> SafetyConfig | None:
        """Build SafetyConfig from param registry, or None to use defaults."""
        r = self._registry
        if r is None:
            return None
        return SafetyConfig(
            range_close_mm=r.get_value("speed_cap_close_mm", 300),
            range_medium_mm=r.get_value("speed_cap_medium_mm", 500),
            speed_cap_close_scale=r.get_value("speed_cap_close_scale", 0.25),
            speed_cap_medium_scale=r.get_value("speed_cap_medium_scale", 0.50),
            speed_cap_stale_scale=r.get_value("speed_cap_stale_scale", 0.50),
        )

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
        s.echo_us = tel.echo_us
        s.reflex_seq = tel.seq
        s.reflex_rx_mono_ms = tel.rx_mono_ms
        s.v_meas_mm_s = tel.v_meas_mm_s
        s.w_meas_mrad_s = tel.w_meas_mrad_s

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

        # 4. Apply safety policy (with live params from registry)
        safety_cfg = self._build_safety_config()
        s.twist_capped = apply_safety(s.twist_cmd, s, safety_cfg)

        # 5. Send to reflex
        if s.reflex_connected:
            if s.twist_capped.v_mm_s == 0 and s.twist_capped.w_mrad_s == 0:
                # Still send zero twist to reset command watchdog
                self._reflex.send_twist(0, 0)
            else:
                self._reflex.send_twist(s.twist_capped.v_mm_s, s.twist_capped.w_mrad_s)

        # 6. Broadcast telemetry at decimated rate
        self._tick_count += 1
        if self._on_telemetry and (self._tick_count % _TELEM_EVERY_N == 0):
            self._on_telemetry(s)
