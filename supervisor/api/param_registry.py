"""Parameter registry — central store for all tunable robot parameters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ParamDef:
    name: str
    type: str  # "float", "int", "bool"
    min: float | None = None
    max: float | None = None
    step: float | None = None
    default: Any = None
    value: Any = None
    owner: str = "supervisor"  # "reflex", "face", "supervisor"
    mutable: str = "runtime"  # "runtime", "boot_only"
    safety: str = "safe"  # "safe", "risky"
    doc: str = ""

    def validate(self, val: Any) -> tuple[bool, str]:
        if self.mutable == "boot_only":
            return False, f"{self.name} is boot_only"
        if self.type == "int":
            if not isinstance(val, int):
                return False, f"{self.name} must be int"
        elif self.type == "float":
            if not isinstance(val, (int, float)):
                return False, f"{self.name} must be numeric"
            val = float(val)
        elif self.type == "bool":
            if not isinstance(val, bool):
                return False, f"{self.name} must be bool"
        if self.min is not None and val < self.min:
            return False, f"{self.name} below min ({self.min})"
        if self.max is not None and val > self.max:
            return False, f"{self.name} above max ({self.max})"
        return True, "ok"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "default": self.default,
            "value": self.value,
            "owner": self.owner,
            "mutable": self.mutable,
            "safety": self.safety,
            "doc": self.doc,
        }


class ParamRegistry:
    """Thread-safe parameter store with validation and transactional updates."""

    def __init__(self) -> None:
        self._params: dict[str, ParamDef] = {}
        self._on_change: list[Callable[[str, Any], None]] = []

    def on_change(self, cb: Callable[[str, Any], None]) -> None:
        """Register a callback invoked after any param value changes."""
        self._on_change.append(cb)

    def register(self, p: ParamDef) -> None:
        if p.value is None:
            p.value = p.default
        self._params[p.name] = p

    def get(self, name: str) -> ParamDef | None:
        return self._params.get(name)

    def get_value(self, name: str, default: Any = None) -> Any:
        p = self._params.get(name)
        return p.value if p else default

    def get_all(self) -> list[dict]:
        return [p.to_dict() for p in self._params.values()]

    def set(self, name: str, value: Any) -> tuple[bool, str]:
        p = self._params.get(name)
        if not p:
            return False, f"unknown param: {name}"
        ok, reason = p.validate(value)
        if not ok:
            return False, reason
        p.value = value
        log.info("param: %s = %s", name, value)
        for cb in self._on_change:
            cb(name, value)
        return True, "ok"

    def bulk_set(self, updates: dict[str, Any]) -> dict[str, tuple[bool, str]]:
        """Transactional bulk update: validate all first, then apply."""
        results: dict[str, tuple[bool, str]] = {}

        # Validate all
        for name, value in updates.items():
            p = self._params.get(name)
            if not p:
                results[name] = (False, f"unknown param: {name}")
                continue
            ok, reason = p.validate(value)
            results[name] = (ok, reason)

        # If any failed, return without applying
        if any(not ok for ok, _ in results.values()):
            return results

        # All valid — apply
        for name, value in updates.items():
            self._params[name].value = value
            log.info("param: %s = %s", name, value)
            for cb in self._on_change:
                cb(name, value)

        return results


def create_default_registry() -> ParamRegistry:
    """Create registry pre-populated with known parameters."""
    reg = ParamRegistry()

    # -- Supervisor parameters (runtime-tunable) --
    reg.register(
        ParamDef(
            name="telemetry_hz",
            type="int",
            min=1,
            max=50,
            step=1,
            default=20,
            owner="supervisor",
            doc="Telemetry broadcast rate",
        )
    )
    reg.register(
        ParamDef(
            name="speed_cap_close_scale",
            type="float",
            min=0.0,
            max=1.0,
            step=0.05,
            default=0.25,
            owner="supervisor",
            doc="Speed scale when range < 300mm",
        )
    )
    reg.register(
        ParamDef(
            name="speed_cap_medium_scale",
            type="float",
            min=0.0,
            max=1.0,
            step=0.05,
            default=0.50,
            owner="supervisor",
            doc="Speed scale when range < 500mm",
        )
    )
    reg.register(
        ParamDef(
            name="speed_cap_stale_scale",
            type="float",
            min=0.0,
            max=1.0,
            step=0.05,
            default=0.50,
            owner="supervisor",
            doc="Speed scale when range sensor stale",
        )
    )

    # -- Reflex parameters --
    # boot_only: require reboot to change (kinematics, HW config)
    # runtime:   can be changed live via SET_CONFIG protocol

    # Kinematics (boot_only)
    reg.register(
        ParamDef(
            name="reflex.wheelbase_mm",
            type="float",
            min=1,
            max=1000,
            step=1,
            default=150.0,
            owner="reflex",
            mutable="boot_only",
            doc="Wheelbase between wheel centers",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.wheel_diameter_mm",
            type="float",
            min=1,
            max=500,
            step=1,
            default=65.0,
            owner="reflex",
            mutable="boot_only",
            doc="Wheel diameter",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.counts_per_rev",
            type="int",
            min=1,
            max=10000,
            step=1,
            default=1440,
            owner="reflex",
            mutable="boot_only",
            doc="Encoder counts per wheel revolution (post-gearbox)",
        )
    )

    # Control loop (boot_only)
    reg.register(
        ParamDef(
            name="reflex.control_hz",
            type="int",
            min=1,
            max=1000,
            step=1,
            default=100,
            owner="reflex",
            mutable="boot_only",
            doc="Control loop frequency",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.pwm_freq_hz",
            type="int",
            min=1000,
            max=40000,
            step=1000,
            default=20000,
            owner="reflex",
            mutable="boot_only",
            doc="LEDC PWM frequency",
        )
    )

    # FF + PI motor control gains (runtime-tunable via SET_CONFIG)
    reg.register(
        ParamDef(
            name="reflex.kV",
            type="float",
            min=0.0,
            max=10.0,
            step=0.1,
            default=1.0,
            owner="reflex",
            doc="Feedforward velocity gain (duty per mm/s)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.kS",
            type="float",
            min=0.0,
            max=500.0,
            step=1.0,
            default=0.0,
            owner="reflex",
            doc="Feedforward static friction offset (duty units)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.Kp",
            type="float",
            min=0.0,
            max=50.0,
            step=0.1,
            default=2.0,
            owner="reflex",
            doc="Proportional gain (speed error correction)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.Ki",
            type="float",
            min=0.0,
            max=50.0,
            step=0.1,
            default=0.5,
            owner="reflex",
            doc="Integral gain (steady-state error correction)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.min_pwm",
            type="int",
            min=0,
            max=500,
            step=1,
            default=80,
            owner="reflex",
            doc="Deadband / stiction compensation (duty units)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.max_pwm",
            type="int",
            min=0,
            max=1023,
            step=1,
            default=1023,
            owner="reflex",
            doc="Max PWM duty (10-bit resolution)",
        )
    )

    # Rate limits (runtime-tunable via SET_CONFIG)
    reg.register(
        ParamDef(
            name="reflex.max_v_mm_s",
            type="int",
            min=0,
            max=2000,
            step=10,
            default=500,
            owner="reflex",
            doc="Max linear velocity",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.max_a_mm_s2",
            type="int",
            min=0,
            max=5000,
            step=50,
            default=1000,
            owner="reflex",
            doc="Max linear acceleration",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.max_w_mrad_s",
            type="int",
            min=0,
            max=10000,
            step=100,
            default=2000,
            owner="reflex",
            doc="Max angular velocity (~115 deg/s)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.max_aw_mrad_s2",
            type="int",
            min=0,
            max=20000,
            step=100,
            default=4000,
            owner="reflex",
            doc="Max angular acceleration",
        )
    )

    # Yaw damping (runtime-tunable via SET_CONFIG)
    reg.register(
        ParamDef(
            name="reflex.K_yaw",
            type="float",
            min=0.0,
            max=5.0,
            step=0.01,
            default=0.1,
            owner="reflex",
            doc="Gyro yaw correction gain",
        )
    )

    # Safety (runtime-tunable via SET_CONFIG)
    reg.register(
        ParamDef(
            name="reflex.cmd_timeout_ms",
            type="int",
            min=50,
            max=5000,
            step=50,
            default=400,
            owner="reflex",
            doc="Command watchdog timeout",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.soft_stop_ramp_ms",
            type="int",
            min=50,
            max=5000,
            step=50,
            default=500,
            owner="reflex",
            doc="Ramp-to-zero duration on soft stop",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.tilt_thresh_deg",
            type="float",
            min=5.0,
            max=90.0,
            step=1.0,
            default=45.0,
            owner="reflex",
            doc="Tilt angle threshold for TILT fault",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.tilt_hold_ms",
            type="int",
            min=10,
            max=5000,
            step=10,
            default=200,
            owner="reflex",
            doc="Tilt must persist this long before fault",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.stall_thresh_ms",
            type="int",
            min=50,
            max=5000,
            step=50,
            default=500,
            owner="reflex",
            doc="Stall detection window duration",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.stall_speed_thresh",
            type="int",
            min=0,
            max=200,
            step=1,
            default=20,
            owner="reflex",
            doc="Speed below this = stalled (mm/s)",
        )
    )

    # Range sensor (runtime-tunable distances, boot_only for HW config)
    reg.register(
        ParamDef(
            name="reflex.range_stop_mm",
            type="int",
            min=50,
            max=2000,
            step=10,
            default=250,
            owner="reflex",
            doc="Hard stop distance (obstacle)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.range_release_mm",
            type="int",
            min=50,
            max=2000,
            step=10,
            default=350,
            owner="reflex",
            doc="Release hysteresis distance",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.range_timeout_us",
            type="int",
            min=1000,
            max=100000,
            step=1000,
            default=25000,
            owner="reflex",
            mutable="boot_only",
            doc="Max echo wait (~4.3m max range)",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.range_hz",
            type="int",
            min=1,
            max=100,
            step=1,
            default=20,
            owner="reflex",
            mutable="boot_only",
            doc="Ultrasonic measurement rate",
        )
    )

    # -- IMU parameters (boot_only — require MCU reboot to take effect) --
    reg.register(
        ParamDef(
            name="reflex.imu_odr_hz",
            type="int",
            min=25,
            max=1600,
            step=1,
            default=400,
            owner="reflex",
            mutable="boot_only",
            doc="IMU output data rate (Hz). Valid: 25, 50, 100, 200, 400, 800, 1600",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.imu_gyro_range_dps",
            type="int",
            min=125,
            max=2000,
            step=1,
            default=500,
            owner="reflex",
            mutable="boot_only",
            doc="Gyroscope full-scale range (dps). Valid: 125, 250, 500, 1000, 2000",
        )
    )
    reg.register(
        ParamDef(
            name="reflex.imu_accel_range_g",
            type="int",
            min=2,
            max=16,
            step=1,
            default=2,
            owner="reflex",
            mutable="boot_only",
            doc="Accelerometer full-scale range (g). Valid: 2, 4, 8, 16",
        )
    )

    # -- Vision parameters (runtime-tunable, applied live to vision worker) --

    # Camera / ISP settings (Picamera2/libcamera)
    reg.register(
        ParamDef(
            name="vision.rotate_deg",
            type="int",
            min=0,
            max=270,
            step=90,
            default=180,
            owner="vision",
            doc="Rotate captured frames before CV/video (0/90/180/270)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.hfov_deg",
            type="float",
            min=30.0,
            max=120.0,
            step=1.0,
            default=66.0,
            owner="vision",
            doc="Horizontal field of view (deg) used for ball bearing estimation",
        )
    )
    reg.register(
        ParamDef(
            name="vision.af_mode",
            type="int",
            min=0,
            max=2,
            step=1,
            default=2,
            owner="vision",
            doc="Autofocus mode: 0=manual, 1=auto, 2=continuous",
        )
    )
    reg.register(
        ParamDef(
            name="vision.lens_position",
            type="float",
            min=0.0,
            max=10.0,
            step=0.1,
            default=1.0,
            owner="vision",
            doc="Manual focus lens position (only when af_mode=0)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.ae_enable",
            type="int",
            min=0,
            max=1,
            step=1,
            default=1,
            owner="vision",
            doc="Auto exposure enable: 0=manual, 1=auto",
        )
    )
    reg.register(
        ParamDef(
            name="vision.exposure_time_us",
            type="int",
            min=100,
            max=1_000_000,
            step=100,
            default=10_000,
            owner="vision",
            doc="Manual exposure time (us) when ae_enable=0",
        )
    )
    reg.register(
        ParamDef(
            name="vision.analogue_gain",
            type="float",
            min=1.0,
            max=16.0,
            step=0.1,
            default=1.0,
            owner="vision",
            doc="Manual analogue gain when ae_enable=0",
        )
    )
    reg.register(
        ParamDef(
            name="vision.awb_enable",
            type="int",
            min=0,
            max=1,
            step=1,
            default=1,
            owner="vision",
            doc="Auto white balance enable: 0=manual, 1=auto",
        )
    )
    reg.register(
        ParamDef(
            name="vision.colour_gain_r",
            type="float",
            min=0.1,
            max=8.0,
            step=0.1,
            default=1.0,
            owner="vision",
            doc="Manual white balance red gain when awb_enable=0",
        )
    )
    reg.register(
        ParamDef(
            name="vision.colour_gain_b",
            type="float",
            min=0.1,
            max=8.0,
            step=0.1,
            default=1.0,
            owner="vision",
            doc="Manual white balance blue gain when awb_enable=0",
        )
    )
    reg.register(
        ParamDef(
            name="vision.brightness",
            type="float",
            min=-1.0,
            max=1.0,
            step=0.05,
            default=0.0,
            owner="vision",
            doc="Image brightness (libcamera control)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.contrast",
            type="float",
            min=0.0,
            max=2.0,
            step=0.05,
            default=1.0,
            owner="vision",
            doc="Image contrast (libcamera control)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.saturation",
            type="float",
            min=0.0,
            max=2.0,
            step=0.05,
            default=1.0,
            owner="vision",
            doc="Image saturation (libcamera control)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.sharpness",
            type="float",
            min=0.0,
            max=2.0,
            step=0.05,
            default=1.0,
            owner="vision",
            doc="Image sharpness (libcamera control)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.jpeg_quality",
            type="int",
            min=10,
            max=95,
            step=1,
            default=50,
            owner="vision",
            doc="MJPEG /video JPEG quality (10-95)",
        )
    )

    # Floor HSV thresholds — tune these to match your actual floor color.
    # Use a colour-picker on a /video frame to find the right HSV range.
    reg.register(
        ParamDef(
            name="vision.floor_hsv_h_low",
            type="int",
            min=0,
            max=180,
            step=1,
            default=0,
            owner="vision",
            doc="Floor HSV hue lower bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.floor_hsv_h_high",
            type="int",
            min=0,
            max=180,
            step=1,
            default=180,
            owner="vision",
            doc="Floor HSV hue upper bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.floor_hsv_s_low",
            type="int",
            min=0,
            max=255,
            step=1,
            default=0,
            owner="vision",
            doc="Floor HSV saturation lower bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.floor_hsv_s_high",
            type="int",
            min=0,
            max=255,
            step=1,
            default=80,
            owner="vision",
            doc="Floor HSV saturation upper bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.floor_hsv_v_low",
            type="int",
            min=0,
            max=255,
            step=1,
            default=50,
            owner="vision",
            doc="Floor HSV value lower bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.floor_hsv_v_high",
            type="int",
            min=0,
            max=255,
            step=1,
            default=220,
            owner="vision",
            doc="Floor HSV value upper bound",
        )
    )

    # Ball HSV thresholds — defaults target a red ball (hue wraps 0/180).
    reg.register(
        ParamDef(
            name="vision.ball_hsv_h_low",
            type="int",
            min=0,
            max=180,
            step=1,
            default=170,
            owner="vision",
            doc="Ball HSV hue lower bound (wrap-around allowed: low > high)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.ball_hsv_h_high",
            type="int",
            min=0,
            max=180,
            step=1,
            default=15,
            owner="vision",
            doc="Ball HSV hue upper bound (wrap-around allowed: low > high)",
        )
    )
    reg.register(
        ParamDef(
            name="vision.ball_hsv_s_low",
            type="int",
            min=0,
            max=255,
            step=1,
            default=80,
            owner="vision",
            doc="Ball HSV saturation lower bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.ball_hsv_s_high",
            type="int",
            min=0,
            max=255,
            step=1,
            default=255,
            owner="vision",
            doc="Ball HSV saturation upper bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.ball_hsv_v_low",
            type="int",
            min=0,
            max=255,
            step=1,
            default=40,
            owner="vision",
            doc="Ball HSV value lower bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.ball_hsv_v_high",
            type="int",
            min=0,
            max=255,
            step=1,
            default=255,
            owner="vision",
            doc="Ball HSV value upper bound",
        )
    )
    reg.register(
        ParamDef(
            name="vision.min_ball_radius_px",
            type="int",
            min=1,
            max=100,
            step=1,
            default=8,
            owner="vision",
            doc="Minimum ball contour radius in pixels",
        )
    )

    # Vision safety thresholds — control how clear_confidence caps speed.
    reg.register(
        ParamDef(
            name="vision.stale_ms",
            type="float",
            min=100.0,
            max=2000.0,
            step=50.0,
            default=500.0,
            owner="vision",
            doc="Vision age (ms) above which stale speed cap applies",
        )
    )
    reg.register(
        ParamDef(
            name="vision.clear_low",
            type="float",
            min=0.01,
            max=1.0,
            step=0.01,
            default=0.3,
            owner="vision",
            doc="clear_conf below this → 25%% speed cap",
        )
    )
    reg.register(
        ParamDef(
            name="vision.clear_high",
            type="float",
            min=0.01,
            max=1.0,
            step=0.01,
            default=0.6,
            owner="vision",
            doc="clear_conf below this → 50%% speed cap",
        )
    )

    return reg
