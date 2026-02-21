"""Face animation state machine v2 (Final).

Updates:
- Added timeout logic for one-shot gestures (Heart, Rage, etc).
- Tuned mood parameters.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import IntEnum


class Mood(IntEnum):
    NEUTRAL = 0
    HAPPY = 1
    EXCITED = 2
    CURIOUS = 3
    SAD = 4
    SCARED = 5
    ANGRY = 6
    SURPRISED = 7
    SLEEPY = 8
    LOVE = 9
    SILLY = 10
    THINKING = 11


class Gesture(IntEnum):
    BLINK = 0
    WINK_L = 1
    WINK_R = 2
    CONFUSED = 3
    LAUGH = 4
    SURPRISE = 5
    HEART = 6
    X_EYES = 7
    SLEEPY = 8
    RAGE = 9
    NOD = 10
    HEADSHAKE = 11
    WIGGLE = 12


class SystemMode(IntEnum):
    NONE = 0
    BOOTING = 1
    ERROR = 2
    LOW_BATTERY = 3
    UPDATING = 4
    SHUTTING_DOWN = 5


# ── Geometry constants ───────────────────────────────────────────────

SCREEN_W = 320
SCREEN_H = 240

EYE_WIDTH = 80.0
EYE_HEIGHT = 85.0
EYE_CORNER_R = 25.0
PUPIL_R = 20.0

LEFT_EYE_CX = 90.0
LEFT_EYE_CY = 85.0
RIGHT_EYE_CX = 230.0
RIGHT_EYE_CY = 85.0

# Adjusted shifts to prevent pupil leaving eye even without clamping
GAZE_EYE_SHIFT = 3.0
GAZE_PUPIL_SHIFT = 8.0
MAX_GAZE = 12.0

MOUTH_CX = 160.0
MOUTH_CY = 185.0
MOUTH_HALF_W = 60.0
MOUTH_THICKNESS = 8.0

ANIM_FPS = 30
BLINK_INTERVAL = 3.0
BLINK_VARIATION = 4.0


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

    confused: bool = False
    confused_timer: float = 0.0
    confused_toggle: bool = True

    laugh: bool = False
    laugh_timer: float = 0.0
    laugh_toggle: bool = True

    surprise: bool = False
    surprise_timer: float = 0.0

    heart: bool = False
    heart_timer: float = 0.0

    x_eyes: bool = False
    x_eyes_timer: float = 0.0

    sleepy: bool = False
    sleepy_timer: float = 0.0

    rage: bool = False
    rage_timer: float = 0.0

    h_flicker: bool = False
    h_flicker_alt: bool = False
    h_flicker_amp: float = 1.5

    v_flicker: bool = False
    v_flicker_alt: bool = False
    v_flicker_amp: float = 1.5


@dataclass
class EffectsState:
    breathing: bool = True
    breath_phase: float = 0.0
    breath_speed: float = 1.8
    breath_amount: float = 0.04
    boot_active: bool = True
    boot_timer: float = 0.0
    boot_phase: int = 0
    sparkle: bool = True
    sparkle_pixels: list = field(default_factory=list)
    sparkle_chance: float = 0.05
    fire_pixels: list = field(default_factory=list)
    afterglow: bool = True
    afterglow_buf: list | None = None
    edge_glow: bool = True
    edge_glow_falloff: float = 0.4


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
    brightness: float = 1.0
    solid_eye: bool = True
    show_mouth: bool = True

    talking: bool = False
    talking_energy: float = 0.0
    talking_phase: float = 0.0

    mouth_curve: float = 0.2
    mouth_curve_target: float = 0.2
    mouth_open: float = 0.0
    mouth_open_target: float = 0.0
    mouth_wave: float = 0.0
    mouth_wave_target: float = 0.0
    mouth_offset_x: float = 0.0
    mouth_offset_x_target: float = 0.0
    mouth_width: float = 1.0
    mouth_width_target: float = 1.0


def _tween(current: float, target: float, speed: float) -> float:
    return current + (target - current) * speed


def _spring(
    current: float, target: float, vel: float, k: float = 0.2, d: float = 0.7
) -> tuple[float, float]:
    force = (target - current) * k
    vel = (vel + force) * d
    return current + vel, vel


def face_state_update(fs: FaceState) -> None:
    now = time.monotonic()
    dt = 0.033

    if _update_system(fs):
        return

    if fs.fx.boot_active:
        if fs.fx.boot_timer == 0.0:
            fs.fx.boot_timer = now
        _update_boot(fs)
        _update_breathing(fs)
        return

    # ── 1. MOOD TARGETS ──────────────────────────────────────────────
    t_curve = 0.2
    t_width = 1.0
    t_open = 0.0
    t_lid_slope = 0.0
    t_lid_top = 0.0
    t_lid_bot = 0.0

    m = fs.mood
    if m == Mood.NEUTRAL:
        t_curve, t_lid_top = 0.1, 0.0
    elif m == Mood.HAPPY:
        t_curve = 0.8  # Positive = Smile
        t_lid_bot = 0.4
        t_width = 1.1
    elif m == Mood.EXCITED:
        t_curve = 0.9
        t_open = 0.2
        t_lid_bot = 0.3
        t_width = 1.2
    elif m == Mood.CURIOUS:
        t_curve = 0.0
        t_lid_slope = -0.3
        t_width = 0.9
    elif m == Mood.SAD:
        t_curve = -0.5  # Negative = Frown
        t_lid_slope = -0.6
        t_lid_top = 0.3
    elif m == Mood.SCARED:
        t_curve = -0.3
        t_open = 0.3
        t_lid_top = 0.0
        t_width = 0.8
        fs.eye_l.width_scale_target = 0.9
        fs.eye_r.width_scale_target = 0.9
    elif m == Mood.ANGRY:
        t_curve = -0.6
        t_lid_slope = 0.8
        t_lid_top = 0.4
    elif m == Mood.SURPRISED:
        t_curve = 0.0
        t_open = 0.6
        t_width = 0.4
        fs.eye_l.width_scale_target = 1.2
        fs.eye_l.height_scale_target = 1.2
        fs.eye_r.width_scale_target = 1.2
        fs.eye_r.height_scale_target = 1.2
    elif m == Mood.SLEEPY:
        t_curve = 0.0
        t_lid_top = 0.6
        t_lid_slope = -0.2
    elif m == Mood.LOVE:
        t_curve = 0.6
        t_lid_bot = 0.3
    elif m == Mood.SILLY:
        t_curve = 0.5
        t_width = 1.1
        t_lid_slope = 0.0
    elif m == Mood.THINKING:
        t_curve = -0.1
        t_lid_slope = 0.4
        t_lid_top = 0.2

    fs.mouth_curve_target = t_curve
    fs.mouth_width_target = t_width
    fs.mouth_open_target = t_open
    fs.mouth_offset_x_target = 0.0
    fs.eyelids.slope_target = t_lid_slope

    # Thinking: gaze up-and-aside + mouth offset
    if m == Mood.THINKING:
        fs.mouth_offset_x_target = 1.5
        fs.eye_l.gaze_x_target = 6.0
        fs.eye_l.gaze_y_target = -4.0
        fs.eye_r.gaze_x_target = 6.0
        fs.eye_r.gaze_y_target = -4.0

    # ── 2. GESTURE OVERRIDES ────────────────────────────────────────
    if fs.anim.surprise:
        elapsed_g = now - fs.anim.surprise_timer
        # Widen eyes during surprise
        if elapsed_g < 0.15:
            fs.eye_l.width_scale_target = 1.3
            fs.eye_l.height_scale_target = 1.25
            fs.eye_r.width_scale_target = 1.3
            fs.eye_r.height_scale_target = 1.25
        # O-mouth
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = 0.6
        fs.mouth_width_target = 0.5

    if fs.anim.laugh:
        # Chatter mouth
        fs.mouth_curve_target = 1.0
        elapsed_g = now - fs.anim.laugh_timer
        chatter = 0.2 + 0.3 * max(0.0, math.sin(elapsed_g * 50.0))
        fs.mouth_open_target = max(fs.mouth_open_target, chatter)

    if fs.anim.rage:
        # Slam eyelids + shake + snarl
        elapsed_g = now - fs.anim.rage_timer
        fs.eyelids.slope_target = 0.9
        t_lid_top = max(t_lid_top, 0.4)
        shake = math.sin(elapsed_g * 30.0) * 0.4
        fs.eye_l.gaze_x_target = shake
        fs.eye_r.gaze_x_target = shake
        fs.mouth_curve_target = -1.0
        fs.mouth_open_target = 0.3
        fs.mouth_wave_target = 0.7

    if fs.anim.x_eyes:
        # O-mouth for KO
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = 0.8
        fs.mouth_width_target = 0.5

    if fs.anim.heart:
        # Big smile
        fs.mouth_curve_target = 1.0
        fs.mouth_open_target = 0.0

    if fs.anim.sleepy:
        # Droop lids + sway + yawn
        elapsed_g = now - fs.anim.sleepy_timer
        droop = min(1.0, elapsed_g / 1.5)
        t_lid_top = max(t_lid_top, droop * 0.6)
        fs.eyelids.slope_target = -0.2
        sway = math.sin(elapsed_g * 2.0) * 6.0
        fs.eye_l.gaze_x_target = sway
        fs.eye_r.gaze_x_target = sway
        fs.eye_l.gaze_y_target = droop * 3.0
        fs.eye_r.gaze_y_target = droop * 3.0
        # Yawn sequence
        dur = 3.0
        ys, yp, ye = dur * 0.2, dur * 0.4, dur * 0.7
        if elapsed_g < ys:
            pass
        elif elapsed_g < yp:
            fs.mouth_open_target = (elapsed_g - ys) / (yp - ys)
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = 0.7
        elif elapsed_g < ye:
            fs.mouth_open_target = 1.0
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = 0.7
        else:
            t2 = (elapsed_g - ye) / (dur - ye)
            fs.mouth_open_target = max(0.0, 1.0 - t2 * 1.5)

    if fs.anim.confused:
        # Smirk
        elapsed_g = now - fs.anim.confused_timer
        fs.mouth_offset_x_target = 1.5 * math.sin(elapsed_g * 12.0)
        fs.mouth_curve_target = -0.2
        fs.mouth_open_target = 0.0

    # ── 3. TIMEOUTS ─────────────────────────────────────────────────
    if fs.anim.heart and now > fs.anim.heart_timer + 2.0:
        fs.anim.heart = False

    if fs.anim.x_eyes and now > fs.anim.x_eyes_timer + 2.5:
        fs.anim.x_eyes = False

    if fs.anim.rage and now > fs.anim.rage_timer + 3.0:
        fs.anim.rage = False
        fs.fx.fire_pixels.clear()

    if fs.anim.surprise and now > fs.anim.surprise_timer + 1.0:
        fs.anim.surprise = False

    if fs.anim.sleepy:
        elapsed_sl = now - fs.anim.sleepy_timer
        if elapsed_sl >= 3.0:
            fs.anim.sleepy = False

    if fs.anim.confused:
        if fs.anim.confused_toggle:
            fs.anim.h_flicker = True
            fs.anim.h_flicker_amp = 1.5
            fs.anim.confused_toggle = False
        if now > fs.anim.confused_timer + 0.5:
            fs.anim.confused = False
            fs.anim.h_flicker = False
            fs.anim.confused_toggle = True

    if fs.anim.laugh:
        if fs.anim.laugh_toggle:
            fs.anim.v_flicker = True
            fs.anim.v_flicker_amp = 1.5
            fs.anim.laugh_toggle = False
        if now > fs.anim.laugh_timer + 0.5:
            fs.anim.laugh = False
            fs.anim.v_flicker = False
            fs.anim.laugh_toggle = True

    # ── 4. BLINK LOGIC ───────────────────────────────────────────────
    if fs.anim.autoblink and now >= fs.anim.next_blink:
        face_blink(fs)
        fs.anim.next_blink = now + BLINK_INTERVAL + random.random() * BLINK_VARIATION

    # Per-eye blink/wink closure
    if not fs.eye_l.is_open and fs.eyelids.top_l > 0.95:
        fs.eye_l.is_open = True
    if not fs.eye_r.is_open and fs.eyelids.top_r > 0.95:
        fs.eye_r.is_open = True

    closure_l = 1.0 if not fs.eye_l.is_open else 0.0
    closure_r = 1.0 if not fs.eye_r.is_open else 0.0
    final_top_l = max(t_lid_top, closure_l)
    final_top_r = max(t_lid_top, closure_r)

    speed_l = 0.6 if final_top_l > fs.eyelids.top_l else 0.4
    speed_r = 0.6 if final_top_r > fs.eyelids.top_r else 0.4
    fs.eyelids.top_l = _tween(fs.eyelids.top_l, final_top_l, speed_l)
    fs.eyelids.top_r = _tween(fs.eyelids.top_r, final_top_r, speed_r)
    fs.eyelids.bottom_l = _tween(fs.eyelids.bottom_l, t_lid_bot, 0.3)
    fs.eyelids.bottom_r = _tween(fs.eyelids.bottom_r, t_lid_bot, 0.3)
    fs.eyelids.slope = _tween(fs.eyelids.slope, fs.eyelids.slope_target, 0.3)

    # ── 5. IDLE & PHYSICS ────────────────────────────────────────────
    if fs.anim.idle and now >= fs.anim.next_idle:
        target_x = random.uniform(-MAX_GAZE, MAX_GAZE)
        target_y = random.uniform(-MAX_GAZE * 0.6, MAX_GAZE * 0.6)

        if fs.mood == Mood.SILLY:
            if random.random() < 0.5:
                fs.eye_l.gaze_x_target = 8.0
                fs.eye_r.gaze_x_target = -8.0
            else:
                fs.eye_l.gaze_x_target = -6.0
                fs.eye_r.gaze_x_target = 6.0
        else:
            fs.eye_l.gaze_x_target = target_x
            fs.eye_r.gaze_x_target = target_x

        fs.eye_l.gaze_y_target = target_y
        fs.eye_r.gaze_y_target = target_y
        fs.anim.next_idle = now + 1.0 + random.random() * 2.0

    if now > fs.anim.next_saccade:
        jitter_x = random.uniform(-0.5, 0.5)
        jitter_y = random.uniform(-0.5, 0.5)
        fs.eye_l.gaze_x += jitter_x
        fs.eye_r.gaze_x += jitter_x
        fs.eye_l.gaze_y += jitter_y
        fs.eye_r.gaze_y += jitter_y
        fs.anim.next_saccade = now + random.uniform(0.1, 0.4)

    # ── 6. TALKING ───────────────────────────────────────────────────
    if fs.talking:
        e = fs.talking_energy
        # Phase speed coupling: faster chatter at higher energy
        phase_speed = 12.0 + 6.0 * e
        fs.talking_phase += phase_speed * dt
        noise_open = math.sin(fs.talking_phase) + math.sin(fs.talking_phase * 2.3)
        noise_width = math.cos(fs.talking_phase * 0.7)

        base_open = 0.2 + 0.5 * e
        mod_open = abs(noise_open) * 0.6 * e
        base_width = 1.0
        mod_width = noise_width * 0.3 * e

        fs.mouth_open_target = max(fs.mouth_open_target, base_open + mod_open)
        fs.mouth_width_target = base_width + mod_width

        bounce = abs(math.sin(fs.talking_phase)) * 0.05 * e
        fs.eye_l.height_scale_target += bounce
        fs.eye_r.height_scale_target += bounce

    # ── 7. UPDATE TWEENS ─────────────────────────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        eye.gaze_x, eye.vx = _spring(eye.gaze_x, eye.gaze_x_target, eye.vx, 0.25, 0.65)
        eye.gaze_y, eye.vy = _spring(eye.gaze_y, eye.gaze_y_target, eye.vy, 0.25, 0.65)
        eye.width_scale = _tween(eye.width_scale, eye.width_scale_target, 0.2)
        eye.height_scale = _tween(eye.height_scale, eye.height_scale_target, 0.2)
        eye.width_scale_target = 1.0
        eye.height_scale_target = 1.0

    fs.mouth_curve = _tween(fs.mouth_curve, fs.mouth_curve_target, 0.2)
    fs.mouth_open = _tween(fs.mouth_open, fs.mouth_open_target, 0.4)
    fs.mouth_width = _tween(fs.mouth_width, fs.mouth_width_target, 0.2)
    fs.mouth_offset_x = _tween(fs.mouth_offset_x, fs.mouth_offset_x_target, 0.2)
    fs.mouth_wave = _tween(fs.mouth_wave, fs.mouth_wave_target, 0.1)

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


def _update_boot(fs: FaceState) -> None:
    now = time.monotonic()
    elapsed = now - fs.fx.boot_timer
    if elapsed < 1.0:
        val = elapsed
        val = 1.0 - (1.0 - val) ** 3
        fs.eyelids.top_l = 1.0 - val
        fs.eyelids.top_r = 1.0 - val
    else:
        fs.fx.boot_active = False


def _update_breathing(fs: FaceState) -> None:
    if fs.fx.breathing:
        fs.fx.breath_phase += 2.0 / 30.0
        if fs.fx.breath_phase > 6.28:
            fs.fx.breath_phase -= 6.28


def _update_sparkle(fs: FaceState) -> None:
    if not fs.fx.sparkle:
        fs.fx.sparkle_pixels.clear()
        return
    fs.fx.sparkle_pixels = [
        (x, y, life - 1) for x, y, life in fs.fx.sparkle_pixels if life > 0
    ]
    if random.random() < fs.fx.sparkle_chance:
        fs.fx.sparkle_pixels.append(
            (
                random.randint(0, SCREEN_W),
                random.randint(0, SCREEN_H),
                random.randint(5, 15),
            )
        )


def _update_fire(fs: FaceState) -> None:
    if not fs.anim.rage:
        fs.fx.fire_pixels.clear()
        return
    fs.fx.fire_pixels = [
        (x + random.uniform(-1.5, 1.5), y - 3.0, life - 1, heat * 0.9)
        for x, y, life, heat in fs.fx.fire_pixels
        if life > 1 and y > 0
    ]
    if random.random() < 0.3:
        for cx in (LEFT_EYE_CX, RIGHT_EYE_CX):
            x = cx + random.uniform(-20, 20)
            y = LEFT_EYE_CY - 30
            fs.fx.fire_pixels.append((x, y, random.randint(5, 15), 1.0))


def _update_system(fs: FaceState) -> bool:
    if fs.system.mode == SystemMode.NONE:
        return False
    return True


def face_blink(fs: FaceState) -> None:
    fs.eye_l.is_open = False
    fs.eye_r.is_open = False


def face_wink_left(fs: FaceState) -> None:
    fs.eye_l.is_open = False


def face_wink_right(fs: FaceState) -> None:
    fs.eye_r.is_open = False


def face_set_mood(fs: FaceState, mood: Mood) -> None:
    fs.mood = mood


def face_trigger_gesture(fs: FaceState, gst: Gesture) -> None:
    now = time.monotonic()
    if gst == Gesture.BLINK:
        face_blink(fs)
    elif gst == Gesture.WINK_L:
        face_wink_left(fs)
    elif gst == Gesture.WINK_R:
        face_wink_right(fs)
    elif gst == Gesture.NOD:
        fs.anim.laugh = True
        fs.anim.laugh_timer = now
        fs.anim.laugh_toggle = True
    elif gst == Gesture.HEADSHAKE:
        fs.anim.confused = True
        fs.anim.confused_timer = now
        fs.anim.confused_toggle = True
    elif gst == Gesture.WIGGLE:
        fs.anim.confused = True
        fs.anim.confused_timer = now
        fs.anim.confused_toggle = True
        fs.anim.laugh = True
        fs.anim.laugh_timer = now
        fs.anim.laugh_toggle = True
    elif gst == Gesture.LAUGH:
        fs.anim.laugh = True
        fs.anim.laugh_timer = now
        fs.anim.laugh_toggle = True
    elif gst == Gesture.CONFUSED:
        fs.anim.confused = True
        fs.anim.confused_timer = now
        fs.anim.confused_toggle = True
    elif gst == Gesture.RAGE:
        fs.anim.rage = True
        fs.anim.rage_timer = now
    elif gst == Gesture.HEART:
        fs.anim.heart = True
        fs.anim.heart_timer = now
    elif gst == Gesture.X_EYES:
        fs.anim.x_eyes = True
        fs.anim.x_eyes_timer = now
    elif gst == Gesture.SLEEPY:
        fs.anim.sleepy = True
        fs.anim.sleepy_timer = now
    elif gst == Gesture.SURPRISE:
        fs.anim.surprise = True
        fs.anim.surprise_timer = now


def face_set_gaze(fs: FaceState, x: float, y: float) -> None:
    fs.eye_l.gaze_x_target = x
    fs.eye_l.gaze_y_target = y
    fs.eye_r.gaze_x_target = x
    fs.eye_r.gaze_y_target = y


def face_set_system_mode(fs: FaceState, mode: SystemMode, param: float = 0.0) -> None:
    fs.system.mode = mode
    fs.system.timer = time.monotonic()
    fs.system.param = param


def get_breath_scale(fs: FaceState) -> float:
    return 1.0 + math.sin(fs.fx.breath_phase) * fs.fx.breath_amount


def get_emotion_color(fs: FaceState) -> tuple[int, int, int]:
    m = fs.mood
    if fs.anim.rage:
        return (255, 30, 0)
    if fs.anim.heart:
        return (255, 105, 180)
    if fs.anim.x_eyes:
        return (200, 40, 40)

    if m == Mood.HAPPY:
        return (0, 255, 200)
    if m == Mood.EXCITED:
        return (100, 255, 100)
    if m == Mood.CURIOUS:
        return (255, 180, 50)
    if m == Mood.SAD:
        return (50, 80, 200)
    if m == Mood.SCARED:
        return (180, 50, 255)
    if m == Mood.ANGRY:
        return (255, 0, 0)
    if m == Mood.SURPRISED:
        return (255, 255, 200)
    if m == Mood.SLEEPY:
        return (40, 60, 100)
    if m == Mood.LOVE:
        return (255, 100, 150)
    if m == Mood.SILLY:
        return (200, 255, 50)
    return (50, 150, 255)
