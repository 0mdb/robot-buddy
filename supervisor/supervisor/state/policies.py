"""Safety policies applied to motion commands each tick.

Defense-in-depth above the reflex MCU's own safety (250mm hard stop, tilt, etc).
"""

from __future__ import annotations

from supervisor.devices.protocol import RangeStatus
from supervisor.state.datatypes import (
    DesiredTwist,
    MOTION_MODES,
    RobotState,
    SpeedCap,
)


def apply_safety(desired: DesiredTwist, state: RobotState) -> DesiredTwist:
    """Apply safety policy to desired twist, returning capped twist.

    Also populates state.speed_caps with reasons for any limiting.
    """
    state.speed_caps.clear()
    v = desired.v_mm_s
    w = desired.w_mrad_s

    # 1. Mode gate — no motion outside motion modes
    if state.mode not in MOTION_MODES:
        state.speed_caps.append(SpeedCap(0.0, f"mode={state.mode.value}"))
        return DesiredTwist(0, 0)

    # 2. Fault gate — zero on any active fault
    if state.any_fault:
        state.speed_caps.append(SpeedCap(0.0, f"fault=0x{state.fault_flags:04X}"))
        return DesiredTwist(0, 0)

    # 3. Reflex not connected
    if not state.reflex_connected:
        state.speed_caps.append(SpeedCap(0.0, "reflex_disconnected"))
        return DesiredTwist(0, 0)

    # 4. Ultrasonic speed governor (defense-in-depth above reflex's 250mm stop)
    if state.range_status == RangeStatus.OK and state.range_mm > 0:
        if state.range_mm < 300:
            scale = 0.25
            state.speed_caps.append(SpeedCap(scale, f"range={state.range_mm}mm<300"))
            v = int(v * scale)
            w = int(w * scale)
        elif state.range_mm < 500:
            scale = 0.50
            state.speed_caps.append(SpeedCap(scale, f"range={state.range_mm}mm<500"))
            v = int(v * scale)
            w = int(w * scale)

    # 5. Stale range — if NOT_READY or TIMEOUT, be conservative
    if state.range_status in (RangeStatus.TIMEOUT, RangeStatus.NOT_READY):
        scale = 0.50
        state.speed_caps.append(SpeedCap(scale, f"range_stale={state.range_status}"))
        v = int(v * scale)
        w = int(w * scale)

    # 6. Vision clear-path confidence scaling
    _VISION_STALE_MS = 500.0
    if state.clear_confidence >= 0:
        if state.vision_age_ms > _VISION_STALE_MS or state.vision_age_ms < 0:
            scale = 0.50
            state.speed_caps.append(SpeedCap(scale, "vision_stale"))
            v = int(v * scale)
            w = int(w * scale)
        elif state.clear_confidence < 0.3:
            scale = 0.25
            state.speed_caps.append(
                SpeedCap(scale, f"clear_conf={state.clear_confidence:.2f}<0.3")
            )
            v = int(v * scale)
            w = int(w * scale)
        elif state.clear_confidence < 0.6:
            scale = 0.50
            state.speed_caps.append(
                SpeedCap(scale, f"clear_conf={state.clear_confidence:.2f}<0.6")
            )
            v = int(v * scale)
            w = int(w * scale)

    return DesiredTwist(v, w)
