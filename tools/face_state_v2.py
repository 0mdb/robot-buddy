"""Face animation state machine v2.

Matches the ESP32 face-display firmware (esp32-face-display/main/face_state.h/.cpp)
with 12 moods, 13 gestures, talking state, and 240x320 TFT geometry.

All coordinates are in abstract units; rendering maps them to the 240x320 canvas.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import IntEnum

# ── Mood enum (12 emotions) ─────────────────────────────────────────

class Mood(IntEnum):
    NEUTRAL   = 0
    HAPPY     = 1
    EXCITED   = 2
    CURIOUS   = 3
    SAD       = 4
    SCARED    = 5
    ANGRY     = 6
    SURPRISED = 7
    SLEEPY    = 8
    LOVE      = 9
    SILLY     = 10
    THINKING  = 11


# ── Gesture enum (13 one-shot animations) ────────────────────────────

class Gesture(IntEnum):
    BLINK     = 0
    WINK_L    = 1
    WINK_R    = 2
    CONFUSED  = 3
    LAUGH     = 4
    SURPRISE  = 5
    HEART     = 6
    X_EYES    = 7
    SLEEPY    = 8
    RAGE      = 9
    NOD       = 10
    HEADSHAKE = 11
    WIGGLE    = 12


class SystemMode(IntEnum):
    NONE          = 0
    BOOTING       = 1
    ERROR         = 2
    LOW_BATTERY   = 3
    UPDATING      = 4
    SHUTTING_DOWN = 5


# ── Geometry constants (matching config.h) ───────────────────────────

SCREEN_W = 320
SCREEN_H = 240

EYE_WIDTH      = 70.0
EYE_HEIGHT     = 70.0
EYE_CORNER_R   = 20.0
PUPIL_R        = 18.0

LEFT_EYE_CX    = 90.0
LEFT_EYE_CY    = 85.0
RIGHT_EYE_CX   = 230.0
RIGHT_EYE_CY   = 85.0

GAZE_EYE_SHIFT   = 2.0
GAZE_PUPIL_SHIFT = 6.0
MAX_GAZE         = 4.0

MOUTH_CX        = 160.0
MOUTH_CY        = 185.0
MOUTH_HALF_W    = 55.0
MOUTH_THICKNESS = 6.0

ANIM_FPS        = 30
BLINK_INTERVAL  = 2.0
BLINK_VARIATION = 3.0
IDLE_INTERVAL   = 1.5
IDLE_VARIATION  = 2.5
BREATH_SPEED    = 1.8
BREATH_AMOUNT   = 0.04


# ── Per-eye state ────────────────────────────────────────────────────

@dataclass
class EyeState:
    openness: float = 0.0
    openness_target: float = 1.0
    is_open: bool = True

    gaze_x: float = 0.0
    gaze_x_target: float = 0.0
    gaze_y: float = 0.0
    gaze_y_target: float = 0.0

    width_scale: float = 1.0
    width_scale_target: float = 1.0
    height_scale: float = 1.0
    height_scale_target: float = 1.0


# ── Eyelid overlay state ────────────────────────────────────────────

@dataclass
class EyelidState:
    tired: float = 0.0
    tired_target: float = 0.0
    angry: float = 0.0
    angry_target: float = 0.0
    happy: float = 0.0
    happy_target: float = 0.0


# ── Animation timers ────────────────────────────────────────────────

@dataclass
class AnimTimers:
    autoblink: bool = True
    next_blink: float = 0.0

    idle: bool = True
    next_idle: float = 0.0

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


# ── Effects state ────────────────────────────────────────────────────

@dataclass
class EffectsState:
    breathing: bool = True
    breath_phase: float = 0.0

    boot_active: bool = True
    boot_timer: float = 0.0
    boot_phase: int = 0

    # Sparkle (visual polish, not in firmware yet)
    sparkle: bool = True
    sparkle_pixels: list = field(default_factory=list)
    sparkle_chance: float = 0.02

    # Fire particles (rage gesture)
    fire_pixels: list = field(default_factory=list)

    # Afterglow (blink fade)
    afterglow: bool = True
    afterglow_buf: list | None = None

    # Edge glow
    edge_glow: bool = True
    edge_glow_falloff: float = 0.35


# ── System display state ────────────────────────────────────────────

@dataclass
class SystemState:
    mode: SystemMode = SystemMode.NONE
    timer: float = 0.0
    phase: int = 0
    param: float = 0.0


# ── Top-level face state ────────────────────────────────────────────

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


# ── Tweening ─────────────────────────────────────────────────────────

def _tween(current: float, target: float, speed: float = 0.5) -> float:
    return current + (target - current) * speed


# ── Boot-up sequence ─────────────────────────────────────────────────

def _update_boot(fs: FaceState) -> None:
    now = time.monotonic()
    elapsed = now - fs.fx.boot_timer

    if fs.fx.boot_phase == 0:
        progress = min(1.0, elapsed / 1.0)
        eased = 1.0 - (1.0 - progress) ** 2
        fs.eye_l.openness = eased
        fs.eye_r.openness = eased
        fs.eye_l.openness_target = eased
        fs.eye_r.openness_target = eased
        if progress >= 1.0:
            fs.fx.boot_phase = 1
            fs.fx.boot_timer = now

    elif fs.fx.boot_phase == 1:
        if elapsed < 0.3:
            t = elapsed / 0.3
            fs.eye_l.openness = 1.0 - t
            fs.eye_r.openness = 1.0 - t
        elif elapsed < 0.5:
            fs.eye_l.openness = 0.0
            fs.eye_r.openness = 0.0
        elif elapsed < 0.9:
            t = (elapsed - 0.5) / 0.4
            fs.eye_l.openness = t
            fs.eye_r.openness = t
        else:
            fs.eye_l.openness = 1.0
            fs.eye_r.openness = 1.0
            fs.eye_l.openness_target = 1.0
            fs.eye_r.openness_target = 1.0
            fs.fx.boot_phase = 2
            fs.fx.boot_timer = now

    elif fs.fx.boot_phase == 2:
        if elapsed < 0.5:
            gx = -2.0 * (elapsed / 0.5)
        elif elapsed < 1.2:
            gx = -2.0 + 4.0 * ((elapsed - 0.5) / 0.7)
        elif elapsed < 1.8:
            gx = 2.0 * (1.0 - (elapsed - 1.2) / 0.6)
        else:
            gx = 0.0
            fs.fx.boot_active = False
        for eye in (fs.eye_l, fs.eye_r):
            eye.gaze_x = gx
            eye.gaze_x_target = gx
            eye.gaze_y = 0.0
            eye.gaze_y_target = 0.0


# ── State update ─────────────────────────────────────────────────────

def face_state_update(fs: FaceState) -> None:
    now = time.monotonic()

    if _update_system(fs):
        return

    if fs.fx.boot_active:
        if fs.fx.boot_timer == 0.0:
            fs.fx.boot_timer = now
        _update_boot(fs)
        _update_breathing(fs)
        return

    # ── Mood → eyelid targets (matches face_state.cpp) ────────────
    fs.eyelids.tired_target = (
        1.0 if fs.mood in (Mood.SAD, Mood.SLEEPY, Mood.THINKING) else 0.0
    )
    fs.eyelids.angry_target = (
        1.0 if fs.mood in (Mood.ANGRY, Mood.SCARED) else 0.0
    )
    fs.eyelids.happy_target = (
        1.0 if fs.mood in (Mood.HAPPY, Mood.EXCITED, Mood.LOVE, Mood.SILLY) else 0.0
    )

    # ── Mood → mouth targets ─────────────────────────────────────
    if fs.mood in (Mood.HAPPY, Mood.EXCITED, Mood.LOVE, Mood.SILLY):
        fs.mouth_curve_target = 0.8
    elif fs.mood in (Mood.ANGRY, Mood.SCARED):
        fs.mouth_curve_target = -0.6
    elif fs.mood in (Mood.SAD, Mood.SLEEPY):
        fs.mouth_curve_target = -0.3
    elif fs.mood in (Mood.CURIOUS, Mood.THINKING):
        fs.mouth_curve_target = 0.1
    elif fs.mood == Mood.SURPRISED:
        fs.mouth_curve_target = 0.0
    else:
        fs.mouth_curve_target = 0.2

    # ── Auto-blink ───────────────────────────────────────────────
    if fs.anim.autoblink and now >= fs.anim.next_blink:
        face_blink(fs)
        fs.anim.next_blink = now + BLINK_INTERVAL + random.random() * BLINK_VARIATION

    # ── Re-open after blink ──────────────────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        if eye.is_open and eye.openness < 0.05:
            eye.openness_target = 1.0
        if not eye.is_open:
            eye.openness_target = 0.0

    # ── Idle gaze wander ─────────────────────────────────────────
    if fs.anim.idle and now >= fs.anim.next_idle:
        gx = random.uniform(-MAX_GAZE, MAX_GAZE)
        gy = random.uniform(-MAX_GAZE * 0.6, MAX_GAZE * 0.6)
        for eye in (fs.eye_l, fs.eye_r):
            eye.gaze_x_target = gx
            eye.gaze_y_target = gy
        fs.anim.next_idle = now + IDLE_INTERVAL + random.random() * IDLE_VARIATION

    # ── Confused (horizontal shake) ──────────────────────────────
    if fs.anim.confused:
        if fs.anim.confused_toggle:
            fs.anim.h_flicker = True
            fs.anim.h_flicker_amp = 1.5
            fs.anim.confused_timer = now
            fs.anim.confused_toggle = False
        elif now >= fs.anim.confused_timer + 0.5:
            fs.anim.h_flicker = False
            fs.anim.confused_toggle = True
            fs.anim.confused = False

    # ── Laugh (vertical shake) ───────────────────────────────────
    if fs.anim.laugh:
        if fs.anim.laugh_toggle:
            fs.anim.v_flicker = True
            fs.anim.v_flicker_amp = 1.5
            fs.anim.laugh_timer = now
            fs.anim.laugh_toggle = False
        elif now >= fs.anim.laugh_timer + 0.5:
            fs.anim.v_flicker = False
            fs.anim.laugh_toggle = True
            fs.anim.laugh = False

    # ── Surprise ─────────────────────────────────────────────────
    if fs.anim.surprise:
        elapsed = now - fs.anim.surprise_timer
        if elapsed < 0.15:
            for eye in (fs.eye_l, fs.eye_r):
                eye.width_scale_target = 1.3
                eye.height_scale_target = 1.25
        elif elapsed < 0.8:
            for eye in (fs.eye_l, fs.eye_r):
                eye.width_scale_target = 1.0
                eye.height_scale_target = 1.0
        else:
            for eye in (fs.eye_l, fs.eye_r):
                eye.width_scale_target = 1.0
                eye.height_scale_target = 1.0
            fs.anim.surprise = False

    # ── Heart ────────────────────────────────────────────────────
    if fs.anim.heart and now >= fs.anim.heart_timer + 2.0:
        fs.anim.heart = False

    # ── X eyes ───────────────────────────────────────────────────
    if fs.anim.x_eyes and now >= fs.anim.x_eyes_timer + 1.5:
        fs.anim.x_eyes = False

    # ── Rage ─────────────────────────────────────────────────────
    if fs.anim.rage:
        elapsed = now - fs.anim.rage_timer
        if elapsed < 3.0:
            fs.eyelids.angry_target = 1.0
            shake = math.sin(elapsed * 30.0) * 0.4
            for eye in (fs.eye_l, fs.eye_r):
                eye.gaze_x_target = shake
        else:
            fs.eyelids.angry_target = 0.0
            fs.anim.rage = False
            fs.fx.fire_pixels.clear()

    # ── Sleepy ───────────────────────────────────────────────────
    if fs.anim.sleepy:
        elapsed = now - fs.anim.sleepy_timer
        if elapsed < 3.0:
            droop = min(1.0, elapsed / 1.5)
            fs.eyelids.tired_target = droop
            sway = math.sin(elapsed * 2.0) * 1.5
            for eye in (fs.eye_l, fs.eye_r):
                eye.gaze_x_target = sway
                eye.gaze_y_target = droop
        else:
            fs.eyelids.tired_target = 0.0
            fs.anim.sleepy = False

    # ── Gesture → mouth overrides ────────────────────────────────
    fs.mouth_wave_target = 0.0
    fs.mouth_offset_x_target = 0.0
    fs.mouth_width_target = 1.0

    if fs.anim.surprise:
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = 0.8
        fs.mouth_width_target = 0.5
    elif fs.anim.laugh:
        fs.mouth_curve_target = 1.0
        elapsed = now - fs.anim.laugh_timer
        chatter = 0.2 + 0.3 * max(0.0, math.sin(elapsed * 50.0))
        fs.mouth_open = chatter
        fs.mouth_open_target = chatter
    elif fs.anim.heart:
        fs.mouth_curve_target = 1.0
        fs.mouth_open_target = 0.0
    elif fs.anim.rage:
        fs.mouth_curve_target = -1.0
        fs.mouth_open_target = 0.3
        fs.mouth_wave_target = 0.7
    elif fs.anim.x_eyes:
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = 0.8
        fs.mouth_width_target = 0.5
    elif fs.anim.sleepy:
        elapsed = now - fs.anim.sleepy_timer
        dur = 3.0
        ys, yp, ye = dur * 0.2, dur * 0.4, dur * 0.7
        if elapsed < ys:
            fs.mouth_open_target = 0.0
        elif elapsed < yp:
            fs.mouth_open_target = (elapsed - ys) / (yp - ys)
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = 0.7
        elif elapsed < ye:
            fs.mouth_open_target = 1.0
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = 0.7
        else:
            t = (elapsed - ye) / (dur - ye)
            fs.mouth_open_target = max(0.0, 1.0 - t * 1.5)
    elif fs.anim.confused:
        elapsed = now - fs.anim.confused_timer
        fs.mouth_offset_x_target = 1.5 * math.sin(elapsed * 12.0)
        fs.mouth_curve_target = -0.2
        fs.mouth_open_target = 0.0
    else:
        fs.mouth_open_target = 0.0

    # ── Talking animation (matches face_state.cpp) ───────────────
    if fs.talking:
        e = max(0.0, min(1.0, fs.talking_energy))
        chatter = 0.18 + (0.72 * e) * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(now * 28.0)))
        fs.mouth_open_target = max(fs.mouth_open_target, chatter)
        fs.mouth_width_target = max(fs.mouth_width_target, 1.0 + 0.08 * e)
        pulse = 0.015 + 0.035 * e
        y_pulse = pulse * math.sin(now * 8.0)
        fs.eye_l.height_scale_target = max(0.8, fs.eye_l.height_scale_target + y_pulse)
        fs.eye_r.height_scale_target = max(0.8, fs.eye_r.height_scale_target + y_pulse)

    # ── Squash & stretch on blink ────────────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        if eye.openness_target < 0.1 and eye.openness > 0.3:
            eye.width_scale_target = 1.15
            eye.height_scale_target = 0.85
        elif eye.openness_target > 0.9 and eye.openness < 0.7:
            eye.width_scale_target = 0.9
            eye.height_scale_target = 1.1
        elif eye.openness > 0.9:
            eye.width_scale_target = 1.0
            eye.height_scale_target = 1.0

    # ── Tween all continuous values ──────────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        eye.openness = _tween(eye.openness, eye.openness_target)
        eye.gaze_x = _tween(eye.gaze_x, eye.gaze_x_target, 0.35)
        eye.gaze_y = _tween(eye.gaze_y, eye.gaze_y_target, 0.35)
        eye.width_scale = _tween(eye.width_scale, eye.width_scale_target, 0.3)
        eye.height_scale = _tween(eye.height_scale, eye.height_scale_target, 0.3)

    fs.eyelids.tired = _tween(fs.eyelids.tired, fs.eyelids.tired_target)
    fs.eyelids.angry = _tween(fs.eyelids.angry, fs.eyelids.angry_target)
    fs.eyelids.happy = _tween(fs.eyelids.happy, fs.eyelids.happy_target)

    fs.mouth_curve = _tween(fs.mouth_curve, fs.mouth_curve_target, 0.25)
    fs.mouth_open = _tween(fs.mouth_open, fs.mouth_open_target, 0.3)
    fs.mouth_wave = _tween(fs.mouth_wave, fs.mouth_wave_target, 0.3)
    fs.mouth_offset_x = _tween(fs.mouth_offset_x, fs.mouth_offset_x_target, 0.25)
    fs.mouth_width = _tween(fs.mouth_width, fs.mouth_width_target, 0.25)

    # ── Flicker offsets ──────────────────────────────────────────
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

    # ── Effects ──────────────────────────────────────────────────
    _update_breathing(fs)
    _update_sparkle(fs)
    _update_fire(fs)


# ── Effects helpers ──────────────────────────────────────────────────

def _update_breathing(fs: FaceState) -> None:
    if not fs.fx.breathing:
        return
    fs.fx.breath_phase += BREATH_SPEED / ANIM_FPS
    if fs.fx.breath_phase > math.tau:
        fs.fx.breath_phase -= math.tau


def _update_sparkle(fs: FaceState) -> None:
    if not fs.fx.sparkle:
        fs.fx.sparkle_pixels.clear()
        return
    fs.fx.sparkle_pixels = [
        (x, y, life - 1) for x, y, life in fs.fx.sparkle_pixels if life > 1
    ]
    if random.random() < fs.fx.sparkle_chance:
        x = random.randint(0, SCREEN_W - 1)
        y = random.randint(0, SCREEN_H - 1)
        life = random.randint(4, 12)
        fs.fx.sparkle_pixels.append((x, y, life))


def _update_fire(fs: FaceState) -> None:
    if not fs.anim.rage:
        fs.fx.fire_pixels.clear()
        return
    fs.fx.fire_pixels = [
        (x + random.uniform(-1.5, 1.5), y - 3.0, life - 1, heat * 0.9)
        for x, y, life, heat in fs.fx.fire_pixels if life > 1 and y > 0
    ]
    for ecx in (LEFT_EYE_CX, RIGHT_EYE_CX):
        for _ in range(3):
            if random.random() < 0.7:
                x = ecx + random.uniform(-30, 30)
                y = LEFT_EYE_CY - EYE_HEIGHT / 2 + random.uniform(-10, 15)
                life = random.randint(4, 10)
                heat = random.uniform(0.7, 1.0)
                fs.fx.fire_pixels.append((x, y, life, heat))


def get_breath_scale(fs: FaceState) -> float:
    if not fs.fx.breathing:
        return 1.0
    return 1.0 + math.sin(fs.fx.breath_phase) * BREATH_AMOUNT


def get_emotion_color(fs: FaceState) -> tuple[int, int, int]:
    """Return eye color for current mood/gesture (matches face_state.cpp)."""
    if fs.anim.rage:
        flicker = random.randint(-20, 20)
        return (min(255, max(0, 230 + flicker)), max(0, 30 + flicker), 0)
    if fs.anim.heart:
        return (255, 60, 140)
    if fs.anim.x_eyes:
        return (200, 40, 40)
    if fs.anim.surprise:
        elapsed = time.monotonic() - fs.anim.surprise_timer
        if elapsed < 0.15:
            return (200, 220, 255)

    colors = {
        Mood.HAPPY:     (50, 180, 255),
        Mood.EXCITED:   (80, 220, 255),
        Mood.CURIOUS:   (40, 160, 240),
        Mood.SAD:       (20, 60, 160),
        Mood.SCARED:    (100, 60, 200),
        Mood.ANGRY:     (60, 80, 220),
        Mood.SURPRISED: (200, 220, 255),
        Mood.SLEEPY:    (20, 40, 120),
        Mood.LOVE:      (255, 100, 180),
        Mood.SILLY:     (180, 255, 100),
        Mood.THINKING:  (60, 120, 200),
    }
    return colors.get(fs.mood, (30, 120, 255))


# ── Convenience triggers ─────────────────────────────────────────────

def face_blink(fs: FaceState) -> None:
    fs.eye_l.openness_target = 0.0
    fs.eye_r.openness_target = 0.0
    fs.eye_l.is_open = True
    fs.eye_r.is_open = True


def face_wink_left(fs: FaceState) -> None:
    fs.eye_l.openness_target = 0.0
    fs.eye_l.is_open = True


def face_wink_right(fs: FaceState) -> None:
    fs.eye_r.openness_target = 0.0
    fs.eye_r.is_open = True


def face_set_gaze(fs: FaceState, x: float, y: float) -> None:
    x = max(-MAX_GAZE, min(MAX_GAZE, x))
    y = max(-MAX_GAZE, min(MAX_GAZE, y))
    for eye in (fs.eye_l, fs.eye_r):
        eye.gaze_x_target = x
        eye.gaze_y_target = y


def face_set_mood(fs: FaceState, mood: Mood) -> None:
    fs.mood = mood


def face_trigger_gesture(fs: FaceState, gesture: Gesture) -> None:
    now = time.monotonic()
    if gesture == Gesture.BLINK:
        face_blink(fs)
    elif gesture == Gesture.WINK_L:
        face_wink_left(fs)
    elif gesture == Gesture.WINK_R:
        face_wink_right(fs)
    elif gesture == Gesture.CONFUSED:
        fs.anim.confused = True
    elif gesture == Gesture.LAUGH:
        fs.anim.laugh = True
    elif gesture == Gesture.SURPRISE:
        fs.anim.surprise = True
        fs.anim.surprise_timer = now
    elif gesture == Gesture.HEART:
        fs.anim.heart = True
        fs.anim.heart_timer = now
    elif gesture == Gesture.X_EYES:
        fs.anim.x_eyes = True
        fs.anim.x_eyes_timer = now
    elif gesture == Gesture.SLEEPY:
        fs.anim.sleepy = True
        fs.anim.sleepy_timer = now
    elif gesture == Gesture.RAGE:
        fs.anim.rage = True
        fs.anim.rage_timer = now
    elif gesture == Gesture.NOD:
        fs.anim.laugh = True
    elif gesture == Gesture.HEADSHAKE:
        fs.anim.confused = True
    elif gesture == Gesture.WIGGLE:
        fs.anim.confused = True
        fs.anim.laugh = True


def face_set_system_mode(fs: FaceState, mode: SystemMode,
                         param: float = 0.0) -> None:
    fs.system.mode = mode
    fs.system.timer = time.monotonic()
    fs.system.phase = 0
    fs.system.param = param


def _update_system(fs: FaceState) -> bool:
    if fs.system.mode == SystemMode.NONE:
        return False

    now = time.monotonic()
    elapsed = now - fs.system.timer

    if fs.system.mode == SystemMode.BOOTING:
        if elapsed >= 3.0:
            fs.system.mode = SystemMode.NONE
            return False

    return True
