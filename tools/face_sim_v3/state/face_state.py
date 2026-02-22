"""Face animation state machine — mirrors MCU face_state.cpp.

All constants imported from constants.py (no inline magic numbers).
Key V3 additions over V2:
- expression_intensity field for mood sequencer ramps
- Intensity blending for mood targets and emotion colors
- Per-gesture duration fields (MCU-accurate)
- active_gesture tracking
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from tools.face_sim_v3.state.constants import (
    BLINK_INTERVAL,
    BLINK_VARIATION,
    BREATH_AMOUNT,
    BREATH_SPEED,
    CONFUSED_MOUTH_CURVE,
    CONFUSED_OFFSET_AMP,
    CONFUSED_OFFSET_FREQ,
    FIRE_DRIFT,
    FIRE_HEAT_DECAY,
    FIRE_RISE_SPEED,
    FIRE_SPAWN_CHANCE,
    FLAG_AFTERGLOW,
    FLAG_AUTOBLINK,
    FLAG_EDGE_GLOW,
    FLAG_IDLE_WANDER,
    FLAG_SHOW_MOUTH,
    FLAG_SOLID_EYE,
    FLAG_SPARKLE,
    FLICKER_AMP,
    GESTURE_DURATIONS,
    GESTURE_COLOR_HEART,
    GESTURE_COLOR_RAGE,
    GESTURE_COLOR_X_EYES,
    HEART_MOUTH_CURVE,
    IDLE_GAZE_HOLD_MIN,
    IDLE_GAZE_HOLD_RANGE,
    LAUGH_CHATTER_AMP,
    LAUGH_CHATTER_BASE,
    LAUGH_CHATTER_FREQ,
    LEFT_EYE_CX,
    LEFT_EYE_CY,
    MAX_GAZE,
    MOOD_COLORS,
    MOOD_EYE_SCALE,
    MOOD_TARGETS,
    NEUTRAL_COLOR,
    NEUTRAL_LID_BOT,
    NEUTRAL_LID_SLOPE,
    NEUTRAL_LID_TOP,
    NEUTRAL_MOUTH_CURVE,
    NEUTRAL_MOUTH_OPEN,
    NEUTRAL_MOUTH_WIDTH,
    RAGE_LID_SLOPE,
    RAGE_MOUTH_CURVE,
    RAGE_MOUTH_OPEN,
    RAGE_MOUTH_WAVE,
    RAGE_SHAKE_AMP,
    RAGE_SHAKE_FREQ,
    RIGHT_EYE_CX,
    SACCADE_INTERVAL_MAX,
    SACCADE_INTERVAL_MIN,
    SACCADE_JITTER,
    SCREEN_H,
    SCREEN_W,
    SILLY_CROSS_EYE_A,
    SILLY_CROSS_EYE_B,
    SLEEPY_LID_SLOPE,
    SLEEPY_MOUTH_WIDTH,
    SLEEPY_SWAY_AMP,
    SLEEPY_SWAY_FREQ,
    SPARKLE_CHANCE,
    SPARKLE_LIFE_MAX,
    SPARKLE_LIFE_MIN,
    SPRING_D,
    SPRING_K,
    SURPRISE_PEAK_H,
    SURPRISE_PEAK_TIME,
    SURPRISE_PEAK_W,
    TALKING_BASE_OPEN,
    TALKING_BOUNCE_MOD,
    TALKING_OPEN_MOD,
    TALKING_PHASE_SPEED,
    TALKING_WIDTH_MOD,
    THINKING_GAZE_X,
    THINKING_GAZE_Y,
    THINKING_MOUTH_OFFSET_X,
    TWEEN_EYELID_BOT,
    TWEEN_EYELID_SLOPE,
    TWEEN_EYELID_TOP_CLOSING,
    TWEEN_EYELID_TOP_OPENING,
    TWEEN_EYE_SCALE,
    TWEEN_MOUTH_CURVE,
    TWEEN_MOUTH_OFFSET_X,
    TWEEN_MOUTH_OPEN,
    TWEEN_MOUTH_WAVE,
    TWEEN_MOUTH_WIDTH,
    TWEEN_OPENNESS,
    X_EYES_MOUTH_OPEN,
    X_EYES_MOUTH_WIDTH,
    GestureId,
    Mood,
    SystemMode,
)


# ── Dataclasses ──────────────────────────────────────────────────────


@dataclass
class EyeState:
    openness: float = 1.0
    openness_target: float = 1.0
    is_open: bool = True
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    gaze_x_target: float = 0.0
    gaze_y_target: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    width_scale: float = 1.0
    width_scale_target: float = 1.0
    height_scale: float = 1.0
    height_scale_target: float = 1.0


@dataclass
class EyelidState:
    top_l: float = 0.0
    top_r: float = 0.0
    bottom_l: float = 0.0
    bottom_r: float = 0.0
    slope: float = 0.0
    slope_target: float = 0.0


@dataclass
class AnimTimers:
    autoblink: bool = True
    next_blink: float = 0.0
    idle: bool = True
    next_idle: float = 0.0
    next_saccade: float = 0.0

    # Gesture active flags + timers + per-gesture durations (MCU-accurate)
    confused: bool = False
    confused_timer: float = 0.0
    confused_toggle: bool = True
    confused_duration: float = 0.50

    laugh: bool = False
    laugh_timer: float = 0.0
    laugh_toggle: bool = True
    laugh_duration: float = 0.50

    surprise: bool = False
    surprise_timer: float = 0.0
    surprise_duration: float = 0.80

    heart: bool = False
    heart_timer: float = 0.0
    heart_duration: float = 2.00

    x_eyes: bool = False
    x_eyes_timer: float = 0.0
    x_eyes_duration: float = 2.50

    sleepy: bool = False
    sleepy_timer: float = 0.0
    sleepy_duration: float = 3.00

    rage: bool = False
    rage_timer: float = 0.0
    rage_duration: float = 3.00

    h_flicker: bool = False
    h_flicker_alt: bool = False
    h_flicker_amp: float = FLICKER_AMP

    v_flicker: bool = False
    v_flicker_alt: bool = False
    v_flicker_amp: float = FLICKER_AMP


@dataclass
class EffectsState:
    breathing: bool = True
    breath_phase: float = 0.0
    boot_active: bool = True
    boot_timer: float = 0.0
    sparkle: bool = True
    sparkle_pixels: list = field(default_factory=list)
    fire_pixels: list = field(default_factory=list)
    afterglow: bool = False  # Off by default (matches MCU)
    afterglow_buf: list | None = None
    edge_glow: bool = True


@dataclass
class SystemState:
    mode: SystemMode = SystemMode.NONE
    timer: float = 0.0
    phase: int = 0
    param: float = 0.0


@dataclass
class FaceState:
    eye_l: EyeState = field(default_factory=EyeState)
    eye_r: EyeState = field(default_factory=EyeState)
    eyelids: EyelidState = field(default_factory=EyelidState)
    anim: AnimTimers = field(default_factory=AnimTimers)
    fx: EffectsState = field(default_factory=EffectsState)
    system: SystemState = field(default_factory=SystemState)

    mood: Mood = Mood.NEUTRAL
    expression_intensity: float = 1.0  # V3: mood sequencer ramp control
    brightness: float = 1.0
    solid_eye: bool = True
    show_mouth: bool = True

    talking: bool = False
    talking_energy: float = 0.0
    talking_phase: float = 0.0

    mouth_curve: float = 0.1
    mouth_curve_target: float = 0.1
    mouth_open: float = 0.0
    mouth_open_target: float = 0.0
    mouth_wave: float = 0.0
    mouth_wave_target: float = 0.0
    mouth_offset_x: float = 0.0
    mouth_offset_x_target: float = 0.0
    mouth_width: float = 1.0
    mouth_width_target: float = 1.0

    # Active gesture tracking (MCU: active_gesture + active_gesture_until)
    active_gesture: int = 0xFF  # 0xFF = none
    active_gesture_until: float = 0.0


# ── Physics ──────────────────────────────────────────────────────────


def _tween(current: float, target: float, speed: float) -> float:
    """Exponential interpolation (MCU: tween)."""
    return current + (target - current) * speed


def _spring(
    current: float, target: float, vel: float, k: float = SPRING_K, d: float = SPRING_D
) -> tuple[float, float]:
    """Spring physics for gaze (MCU: spring_step)."""
    force = (target - current) * k
    vel = (vel + force) * d
    return current + vel, vel


# ── Per-frame update ─────────────────────────────────────────────────


def face_state_update(fs: FaceState) -> None:
    """Main per-frame update — mirrors MCU face_state_update()."""
    now = time.monotonic()
    dt = 1.0 / 30.0

    if _update_system(fs):
        return

    if fs.fx.boot_active:
        if fs.fx.boot_timer == 0.0:
            fs.fx.boot_timer = now
        _update_boot(fs)
        _update_breathing(fs)
        _update_sparkle(fs)
        _update_fire(fs)
        # Expire active gesture during boot
        if fs.active_gesture != 0xFF and now > fs.active_gesture_until:
            fs.active_gesture = 0xFF
        return

    # ── 1. MOOD TARGETS with intensity blending ──────────────────
    targets = MOOD_TARGETS.get(fs.mood, MOOD_TARGETS[Mood.NEUTRAL])
    t_curve, t_width, t_open, t_lid_slope, t_lid_top, t_lid_bot = targets

    # Intensity blending: displayed = neutral + (target - neutral) * intensity
    intensity = max(0.0, min(1.0, fs.expression_intensity))
    t_curve = NEUTRAL_MOUTH_CURVE + (t_curve - NEUTRAL_MOUTH_CURVE) * intensity
    t_width = NEUTRAL_MOUTH_WIDTH + (t_width - NEUTRAL_MOUTH_WIDTH) * intensity
    t_open = NEUTRAL_MOUTH_OPEN + (t_open - NEUTRAL_MOUTH_OPEN) * intensity
    t_lid_slope = NEUTRAL_LID_SLOPE + (t_lid_slope - NEUTRAL_LID_SLOPE) * intensity
    t_lid_top = NEUTRAL_LID_TOP + (t_lid_top - NEUTRAL_LID_TOP) * intensity
    t_lid_bot = NEUTRAL_LID_BOT + (t_lid_bot - NEUTRAL_LID_BOT) * intensity

    # Eye scale overrides for specific moods
    eye_scale = MOOD_EYE_SCALE.get(fs.mood)
    if eye_scale is not None:
        ws, hs = eye_scale
        ws = 1.0 + (ws - 1.0) * intensity
        hs = 1.0 + (hs - 1.0) * intensity
        fs.eye_l.width_scale_target = ws
        fs.eye_r.width_scale_target = ws
        fs.eye_l.height_scale_target = hs
        fs.eye_r.height_scale_target = hs

    fs.mouth_curve_target = t_curve
    fs.mouth_width_target = t_width
    fs.mouth_open_target = t_open
    fs.mouth_wave_target = 0.0
    fs.mouth_offset_x_target = 0.0
    fs.eyelids.slope_target = t_lid_slope

    # Thinking: gaze up-and-aside + mouth offset
    if fs.mood == Mood.THINKING:
        fs.mouth_offset_x_target = THINKING_MOUTH_OFFSET_X
        fs.eye_l.gaze_x_target = THINKING_GAZE_X
        fs.eye_l.gaze_y_target = THINKING_GAZE_Y
        fs.eye_r.gaze_x_target = THINKING_GAZE_X
        fs.eye_r.gaze_y_target = THINKING_GAZE_Y

    # ── 2. GESTURE OVERRIDES ─────────────────────────────────────
    if fs.anim.surprise:
        elapsed_g = now - fs.anim.surprise_timer
        if elapsed_g < SURPRISE_PEAK_TIME:
            fs.eye_l.width_scale_target = SURPRISE_PEAK_W
            fs.eye_l.height_scale_target = SURPRISE_PEAK_H
            fs.eye_r.width_scale_target = SURPRISE_PEAK_W
            fs.eye_r.height_scale_target = SURPRISE_PEAK_H
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = 0.6
        fs.mouth_width_target = 0.5

    if fs.anim.laugh:
        fs.mouth_curve_target = 1.0
        elapsed_g = now - fs.anim.laugh_timer
        chatter = LAUGH_CHATTER_BASE + LAUGH_CHATTER_AMP * max(
            0.0, math.sin(elapsed_g * LAUGH_CHATTER_FREQ)
        )
        fs.mouth_open_target = max(fs.mouth_open_target, chatter)

    if fs.anim.rage:
        elapsed_g = now - fs.anim.rage_timer
        fs.eyelids.slope_target = RAGE_LID_SLOPE
        t_lid_top = max(t_lid_top, 0.4)
        shake = math.sin(elapsed_g * RAGE_SHAKE_FREQ) * RAGE_SHAKE_AMP
        fs.eye_l.gaze_x_target = shake
        fs.eye_r.gaze_x_target = shake
        fs.mouth_curve_target = RAGE_MOUTH_CURVE
        fs.mouth_open_target = RAGE_MOUTH_OPEN
        fs.mouth_wave_target = RAGE_MOUTH_WAVE

    if fs.anim.x_eyes:
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = X_EYES_MOUTH_OPEN
        fs.mouth_width_target = X_EYES_MOUTH_WIDTH

    if fs.anim.heart:
        fs.mouth_curve_target = HEART_MOUTH_CURVE
        fs.mouth_open_target = 0.0

    if fs.anim.sleepy:
        elapsed_g = now - fs.anim.sleepy_timer
        droop = min(1.0, elapsed_g / max(0.15, fs.anim.sleepy_duration * 0.5))
        t_lid_top = max(t_lid_top, droop * 0.6)
        fs.eyelids.slope_target = SLEEPY_LID_SLOPE
        sway = math.sin(elapsed_g * SLEEPY_SWAY_FREQ) * SLEEPY_SWAY_AMP
        fs.eye_l.gaze_x_target = sway
        fs.eye_r.gaze_x_target = sway
        fs.eye_l.gaze_y_target = droop * 3.0
        fs.eye_r.gaze_y_target = droop * 3.0
        # Yawn sequence
        dur = max(0.2, fs.anim.sleepy_duration)
        ys, yp, ye = dur * 0.2, dur * 0.4, dur * 0.7
        if elapsed_g < ys:
            pass
        elif elapsed_g < yp:
            fs.mouth_open_target = (elapsed_g - ys) / (yp - ys)
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = SLEEPY_MOUTH_WIDTH
        elif elapsed_g < ye:
            fs.mouth_open_target = 1.0
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = SLEEPY_MOUTH_WIDTH
        else:
            t2 = (elapsed_g - ye) / max(0.001, dur - ye)
            fs.mouth_open_target = max(0.0, 1.0 - t2 * 1.5)

    if fs.anim.confused:
        elapsed_g = now - fs.anim.confused_timer
        fs.mouth_offset_x_target = CONFUSED_OFFSET_AMP * math.sin(
            elapsed_g * CONFUSED_OFFSET_FREQ
        )
        fs.mouth_curve_target = CONFUSED_MOUTH_CURVE
        fs.mouth_open_target = 0.0

    # ── 3. GESTURE TIMEOUTS ──────────────────────────────────────
    if fs.anim.heart and now > fs.anim.heart_timer + fs.anim.heart_duration:
        fs.anim.heart = False

    if fs.anim.x_eyes and now > fs.anim.x_eyes_timer + fs.anim.x_eyes_duration:
        fs.anim.x_eyes = False

    if fs.anim.rage and now > fs.anim.rage_timer + fs.anim.rage_duration:
        fs.anim.rage = False
        fs.fx.fire_pixels.clear()

    if fs.anim.surprise and now > fs.anim.surprise_timer + fs.anim.surprise_duration:
        fs.anim.surprise = False

    if fs.anim.sleepy and now > fs.anim.sleepy_timer + fs.anim.sleepy_duration:
        fs.anim.sleepy = False

    if fs.anim.confused:
        if fs.anim.confused_toggle:
            fs.anim.h_flicker = True
            fs.anim.h_flicker_amp = FLICKER_AMP
            fs.anim.confused_toggle = False
        if now > fs.anim.confused_timer + fs.anim.confused_duration:
            fs.anim.confused = False
            fs.anim.h_flicker = False
            fs.anim.confused_toggle = True

    if fs.anim.laugh:
        if fs.anim.laugh_toggle:
            fs.anim.v_flicker = True
            fs.anim.v_flicker_amp = FLICKER_AMP
            fs.anim.laugh_toggle = False
        if now > fs.anim.laugh_timer + fs.anim.laugh_duration:
            fs.anim.laugh = False
            fs.anim.v_flicker = False
            fs.anim.laugh_toggle = True

    # ── 4. BLINK LOGIC ───────────────────────────────────────────
    if fs.anim.autoblink and now >= fs.anim.next_blink:
        face_blink(fs)
        fs.anim.next_blink = now + BLINK_INTERVAL + random.random() * BLINK_VARIATION

    # Per-eye blink reopening
    if not fs.eye_l.is_open and fs.eyelids.top_l > 0.95:
        fs.eye_l.is_open = True
    if not fs.eye_r.is_open and fs.eyelids.top_r > 0.95:
        fs.eye_r.is_open = True

    closure_l = 1.0 if not fs.eye_l.is_open else 0.0
    closure_r = 1.0 if not fs.eye_r.is_open else 0.0
    final_top_l = max(t_lid_top, closure_l)
    final_top_r = max(t_lid_top, closure_r)

    speed_l = (
        TWEEN_EYELID_TOP_CLOSING
        if final_top_l > fs.eyelids.top_l
        else TWEEN_EYELID_TOP_OPENING
    )
    speed_r = (
        TWEEN_EYELID_TOP_CLOSING
        if final_top_r > fs.eyelids.top_r
        else TWEEN_EYELID_TOP_OPENING
    )
    fs.eyelids.top_l = _tween(fs.eyelids.top_l, final_top_l, speed_l)
    fs.eyelids.top_r = _tween(fs.eyelids.top_r, final_top_r, speed_r)
    fs.eyelids.bottom_l = _tween(fs.eyelids.bottom_l, t_lid_bot, TWEEN_EYELID_BOT)
    fs.eyelids.bottom_r = _tween(fs.eyelids.bottom_r, t_lid_bot, TWEEN_EYELID_BOT)
    fs.eyelids.slope = _tween(
        fs.eyelids.slope, fs.eyelids.slope_target, TWEEN_EYELID_SLOPE
    )

    # ── 5. IDLE GAZE WANDER ──────────────────────────────────────
    if fs.anim.idle and now >= fs.anim.next_idle:
        target_x = random.uniform(-MAX_GAZE, MAX_GAZE)
        target_y = random.uniform(-MAX_GAZE * 0.6, MAX_GAZE * 0.6)

        if fs.mood == Mood.SILLY:
            if random.random() < 0.5:
                fs.eye_l.gaze_x_target = SILLY_CROSS_EYE_A[0]
                fs.eye_r.gaze_x_target = SILLY_CROSS_EYE_A[1]
            else:
                fs.eye_l.gaze_x_target = SILLY_CROSS_EYE_B[0]
                fs.eye_r.gaze_x_target = SILLY_CROSS_EYE_B[1]
        else:
            fs.eye_l.gaze_x_target = target_x
            fs.eye_r.gaze_x_target = target_x

        fs.eye_l.gaze_y_target = target_y
        fs.eye_r.gaze_y_target = target_y
        fs.anim.next_idle = (
            now + IDLE_GAZE_HOLD_MIN + random.random() * IDLE_GAZE_HOLD_RANGE
        )

    # Saccade jitter
    if now > fs.anim.next_saccade:
        jitter_x = random.uniform(-SACCADE_JITTER, SACCADE_JITTER)
        jitter_y = random.uniform(-SACCADE_JITTER, SACCADE_JITTER)
        fs.eye_l.gaze_x += jitter_x
        fs.eye_r.gaze_x += jitter_x
        fs.eye_l.gaze_y += jitter_y
        fs.eye_r.gaze_y += jitter_y
        fs.anim.next_saccade = now + random.uniform(
            SACCADE_INTERVAL_MIN, SACCADE_INTERVAL_MAX
        )

    # ── 6. TALKING ───────────────────────────────────────────────
    if fs.talking:
        fs.talking_phase += TALKING_PHASE_SPEED * dt
        e = max(0.0, min(1.0, fs.talking_energy))
        noise_open = math.sin(fs.talking_phase) + math.sin(fs.talking_phase * 2.3)
        noise_width = math.cos(fs.talking_phase * 0.7)

        base_open = TALKING_BASE_OPEN + TALKING_OPEN_MOD * e
        mod_open = abs(noise_open) * 0.6 * e
        base_width = 1.0
        mod_width = noise_width * TALKING_WIDTH_MOD * e

        fs.mouth_open_target = max(fs.mouth_open_target, base_open + mod_open)
        fs.mouth_width_target = base_width + mod_width

        bounce = abs(math.sin(fs.talking_phase)) * TALKING_BOUNCE_MOD * e
        fs.eye_l.height_scale_target += bounce
        fs.eye_r.height_scale_target += bounce

    # ── 7. UPDATE TWEENS + SPRING ────────────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        eye.gaze_x, eye.vx = _spring(eye.gaze_x, eye.gaze_x_target, eye.vx)
        eye.gaze_y, eye.vy = _spring(eye.gaze_y, eye.gaze_y_target, eye.vy)
        eye.width_scale = _tween(
            eye.width_scale, eye.width_scale_target, TWEEN_EYE_SCALE
        )
        eye.height_scale = _tween(
            eye.height_scale, eye.height_scale_target, TWEEN_EYE_SCALE
        )
        eye.openness_target = 1.0 if eye.is_open else 0.0
        eye.openness = _tween(eye.openness, eye.openness_target, TWEEN_OPENNESS)
        # Reset scale targets (MCU resets to 1.0 each frame)
        eye.width_scale_target = 1.0
        eye.height_scale_target = 1.0

    fs.mouth_curve = _tween(fs.mouth_curve, fs.mouth_curve_target, TWEEN_MOUTH_CURVE)
    fs.mouth_open = _tween(fs.mouth_open, fs.mouth_open_target, TWEEN_MOUTH_OPEN)
    fs.mouth_width = _tween(fs.mouth_width, fs.mouth_width_target, TWEEN_MOUTH_WIDTH)
    fs.mouth_offset_x = _tween(
        fs.mouth_offset_x, fs.mouth_offset_x_target, TWEEN_MOUTH_OFFSET_X
    )
    fs.mouth_wave = _tween(fs.mouth_wave, fs.mouth_wave_target, TWEEN_MOUTH_WAVE)

    # Flicker post-processing (after spring)
    if fs.anim.h_flicker:
        dx = fs.anim.h_flicker_amp if fs.anim.h_flicker_alt else -fs.anim.h_flicker_amp
        fs.eye_l.gaze_x += dx
        fs.eye_r.gaze_x += dx
        fs.anim.h_flicker_alt = not fs.anim.h_flicker_alt

    if fs.anim.v_flicker:
        dy = fs.anim.v_flicker_amp if fs.anim.v_flicker_alt else -fs.anim.v_flicker_amp
        fs.eye_l.gaze_y += dy
        fs.eye_r.gaze_y += dy
        fs.anim.v_flicker_alt = not fs.anim.v_flicker_alt

    _update_breathing(fs)
    _update_sparkle(fs)
    _update_fire(fs)

    # Expire active gesture
    if fs.active_gesture != 0xFF and now > fs.active_gesture_until:
        fs.active_gesture = 0xFF


# ── Internal helpers ─────────────────────────────────────────────────


def _update_boot(fs: FaceState) -> None:
    now = time.monotonic()
    elapsed = now - fs.fx.boot_timer
    if elapsed < 1.0:
        val = 1.0 - (1.0 - elapsed) ** 3  # Ease-out cubic
        fs.eyelids.top_l = 1.0 - val
        fs.eyelids.top_r = 1.0 - val
    else:
        fs.fx.boot_active = False


def _update_breathing(fs: FaceState) -> None:
    if fs.fx.breathing:
        fs.fx.breath_phase += BREATH_SPEED / 30.0
        if fs.fx.breath_phase > 6.28:
            fs.fx.breath_phase -= 6.28


def _update_sparkle(fs: FaceState) -> None:
    if not fs.fx.sparkle:
        fs.fx.sparkle_pixels.clear()
        return
    fs.fx.sparkle_pixels = [
        (x, y, life - 1) for x, y, life in fs.fx.sparkle_pixels if life > 0
    ]
    if random.random() < SPARKLE_CHANCE:
        fs.fx.sparkle_pixels.append(
            (
                random.randint(0, SCREEN_W),
                random.randint(0, SCREEN_H),
                random.randint(SPARKLE_LIFE_MIN, SPARKLE_LIFE_MAX),
            )
        )


def _update_fire(fs: FaceState) -> None:
    if not fs.anim.rage:
        fs.fx.fire_pixels.clear()
        return
    fs.fx.fire_pixels = [
        (
            x + random.uniform(-FIRE_DRIFT, FIRE_DRIFT),
            y - FIRE_RISE_SPEED,
            life - 1,
            heat * FIRE_HEAT_DECAY,
        )
        for x, y, life, heat in fs.fx.fire_pixels
        if life > 1 and y > 0
    ]
    if random.random() < FIRE_SPAWN_CHANCE:
        for cx in (LEFT_EYE_CX, RIGHT_EYE_CX):
            x = cx + random.uniform(-20, 20)
            y = LEFT_EYE_CY - 30
            fs.fx.fire_pixels.append(
                (
                    x,
                    y,
                    random.randint(SPARKLE_LIFE_MIN, SPARKLE_LIFE_MAX),
                    1.0,
                )
            )


def _update_system(fs: FaceState) -> bool:
    return fs.system.mode != SystemMode.NONE


def _set_active_gesture(fs: FaceState, gesture: GestureId, duration: float) -> None:
    now = time.monotonic()
    fs.active_gesture = int(gesture)
    fs.active_gesture_until = now + duration


# ── Public API (mirrors MCU face_state.cpp) ──────────────────────────


def face_blink(fs: FaceState) -> None:
    fs.eye_l.is_open = False
    fs.eye_r.is_open = False
    fs.eye_l.openness_target = 0.0
    fs.eye_r.openness_target = 0.0
    _set_active_gesture(fs, GestureId.BLINK, 0.18)


def face_wink_left(fs: FaceState) -> None:
    fs.eye_l.is_open = False
    fs.eye_l.openness_target = 0.0
    _set_active_gesture(fs, GestureId.WINK_L, 0.20)


def face_wink_right(fs: FaceState) -> None:
    fs.eye_r.is_open = False
    fs.eye_r.openness_target = 0.0
    _set_active_gesture(fs, GestureId.WINK_R, 0.20)


def face_set_gaze(fs: FaceState, x: float, y: float) -> None:
    x = max(-MAX_GAZE, min(MAX_GAZE, x))
    y = max(-MAX_GAZE, min(MAX_GAZE, y))
    fs.eye_l.gaze_x_target = x
    fs.eye_l.gaze_y_target = y
    fs.eye_r.gaze_x_target = x
    fs.eye_r.gaze_y_target = y


def face_set_mood(fs: FaceState, mood: Mood) -> None:
    fs.mood = mood


def face_set_expression_intensity(fs: FaceState, intensity: float) -> None:
    fs.expression_intensity = max(0.0, min(1.0, intensity))


def face_trigger_gesture(
    fs: FaceState, gesture: GestureId, duration_ms: int = 0
) -> None:
    """Trigger a gesture. duration_ms=0 uses default from GESTURE_DURATIONS."""
    now = time.monotonic()
    default_dur = GESTURE_DURATIONS.get(gesture, 0.5)
    dur = max(0.08, duration_ms / 1000.0) if duration_ms > 0 else default_dur

    if gesture == GestureId.BLINK:
        face_blink(fs)
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.WINK_L:
        face_wink_left(fs)
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.WINK_R:
        face_wink_right(fs)
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.NOD:
        fs.anim.laugh = True
        fs.anim.laugh_timer = now
        fs.anim.laugh_toggle = True
        fs.anim.laugh_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.HEADSHAKE:
        fs.anim.confused = True
        fs.anim.confused_timer = now
        fs.anim.confused_toggle = True
        fs.anim.confused_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.WIGGLE:
        wd = dur if duration_ms > 0 else GESTURE_DURATIONS[GestureId.WIGGLE]
        fs.anim.confused = True
        fs.anim.confused_timer = now
        fs.anim.confused_toggle = True
        fs.anim.confused_duration = wd
        fs.anim.laugh = True
        fs.anim.laugh_timer = now
        fs.anim.laugh_toggle = True
        fs.anim.laugh_duration = wd
        _set_active_gesture(fs, gesture, wd)
    elif gesture == GestureId.LAUGH:
        fs.anim.laugh = True
        fs.anim.laugh_timer = now
        fs.anim.laugh_toggle = True
        fs.anim.laugh_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.CONFUSED:
        fs.anim.confused = True
        fs.anim.confused_timer = now
        fs.anim.confused_toggle = True
        fs.anim.confused_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.RAGE:
        fs.anim.rage = True
        fs.anim.rage_timer = now
        fs.anim.rage_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.HEART:
        fs.anim.heart = True
        fs.anim.heart_timer = now
        fs.anim.heart_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.X_EYES:
        fs.anim.x_eyes = True
        fs.anim.x_eyes_timer = now
        fs.anim.x_eyes_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.SLEEPY:
        fs.anim.sleepy = True
        fs.anim.sleepy_timer = now
        fs.anim.sleepy_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.SURPRISE:
        fs.anim.surprise = True
        fs.anim.surprise_timer = now
        fs.anim.surprise_duration = dur
        _set_active_gesture(fs, gesture, dur)


def face_set_system_mode(fs: FaceState, mode: SystemMode, param: float = 0.0) -> None:
    if fs.system.mode == mode:
        fs.system.param = param
        return
    fs.system.mode = mode
    fs.system.timer = time.monotonic()
    fs.system.phase = 0
    fs.system.param = param


def face_set_flags(fs: FaceState, flags: int) -> None:
    """Apply feature flag bitmask to FaceState boolean fields."""
    fs.anim.idle = bool(flags & FLAG_IDLE_WANDER)
    fs.anim.autoblink = bool(flags & FLAG_AUTOBLINK)
    fs.solid_eye = bool(flags & FLAG_SOLID_EYE)
    fs.show_mouth = bool(flags & FLAG_SHOW_MOUTH)
    fs.fx.edge_glow = bool(flags & FLAG_EDGE_GLOW)
    fs.fx.sparkle = bool(flags & FLAG_SPARKLE)
    fs.fx.afterglow = bool(flags & FLAG_AFTERGLOW)


def face_get_flags(fs: FaceState) -> int:
    """Read current flag state as bitmask."""
    flags = 0
    if fs.anim.idle:
        flags |= FLAG_IDLE_WANDER
    if fs.anim.autoblink:
        flags |= FLAG_AUTOBLINK
    if fs.solid_eye:
        flags |= FLAG_SOLID_EYE
    if fs.show_mouth:
        flags |= FLAG_SHOW_MOUTH
    if fs.fx.edge_glow:
        flags |= FLAG_EDGE_GLOW
    if fs.fx.sparkle:
        flags |= FLAG_SPARKLE
    if fs.fx.afterglow:
        flags |= FLAG_AFTERGLOW
    return flags


def face_get_breath_scale(fs: FaceState) -> float:
    if not fs.fx.breathing:
        return 1.0
    return 1.0 + math.sin(fs.fx.breath_phase) * BREATH_AMOUNT


def face_get_emotion_color(fs: FaceState) -> tuple[int, int, int]:
    """Get current face color with intensity blending (MCU-accurate)."""
    # Gesture overrides take priority
    if fs.anim.rage:
        mood_color = GESTURE_COLOR_RAGE
    elif fs.anim.heart:
        mood_color = GESTURE_COLOR_HEART
    elif fs.anim.x_eyes:
        mood_color = GESTURE_COLOR_X_EYES
    else:
        mood_color = MOOD_COLORS.get(fs.mood, NEUTRAL_COLOR)

    # Intensity blending: neutral_color + (mood_color - neutral_color) * intensity
    intensity = max(0.0, min(1.0, fs.expression_intensity))
    nr, ng, nb = NEUTRAL_COLOR
    mr, mg, mb = mood_color
    r = int(max(0.0, min(255.0, nr + (mr - nr) * intensity)))
    g = int(max(0.0, min(255.0, ng + (mg - ng) * intensity)))
    b = int(max(0.0, min(255.0, nb + (mb - nb) * intensity)))
    return (r, g, b)
