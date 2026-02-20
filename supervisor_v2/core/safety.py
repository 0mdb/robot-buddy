"""Safety policies applied to motion commands each tick.

Defense-in-depth above the reflex MCU's own safety (250mm hard stop, tilt, etc).

Adapted from v1: receives both RobotState and WorldState.
Vision fields now come from WorldState.
"""

from __future__ import annotations

from supervisor_v2.devices.protocol import RangeStatus
from supervisor_v2.core.state import (
    DesiredTwist,
    MOTION_MODES,
    RobotState,
    SpeedCap,
    WorldState,
)

# Vision safety thresholds — updated at runtime via configure_vision_policy().
_vision_stale_ms: float = 500.0
_vision_clear_low: float = 0.3
_vision_clear_high: float = 0.6


def configure_vision_policy(
    stale_ms: float, clear_low: float, clear_high: float
) -> None:
    """Update vision speed-cap thresholds (called when params change)."""
    global _vision_stale_ms, _vision_clear_low, _vision_clear_high
    _vision_stale_ms = stale_ms
    _vision_clear_low = clear_low
    _vision_clear_high = clear_high


def apply_safety(
    desired: DesiredTwist, robot: RobotState, world: WorldState
) -> DesiredTwist:
    """Apply safety policy to desired twist, returning capped twist.

    Also populates robot.speed_caps with reasons for any limiting.
    """
    robot.speed_caps.clear()
    v = desired.v_mm_s
    w = desired.w_mrad_s

    # 1. Mode gate — no motion outside motion modes
    if robot.mode not in MOTION_MODES:
        robot.speed_caps.append(SpeedCap(0.0, f"mode={robot.mode.value}"))
        return DesiredTwist(0, 0)

    # 2. Fault gate — zero on any active fault
    if robot.any_fault:
        robot.speed_caps.append(SpeedCap(0.0, f"fault=0x{robot.fault_flags:04X}"))
        return DesiredTwist(0, 0)

    # 3. Reflex not connected
    if not robot.reflex_connected:
        robot.speed_caps.append(SpeedCap(0.0, "reflex_disconnected"))
        return DesiredTwist(0, 0)

    # 4. Ultrasonic speed governor (defense-in-depth above reflex's 250mm stop)
    if robot.range_status == RangeStatus.OK and robot.range_mm > 0:
        if robot.range_mm < 300:
            scale = 0.25
            robot.speed_caps.append(SpeedCap(scale, f"range={robot.range_mm}mm<300"))
            v = int(v * scale)
            w = int(w * scale)
        elif robot.range_mm < 500:
            scale = 0.50
            robot.speed_caps.append(SpeedCap(scale, f"range={robot.range_mm}mm<500"))
            v = int(v * scale)
            w = int(w * scale)

    # 5. Stale range — if NOT_READY or TIMEOUT, be conservative
    if robot.range_status in (RangeStatus.TIMEOUT, RangeStatus.NOT_READY):
        scale = 0.50
        robot.speed_caps.append(SpeedCap(scale, f"range_stale={robot.range_status}"))
        v = int(v * scale)
        w = int(w * scale)

    # 6. Vision clear-path confidence scaling (vision fields from WorldState)
    if world.clear_confidence >= 0:
        vision_age = world.vision_age_ms
        if vision_age > _vision_stale_ms or vision_age < 0:
            scale = 0.50
            robot.speed_caps.append(SpeedCap(scale, "vision_stale"))
            v = int(v * scale)
            w = int(w * scale)
        elif world.clear_confidence < _vision_clear_low:
            scale = 0.25
            robot.speed_caps.append(
                SpeedCap(scale, f"clear_conf={world.clear_confidence:.2f}<{_vision_clear_low}")
            )
            v = int(v * scale)
            w = int(w * scale)
        elif world.clear_confidence < _vision_clear_high:
            scale = 0.50
            robot.speed_caps.append(
                SpeedCap(scale, f"clear_conf={world.clear_confidence:.2f}<{_vision_clear_high}")
            )
            v = int(v * scale)
            w = int(w * scale)

    return DesiredTwist(v, w)
