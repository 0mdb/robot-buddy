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
    HEADSHAKE_FREQ,
    HEADSHAKE_GAZE_X_AMP,
    HEADSHAKE_MOUTH_CURVE,
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
    NOD_FREQ,
    NOD_GAZE_Y_AMP,
    NOD_LID_TOP_OFFSET,
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
    CONFUSED_MOOD_MOUTH_OFFSET_X,
    CURIOUS_BROW_OFFSET,
    LOVE_CONVERGENCE_X,
    LOVE_IDLE_AMPLITUDE,
    LOVE_IDLE_HOLD_MIN,
    LOVE_IDLE_HOLD_RANGE,
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
    CELEBRATE_EYE_SCALE,
    CELEBRATE_MOUTH_CURVE,
    CELEBRATE_SPARKLE_BOOST,
    DIZZY_FREQ,
    DIZZY_GAZE_R_MAX,
    DIZZY_MOUTH_WAVE,
    EYE_ROLL_GAZE_R,
    EYE_ROLL_LID_PEAK,
    GESTURE_COLOR_CELEBRATE_A,
    GESTURE_COLOR_CELEBRATE_B,
    GESTURE_COLOR_CELEBRATE_C,
    GESTURE_COLOR_SHY,
    PEEK_A_BOO_CLOSE_TIME,
    PEEK_A_BOO_PEAK_H,
    PEEK_A_BOO_PEAK_W,
    SHY_GAZE_X,
    SHY_GAZE_Y,
    SHY_LID_BOT,
    SHY_MOUTH_CURVE,
    SHY_PEEK_FRAC,
    STARTLE_PEAK_H,
    STARTLE_PEAK_TIME,
    STARTLE_PEAK_W,
    THINKING_HARD_FREQ,
    THINKING_HARD_GAZE_A,
    THINKING_HARD_GAZE_B,
    THINKING_HARD_LID_SLOPE,
    THINKING_HARD_MOUTH_OFFSET_FREQ,
    SPEECH_BREATH_MAX,
    SPEECH_BREATH_MIN,
    SPEECH_BREATH_MOD,
    SPEECH_EYE_PULSE_AMOUNT,
    SPEECH_EYE_PULSE_DECAY,
    SPEECH_EYE_PULSE_FRAMES,
    SPEECH_EYE_PULSE_THRESHOLD,
    SPEECH_PAUSE_FRAMES,
    SPEECH_PAUSE_GAZE_SHIFT,
    SPEECH_PAUSE_THRESHOLD,
    MICRO_EXPR_CURIOUS_DUR,
    MICRO_EXPR_FIDGET_DUR,
    MICRO_EXPR_MIN_INTERVAL,
    MICRO_EXPR_RANGE,
    MICRO_EXPR_SIGH_DUR,
    HOLIDAY_BIRTHDAY_CELEBRATE_INTERVAL,
    HOLIDAY_BIRTHDAY_COLOR_A,
    HOLIDAY_BIRTHDAY_COLOR_B,
    HOLIDAY_BIRTHDAY_SPARKLE,
    HOLIDAY_CHRISTMAS_BREATH_SPEED,
    HOLIDAY_CHRISTMAS_COLOR,
    HOLIDAY_CONFETTI_COLORS,
    HOLIDAY_CONFETTI_DRIFT,
    HOLIDAY_CONFETTI_FALL_SPEED,
    HOLIDAY_CONFETTI_LIFE_MAX,
    HOLIDAY_CONFETTI_LIFE_MIN,
    HOLIDAY_CONFETTI_SPAWN_CHANCE,
    HOLIDAY_HALLOWEEN_COLOR,
    HOLIDAY_HALLOWEEN_FLICKER,
    HOLIDAY_HALLOWEEN_LID_SLOPE,
    HOLIDAY_SNOW_DRIFT_AMP,
    HOLIDAY_SNOW_FALL_SPEED,
    HOLIDAY_SNOW_LIFE_MAX,
    HOLIDAY_SNOW_LIFE_MIN,
    HOLIDAY_SNOW_SPAWN_CHANCE,
    GestureId,
    HolidayMode,
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

    nod: bool = False
    nod_timer: float = 0.0
    nod_duration: float = 0.35

    headshake: bool = False
    headshake_timer: float = 0.0
    headshake_duration: float = 0.35

    peek_a_boo: bool = False
    peek_a_boo_timer: float = 0.0
    peek_a_boo_duration: float = 1.50

    shy: bool = False
    shy_timer: float = 0.0
    shy_duration: float = 2.00

    eye_roll: bool = False
    eye_roll_timer: float = 0.0
    eye_roll_duration: float = 1.00

    dizzy: bool = False
    dizzy_timer: float = 0.0
    dizzy_duration: float = 2.00

    celebrate: bool = False
    celebrate_timer: float = 0.0
    celebrate_duration: float = 2.50

    startle_relief: bool = False
    startle_relief_timer: float = 0.0
    startle_relief_duration: float = 1.50

    thinking_hard: bool = False
    thinking_hard_timer: float = 0.0
    thinking_hard_duration: float = 3.00

    # Idle micro-expressions
    micro_expr_next: float = 0.0  # Monotonic time of next trigger
    micro_expr_type: int = 0  # 0=none, 1=curious, 2=sigh, 3=fidget
    micro_expr_timer: float = 0.0
    micro_expr_active: bool = False

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
    snow_pixels: list = field(default_factory=list)  # (x, y, life, phase)
    confetti_pixels: list = field(default_factory=list)  # (x, y, life, color_idx)


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
    mood_color_override: tuple[int, int, int] | None = None  # System mode color
    holiday_mode: int = 0  # HolidayMode.NONE
    _holiday_timer: float = 0.0  # For periodic gesture triggers

    talking: bool = False
    talking_energy: float = 0.0
    talking_phase: float = 0.0

    # Speech rhythm sync state
    _speech_high_frames: int = 0
    _speech_eye_pulse: float = 0.0
    _speech_low_frames: int = 0
    _speech_pause_fired: bool = False

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

    # ── 0b. HOLIDAY MODE TICK ──────────────────────────────────────
    _update_holiday(fs, now)

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

    # Reset eye scale targets to default each frame (MCU: face_state.cpp:559-560)
    fs.eye_l.width_scale_target = 1.0
    fs.eye_l.height_scale_target = 1.0
    fs.eye_r.width_scale_target = 1.0
    fs.eye_r.height_scale_target = 1.0

    # Apply per-mood eye scale with intensity blending
    eye_scale = MOOD_EYE_SCALE.get(fs.mood, (1.0, 1.0))
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

    # Confused: persistent asymmetric mouth (puzzled look)
    if fs.mood == Mood.CONFUSED:
        fs.mouth_offset_x_target = CONFUSED_MOOD_MOUTH_OFFSET_X

    # Love: mild pupil convergence (soft focus / adoring gaze)
    if fs.mood == Mood.LOVE:
        li = max(0.0, min(1.0, fs.expression_intensity))
        fs.eye_l.gaze_x_target = LOVE_CONVERGENCE_X * li
        fs.eye_r.gaze_x_target = -LOVE_CONVERGENCE_X * li

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

    if fs.anim.peek_a_boo:
        elapsed_g = now - fs.anim.peek_a_boo_timer
        dur = max(0.01, fs.anim.peek_a_boo_duration)
        frac = elapsed_g / dur
        if frac < PEEK_A_BOO_CLOSE_TIME:
            # Eyes shutting — force lids closed
            t_lid_top = 1.0
        elif frac < PEEK_A_BOO_CLOSE_TIME + 0.2:
            # Pop open — surprise-scale eyes
            fs.eye_l.width_scale_target = PEEK_A_BOO_PEAK_W
            fs.eye_l.height_scale_target = PEEK_A_BOO_PEAK_H
            fs.eye_r.width_scale_target = PEEK_A_BOO_PEAK_W
            fs.eye_r.height_scale_target = PEEK_A_BOO_PEAK_H
            fs.mouth_open_target = 0.4
            fs.mouth_curve_target = 0.0
        # else: settling back (tweens return to 1.0)

    if fs.anim.shy:
        elapsed_g = now - fs.anim.shy_timer
        dur = max(0.01, fs.anim.shy_duration)
        frac = elapsed_g / dur
        fs.eye_l.gaze_x_target = SHY_GAZE_X
        fs.eye_l.gaze_y_target = SHY_GAZE_Y
        fs.eye_r.gaze_x_target = SHY_GAZE_X
        fs.eye_r.gaze_y_target = SHY_GAZE_Y
        t_lid_bot = max(t_lid_bot, SHY_LID_BOT)
        fs.mouth_curve_target = SHY_MOUTH_CURVE
        # Brief peek-up glance
        if SHY_PEEK_FRAC < frac < SHY_PEEK_FRAC + 0.15:
            fs.eye_l.gaze_y_target = -2.0
            fs.eye_r.gaze_y_target = -2.0

    if fs.anim.eye_roll:
        # Lid droop when looking up (gaze is post-spring)
        elapsed_g = now - fs.anim.eye_roll_timer
        dur = max(0.01, fs.anim.eye_roll_duration)
        frac = elapsed_g / dur
        if frac < 0.8:
            angle = (frac / 0.8) * 2.0 * math.pi
            gy = -EYE_ROLL_GAZE_R * math.cos(angle)
            if gy < -EYE_ROLL_GAZE_R * 0.5:
                t_lid_top = max(t_lid_top, EYE_ROLL_LID_PEAK)

    if fs.anim.dizzy:
        # Mouth wave (gaze is post-spring)
        fs.mouth_wave_target = DIZZY_MOUTH_WAVE

    if fs.anim.celebrate:
        elapsed_g = now - fs.anim.celebrate_timer
        dur = max(0.01, fs.anim.celebrate_duration)
        frac = elapsed_g / dur
        # Big eyes
        fs.eye_l.width_scale_target = CELEBRATE_EYE_SCALE
        fs.eye_l.height_scale_target = CELEBRATE_EYE_SCALE
        fs.eye_r.width_scale_target = CELEBRATE_EYE_SCALE
        fs.eye_r.height_scale_target = CELEBRATE_EYE_SCALE
        # Big smile
        fs.mouth_curve_target = CELEBRATE_MOUTH_CURVE
        # Rapid alternating winks (L-R-L at 0.2, 0.4, 0.6)
        for idx, wf in enumerate([0.2, 0.4, 0.6]):
            if wf <= frac < wf + 0.05:
                if idx % 2 == 0 and fs.eye_l.is_open:
                    fs.eye_l.is_open = False
                    fs.eye_l.openness_target = 0.0
                elif idx % 2 == 1 and fs.eye_r.is_open:
                    fs.eye_r.is_open = False
                    fs.eye_r.openness_target = 0.0

    if fs.anim.startle_relief:
        elapsed_g = now - fs.anim.startle_relief_timer
        dur = max(0.01, fs.anim.startle_relief_duration)
        frac = elapsed_g / dur
        startle_frac = STARTLE_PEAK_TIME / dur
        if frac < startle_frac:
            # Phase 1: Startle — wide eyes, O mouth
            fs.eye_l.width_scale_target = STARTLE_PEAK_W
            fs.eye_l.height_scale_target = STARTLE_PEAK_H
            fs.eye_r.width_scale_target = STARTLE_PEAK_W
            fs.eye_r.height_scale_target = STARTLE_PEAK_H
            fs.mouth_curve_target = 0.0
            fs.mouth_open_target = 0.6
            fs.mouth_width_target = 0.5
        else:
            # Phase 2: Relief — happy squint, big smile, gaze down
            fs.mouth_curve_target = 0.8
            fs.eye_l.width_scale_target = 1.05
            fs.eye_l.height_scale_target = 0.9
            fs.eye_r.width_scale_target = 1.05
            fs.eye_r.height_scale_target = 0.9
            t_lid_bot = max(t_lid_bot, 0.3)
            fs.eye_l.gaze_y_target = 2.0
            fs.eye_r.gaze_y_target = 2.0

    if fs.anim.thinking_hard:
        elapsed_g = now - fs.anim.thinking_hard_timer
        # Gaze oscillates between up-right and up-left
        t_osc = (math.sin(elapsed_g * THINKING_HARD_FREQ) + 1.0) * 0.5
        gx = (
            THINKING_HARD_GAZE_A[0]
            + (THINKING_HARD_GAZE_B[0] - THINKING_HARD_GAZE_A[0]) * t_osc
        )
        gy = (
            THINKING_HARD_GAZE_A[1]
            + (THINKING_HARD_GAZE_B[1] - THINKING_HARD_GAZE_A[1]) * t_osc
        )
        fs.eye_l.gaze_x_target = gx
        fs.eye_r.gaze_x_target = gx
        fs.eye_l.gaze_y_target = gy
        fs.eye_r.gaze_y_target = gy
        # Brow furrow
        fs.eyelids.slope_target = THINKING_HARD_LID_SLOPE
        # Mouth offset oscillation
        fs.mouth_offset_x_target = 2.0 * math.sin(
            elapsed_g * THINKING_HARD_MOUTH_OFFSET_FREQ
        )
        # Eyes narrow slightly
        fs.eye_l.height_scale_target = 0.9
        fs.eye_r.height_scale_target = 0.9

    if fs.anim.nod:
        # Lid droop stays pre-spring (eyelid tweens, not spring-driven)
        elapsed_g = now - fs.anim.nod_timer
        lid_offset = NOD_LID_TOP_OFFSET * max(0.0, math.sin(elapsed_g * NOD_FREQ))
        t_lid_top = max(t_lid_top, lid_offset)
        # Gaze override is post-spring (see below) to bypass spring attenuation

    if fs.anim.headshake:
        # Mouth frown stays pre-spring (mouth tweens, not spring-driven)
        fs.mouth_curve_target = HEADSHAKE_MOUTH_CURVE
        # Gaze override is post-spring (see below) to bypass spring attenuation

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

    if fs.anim.nod and now > fs.anim.nod_timer + fs.anim.nod_duration:
        fs.anim.nod = False

    if fs.anim.headshake and now > fs.anim.headshake_timer + fs.anim.headshake_duration:
        fs.anim.headshake = False

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

    if (
        fs.anim.peek_a_boo
        and now > fs.anim.peek_a_boo_timer + fs.anim.peek_a_boo_duration
    ):
        fs.anim.peek_a_boo = False

    if fs.anim.shy and now > fs.anim.shy_timer + fs.anim.shy_duration:
        fs.anim.shy = False

    if fs.anim.eye_roll and now > fs.anim.eye_roll_timer + fs.anim.eye_roll_duration:
        fs.anim.eye_roll = False

    if fs.anim.dizzy and now > fs.anim.dizzy_timer + fs.anim.dizzy_duration:
        fs.anim.dizzy = False

    if fs.anim.celebrate and now > fs.anim.celebrate_timer + fs.anim.celebrate_duration:
        fs.anim.celebrate = False

    if (
        fs.anim.startle_relief
        and now > fs.anim.startle_relief_timer + fs.anim.startle_relief_duration
    ):
        fs.anim.startle_relief = False

    if (
        fs.anim.thinking_hard
        and now > fs.anim.thinking_hard_timer + fs.anim.thinking_hard_duration
    ):
        fs.anim.thinking_hard = False

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

    # Curious: asymmetric brow — right eye slightly hooded, left appears "raised"
    if fs.mood == Mood.CURIOUS:
        ci = max(0.0, min(1.0, fs.expression_intensity))
        final_top_r = max(final_top_r, CURIOUS_BROW_OFFSET * ci)

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
            # Scale cross-eye offset by expression_intensity (spec §4.1.3)
            si = max(0.0, min(1.0, fs.expression_intensity))
            if random.random() < 0.5:
                fs.eye_l.gaze_x_target = SILLY_CROSS_EYE_A[0] * si
                fs.eye_r.gaze_x_target = SILLY_CROSS_EYE_A[1] * si
            else:
                fs.eye_l.gaze_x_target = SILLY_CROSS_EYE_B[0] * si
                fs.eye_r.gaze_x_target = SILLY_CROSS_EYE_B[1] * si
        elif fs.mood == Mood.LOVE:
            # Reduced wander amplitude + convergence maintained (still, adoring)
            amp = LOVE_IDLE_AMPLITUDE
            fs.eye_l.gaze_x_target = target_x * amp + LOVE_CONVERGENCE_X
            fs.eye_r.gaze_x_target = target_x * amp - LOVE_CONVERGENCE_X
        else:
            fs.eye_l.gaze_x_target = target_x
            fs.eye_r.gaze_x_target = target_x

        if fs.mood == Mood.LOVE:
            fs.eye_l.gaze_y_target = target_y * LOVE_IDLE_AMPLITUDE
            fs.eye_r.gaze_y_target = target_y * LOVE_IDLE_AMPLITUDE
            fs.anim.next_idle = (
                now + LOVE_IDLE_HOLD_MIN + random.random() * LOVE_IDLE_HOLD_RANGE
            )
        else:
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

    # ── 5b. IDLE MICRO-EXPRESSIONS ─────────────────────────────
    # Only fire when idle (no gesture, no talking, no system mode)
    if (
        fs.anim.idle
        and not fs.talking
        and fs.active_gesture == 0xFF
        and fs.system.mode == SystemMode.NONE
    ):
        if not fs.anim.micro_expr_active:
            if fs.anim.micro_expr_next == 0.0:
                fs.anim.micro_expr_next = (
                    now + MICRO_EXPR_MIN_INTERVAL + random.random() * MICRO_EXPR_RANGE
                )
            elif now >= fs.anim.micro_expr_next:
                fs.anim.micro_expr_type = random.randint(1, 3)
                fs.anim.micro_expr_timer = now
                fs.anim.micro_expr_active = True
        else:
            elapsed_m = now - fs.anim.micro_expr_timer
            mtype = fs.anim.micro_expr_type
            done = False

            if mtype == 1:  # Curious glance
                if elapsed_m < MICRO_EXPR_CURIOUS_DUR:
                    # Brief asymmetric brow + quick gaze shift
                    t_lid_top = max(t_lid_top, 0.0)
                    # Right eye slightly hooded (curious brow)
                    frac_m = elapsed_m / MICRO_EXPR_CURIOUS_DUR
                    brow = CURIOUS_BROW_OFFSET * math.sin(frac_m * math.pi)
                    fs.eyelids.top_r = max(fs.eyelids.top_r, brow)
                    shift = 4.0 * math.sin(frac_m * math.pi)
                    fs.eye_l.gaze_x_target += shift
                    fs.eye_r.gaze_x_target += shift
                else:
                    done = True

            elif mtype == 2:  # Content sigh
                if elapsed_m < MICRO_EXPR_SIGH_DUR:
                    frac_m = elapsed_m / MICRO_EXPR_SIGH_DUR
                    droop = 0.3 * math.sin(frac_m * math.pi)
                    t_lid_top = max(t_lid_top, droop)
                    fs.mouth_curve_target = max(fs.mouth_curve_target, 0.3)
                else:
                    done = True

            elif mtype == 3:  # Fidget (quick double-blink)
                if elapsed_m < MICRO_EXPR_FIDGET_DUR:
                    # Trigger blink at start and midpoint
                    if elapsed_m < 0.05:
                        face_blink(fs)
                    elif 0.18 < elapsed_m < 0.22:
                        face_blink(fs)
                else:
                    done = True

            if done:
                fs.anim.micro_expr_active = False
                fs.anim.micro_expr_type = 0
                fs.anim.micro_expr_next = (
                    now + MICRO_EXPR_MIN_INTERVAL + random.random() * MICRO_EXPR_RANGE
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

        # ── Speech rhythm: eye energy pulses ───────────────────
        if e > SPEECH_EYE_PULSE_THRESHOLD:
            fs._speech_high_frames += 1
            if fs._speech_high_frames >= SPEECH_EYE_PULSE_FRAMES:
                fs._speech_eye_pulse = SPEECH_EYE_PULSE_AMOUNT
        else:
            fs._speech_high_frames = 0

        if fs._speech_eye_pulse > 0.001:
            fs.eye_l.height_scale_target += fs._speech_eye_pulse
            fs.eye_r.height_scale_target += fs._speech_eye_pulse
            fs._speech_eye_pulse *= SPEECH_EYE_PULSE_DECAY

        # ── Speech rhythm: pause gaze shift ────────────────────
        if e < SPEECH_PAUSE_THRESHOLD:
            fs._speech_low_frames += 1
            if (
                fs._speech_low_frames >= SPEECH_PAUSE_FRAMES
                and not fs._speech_pause_fired
            ):
                # One-shot gaze micro-shift ("collecting a thought")
                shift = SPEECH_PAUSE_GAZE_SHIFT * (
                    1.0 if random.random() < 0.5 else -1.0
                )
                fs.eye_l.gaze_x_target += shift
                fs.eye_r.gaze_x_target += shift
                fs._speech_pause_fired = True
        else:
            fs._speech_low_frames = 0
            fs._speech_pause_fired = False
    else:
        # Reset speech rhythm state when not talking
        fs._speech_high_frames = 0
        fs._speech_eye_pulse = 0.0
        fs._speech_low_frames = 0
        fs._speech_pause_fired = False

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

    # NOD/HEADSHAKE post-spring gaze overrides (bypass spring for crisp kinematics)
    if fs.anim.nod:
        elapsed_g = now - fs.anim.nod_timer
        gaze_y = NOD_GAZE_Y_AMP * math.sin(elapsed_g * NOD_FREQ)
        fs.eye_l.gaze_y = gaze_y
        fs.eye_r.gaze_y = gaze_y

    if fs.anim.headshake:
        elapsed_g = now - fs.anim.headshake_timer
        gaze_x = HEADSHAKE_GAZE_X_AMP * math.sin(elapsed_g * HEADSHAKE_FREQ)
        fs.eye_l.gaze_x = gaze_x
        fs.eye_r.gaze_x = gaze_x

    # EYE_ROLL / DIZZY post-spring gaze overrides (crisp circular/spiral motion)
    if fs.anim.eye_roll:
        elapsed_g = now - fs.anim.eye_roll_timer
        dur = max(0.01, fs.anim.eye_roll_duration)
        frac = elapsed_g / dur
        if frac < 0.8:
            angle = (frac / 0.8) * 2.0 * math.pi
            gx = EYE_ROLL_GAZE_R * math.sin(angle)
            gy = -EYE_ROLL_GAZE_R * math.cos(angle)
            fs.eye_l.gaze_x = gx
            fs.eye_r.gaze_x = gx
            fs.eye_l.gaze_y = gy
            fs.eye_r.gaze_y = gy

    if fs.anim.dizzy:
        elapsed_g = now - fs.anim.dizzy_timer
        dur = max(0.01, fs.anim.dizzy_duration)
        frac = elapsed_g / dur
        # Spiral: growing then shrinking amplitude
        if frac < 0.5:
            amp = DIZZY_GAZE_R_MAX * (frac / 0.5)
        else:
            amp = DIZZY_GAZE_R_MAX * (1.0 - (frac - 0.5) / 0.5)
        angle = elapsed_g * DIZZY_FREQ
        gx = amp * math.sin(angle)
        gy = amp * math.cos(angle)
        # Slight cross-eye wobble: offset per eye
        fs.eye_l.gaze_x = gx + 1.0
        fs.eye_r.gaze_x = gx - 1.0
        fs.eye_l.gaze_y = gy
        fs.eye_r.gaze_y = gy

    _update_breathing(fs)
    _update_sparkle(fs)
    _update_fire(fs)
    _update_snow(fs)
    _update_confetti(fs)

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
        # During talking, modulate breath speed by energy
        if fs.talking:
            e = max(0.0, min(1.0, fs.talking_energy))
            speed = BREATH_SPEED + (e - 0.5) * SPEECH_BREATH_MOD
            speed = max(SPEECH_BREATH_MIN, min(SPEECH_BREATH_MAX, speed))
        elif fs.holiday_mode == HolidayMode.CHRISTMAS:
            speed = HOLIDAY_CHRISTMAS_BREATH_SPEED
        else:
            speed = BREATH_SPEED
        fs.fx.breath_phase += speed / 30.0
        if fs.fx.breath_phase > 6.28:
            fs.fx.breath_phase -= 6.28


def _update_sparkle(fs: FaceState) -> None:
    if not fs.fx.sparkle:
        fs.fx.sparkle_pixels.clear()
        return
    fs.fx.sparkle_pixels = [
        (x, y, life - 1) for x, y, life in fs.fx.sparkle_pixels if life > 0
    ]
    if fs.anim.celebrate:
        chance = CELEBRATE_SPARKLE_BOOST
    elif fs.holiday_mode == HolidayMode.BIRTHDAY:
        chance = HOLIDAY_BIRTHDAY_SPARKLE
    else:
        chance = SPARKLE_CHANCE
    if random.random() < chance:
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


def _update_holiday(fs: FaceState, now: float) -> None:
    """Apply holiday mode overrides to face state (pre-mood-targets)."""
    mode = fs.holiday_mode
    if mode == HolidayMode.NONE:
        return

    if mode == HolidayMode.BIRTHDAY:
        fs.mood = Mood.HAPPY
        fs.expression_intensity = 1.0
        # Pink/teal color alternation
        cycle = int(now * 1.5) % 2
        fs.mood_color_override = (
            HOLIDAY_BIRTHDAY_COLOR_A if cycle == 0 else HOLIDAY_BIRTHDAY_COLOR_B
        )
        # Periodic CELEBRATE gesture
        if fs._holiday_timer == 0.0:
            fs._holiday_timer = now + HOLIDAY_BIRTHDAY_CELEBRATE_INTERVAL
        elif now >= fs._holiday_timer:
            face_trigger_gesture(fs, GestureId.CELEBRATE)
            fs._holiday_timer = now + HOLIDAY_BIRTHDAY_CELEBRATE_INTERVAL

    elif mode == HolidayMode.HALLOWEEN:
        # Orange with candlelight flicker
        flicker = 1.0 + random.uniform(
            -HOLIDAY_HALLOWEEN_FLICKER, HOLIDAY_HALLOWEEN_FLICKER
        )
        r = min(255, int(HOLIDAY_HALLOWEEN_COLOR[0] * flicker))
        g = min(255, int(HOLIDAY_HALLOWEEN_COLOR[1] * flicker))
        b = min(255, int(HOLIDAY_HALLOWEEN_COLOR[2] * flicker))
        fs.mood_color_override = (r, g, b)
        # Inverted-V eyes + mouth wave (jack-o-lantern)
        fs.eyelids.slope_target = HOLIDAY_HALLOWEEN_LID_SLOPE
        fs.mouth_wave_target = 1.0
        fs.mouth_curve_target = -0.3
        fs.mouth_open_target = 0.4

    elif mode == HolidayMode.CHRISTMAS:
        fs.mood = Mood.HAPPY
        fs.expression_intensity = 0.5
        fs.mood_color_override = HOLIDAY_CHRISTMAS_COLOR

    elif mode == HolidayMode.NEW_YEAR:
        fs.mood = Mood.EXCITED
        fs.expression_intensity = 1.0
        fs.fx.afterglow = True
        # Periodic CELEBRATE gesture
        if fs._holiday_timer == 0.0:
            fs._holiday_timer = now + 4.0
        elif now >= fs._holiday_timer:
            face_trigger_gesture(fs, GestureId.CELEBRATE)
            fs._holiday_timer = now + 4.0 + random.random() * 3.0


def _update_snow(fs: FaceState) -> None:
    """Update snowfall particles (Christmas mode)."""
    if fs.holiday_mode != HolidayMode.CHRISTMAS:
        fs.fx.snow_pixels.clear()
        return
    # Update existing snow
    fs.fx.snow_pixels = [
        (
            x + math.sin(phase + y * 0.05) * HOLIDAY_SNOW_DRIFT_AMP,
            y + HOLIDAY_SNOW_FALL_SPEED,
            life - 1,
            phase,
        )
        for x, y, life, phase in fs.fx.snow_pixels
        if life > 0 and y < SCREEN_H
    ]
    # Spawn new snow at top
    if random.random() < HOLIDAY_SNOW_SPAWN_CHANCE:
        fs.fx.snow_pixels.append(
            (
                random.randint(0, SCREEN_W),
                0.0,
                random.randint(HOLIDAY_SNOW_LIFE_MIN, HOLIDAY_SNOW_LIFE_MAX),
                random.uniform(0, 6.28),
            )
        )


def _update_confetti(fs: FaceState) -> None:
    """Update confetti particles (New Year's mode)."""
    if fs.holiday_mode != HolidayMode.NEW_YEAR:
        fs.fx.confetti_pixels.clear()
        return
    # Update existing confetti
    fs.fx.confetti_pixels = [
        (
            x + random.uniform(-HOLIDAY_CONFETTI_DRIFT, HOLIDAY_CONFETTI_DRIFT),
            y + HOLIDAY_CONFETTI_FALL_SPEED,
            life - 1,
            ci,
        )
        for x, y, life, ci in fs.fx.confetti_pixels
        if life > 0 and y < SCREEN_H
    ]
    # Spawn new confetti at top
    if random.random() < HOLIDAY_CONFETTI_SPAWN_CHANCE:
        fs.fx.confetti_pixels.append(
            (
                random.randint(0, SCREEN_W),
                0.0,
                random.randint(HOLIDAY_CONFETTI_LIFE_MIN, HOLIDAY_CONFETTI_LIFE_MAX),
                random.randint(0, len(HOLIDAY_CONFETTI_COLORS) - 1),
            )
        )


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
        fs.anim.nod = True
        fs.anim.nod_timer = now
        fs.anim.nod_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.HEADSHAKE:
        fs.anim.headshake = True
        fs.anim.headshake_timer = now
        fs.anim.headshake_duration = dur
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
    elif gesture == GestureId.PEEK_A_BOO:
        fs.anim.peek_a_boo = True
        fs.anim.peek_a_boo_timer = now
        fs.anim.peek_a_boo_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.SHY:
        fs.anim.shy = True
        fs.anim.shy_timer = now
        fs.anim.shy_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.EYE_ROLL:
        fs.anim.eye_roll = True
        fs.anim.eye_roll_timer = now
        fs.anim.eye_roll_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.DIZZY:
        fs.anim.dizzy = True
        fs.anim.dizzy_timer = now
        fs.anim.dizzy_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.CELEBRATE:
        fs.anim.celebrate = True
        fs.anim.celebrate_timer = now
        fs.anim.celebrate_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.STARTLE_RELIEF:
        fs.anim.startle_relief = True
        fs.anim.startle_relief_timer = now
        fs.anim.startle_relief_duration = dur
        _set_active_gesture(fs, gesture, dur)
    elif gesture == GestureId.THINKING_HARD:
        fs.anim.thinking_hard = True
        fs.anim.thinking_hard_timer = now
        fs.anim.thinking_hard_duration = dur
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
    # System mode color override (bypasses mood entirely)
    if fs.mood_color_override is not None:
        return fs.mood_color_override

    # Gesture overrides take priority
    if fs.anim.rage:
        mood_color = GESTURE_COLOR_RAGE
    elif fs.anim.heart:
        mood_color = GESTURE_COLOR_HEART
    elif fs.anim.x_eyes:
        mood_color = GESTURE_COLOR_X_EYES
    elif fs.anim.shy:
        mood_color = GESTURE_COLOR_SHY
    elif fs.anim.celebrate:
        # Color cycling through teal → green → warm white
        elapsed_g = time.monotonic() - fs.anim.celebrate_timer
        cycle = int(elapsed_g * 3.0) % 3
        mood_color = (
            GESTURE_COLOR_CELEBRATE_A,
            GESTURE_COLOR_CELEBRATE_B,
            GESTURE_COLOR_CELEBRATE_C,
        )[cycle]
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
