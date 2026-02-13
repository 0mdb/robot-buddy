"""Face animation state machine.

Ported from FluxGarage RoboEyes (GPL-3.0, Dennis Hoelscher).
Adapted for 2x 16x16 WS2812 LED grids: keeps the tweening math
and animation timers, drops the Adafruit GFX rendering.

All coordinates are in "eye-local" pixel space (0..15 x 0..15).
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import IntEnum

# ── Mood / gesture enums ──────────────────────────────────────────────

class Mood(IntEnum):
    DEFAULT = 0
    TIRED = 1
    ANGRY = 2
    HAPPY = 3


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


class SystemMode(IntEnum):
    NONE = 0             # normal face display
    BOOTING = 1          # expanding ring animation (full grid)
    ERROR = 2            # flashing warning triangle
    LOW_BATTERY = 3      # battery icon draining
    UPDATING = 4         # spinning arc loader
    SHUTTING_DOWN = 5    # shrinking dot fade-out


# ── Per-eye state ─────────────────────────────────────────────────────

@dataclass
class EyeState:
    # Openness: 0.0 = fully closed, 1.0 = fully open
    openness: float = 0.0          # current  (starts closed, opens on boot)
    openness_target: float = 1.0   # target
    is_open: bool = True           # intent flag (mirrors RoboEyes eyeL_open)

    # Gaze offset in pixels from center (-3..+3 is the usable range)
    gaze_x: float = 0.0
    gaze_x_target: float = 0.0
    gaze_y: float = 0.0
    gaze_y_target: float = 0.0

    # Squash & stretch: 1.0 = normal, >1 = wide, <1 = tall
    width_scale: float = 1.0
    width_scale_target: float = 1.0
    height_scale: float = 1.0
    height_scale_target: float = 1.0


# ── Eyelid overlay state ─────────────────────────────────────────────

@dataclass
class EyelidState:
    # 0.0 = no eyelid overlay, 1.0 = max eyelid coverage
    tired: float = 0.0
    tired_target: float = 0.0
    angry: float = 0.0
    angry_target: float = 0.0
    happy: float = 0.0
    happy_target: float = 0.0


# ── Macro animation timers ───────────────────────────────────────────

@dataclass
class AnimTimers:
    # Auto-blink
    autoblink: bool = True
    blink_interval: float = 2.0        # base seconds between blinks
    blink_variation: float = 3.0       # random extra seconds
    next_blink: float = 0.0            # monotonic timestamp

    # Idle gaze wander
    idle: bool = True
    idle_interval: float = 1.5
    idle_variation: float = 2.5
    next_idle: float = 0.0

    # One-shot: confused (horizontal shake)
    confused: bool = False
    confused_timer: float = 0.0
    confused_duration: float = 0.5
    confused_toggle: bool = True

    # One-shot: laugh (vertical shake)
    laugh: bool = False
    laugh_timer: float = 0.0
    laugh_duration: float = 0.5
    laugh_toggle: bool = True

    # One-shot: surprise (eyes go wide then settle)
    surprise: bool = False
    surprise_timer: float = 0.0
    surprise_duration: float = 0.8

    # One-shot: heart eyes
    heart: bool = False
    heart_timer: float = 0.0
    heart_duration: float = 2.0

    # One-shot: X eyes (dizzy/KO)
    x_eyes: bool = False
    x_eyes_timer: float = 0.0
    x_eyes_duration: float = 1.5

    # One-shot: sleepy drift (slow droop and sway)
    sleepy: bool = False
    sleepy_timer: float = 0.0
    sleepy_duration: float = 3.0

    # One-shot: rage (red fiery eyes with flame particles)
    rage: bool = False
    rage_timer: float = 0.0
    rage_duration: float = 3.0

    # Flicker state (driven by confused / laugh)
    h_flicker: bool = False
    h_flicker_alt: bool = False
    h_flicker_amp: float = 1.5  # pixels, scaled for 16px grid

    v_flicker: bool = False
    v_flicker_alt: bool = False
    v_flicker_amp: float = 1.5


# ── Breathing & visual effects ────────────────────────────────────────

@dataclass
class EffectsState:
    # Breathing: gentle scale pulse (always active)
    breathing: bool = True
    breath_phase: float = 0.0       # 0..2π radians
    breath_speed: float = 1.8       # radians per second
    breath_amount: float = 0.06     # max scale deviation (±6%)

    # Edge glow: dim outer pixels for depth
    edge_glow: bool = True
    edge_glow_falloff: float = 0.4  # 0=no falloff, 1=max falloff

    # Afterglow: pixels fade out instead of snapping off on blink
    afterglow: bool = True
    afterglow_grid: list | None = None  # previous frame's grid for fade

    # Sparkle: occasional twinkle on solid eyes
    sparkle: bool = True
    sparkle_pixels: list = field(default_factory=list)  # [(x,y,life)]
    sparkle_chance: float = 0.03    # per-frame chance of new sparkle

    # Color emotion: tint shifts based on mood / gesture
    color_emotion: bool = True

    # Fire particles (driven by rage gesture)
    fire_pixels: list = field(default_factory=list)  # [(x, y, life, heat)]

    # Boot-up sequence
    boot_active: bool = True
    boot_timer: float = 0.0
    boot_phase: int = 0             # 0=grow, 1=blink, 2=look-around


# ── System display state ─────────────────────────────────────────────

@dataclass
class SystemState:
    mode: SystemMode = SystemMode.NONE
    timer: float = 0.0           # monotonic timestamp when mode started
    phase: int = 0               # sub-phase for multi-step animations
    param: float = 0.0           # generic parameter (e.g. battery level 0..1)


# ── Top-level face state ─────────────────────────────────────────────

GRID_SIZE = 16   # pixels per eye (square)
MAX_GAZE = 3.0   # max gaze offset in pixels

@dataclass
class FaceState:
    eye_l: EyeState = field(default_factory=EyeState)
    eye_r: EyeState = field(default_factory=EyeState)
    eyelids: EyelidState = field(default_factory=EyelidState)
    anim: AnimTimers = field(default_factory=AnimTimers)
    fx: EffectsState = field(default_factory=EffectsState)
    system: SystemState = field(default_factory=SystemState)

    mood: Mood = Mood.DEFAULT
    brightness: float = 1.0   # 0.0 .. 1.0 global brightness cap
    solid_eye: bool = True     # True = solid-color eyes (EVE/Astro style)
    mouth: bool = True         # show mouth line below eyes

    # Mouth curve: -1.0 = full frown, 0.0 = flat, 1.0 = full smile
    mouth_curve: float = 0.2
    mouth_curve_target: float = 0.2
    # Mouth openness: 0.0 = closed line, 1.0 = wide open (surprise/laugh)
    mouth_open: float = 0.0
    mouth_open_target: float = 0.0
    # Mouth wave: 0.0 = no wobble, 1.0 = full sine wobble (snarl/bared teeth)
    mouth_wave: float = 0.0
    mouth_wave_target: float = 0.0
    # Mouth horizontal offset: -2.0..+2.0 pixel shift (smirk)
    mouth_offset_x: float = 0.0
    mouth_offset_x_target: float = 0.0
    # Mouth width scale: 0.3 = tiny pucker, 1.0 = normal, 1.5 = wide
    mouth_width: float = 1.0
    mouth_width_target: float = 1.0


# ── Tweening helper ──────────────────────────────────────────────────

def _tween(current: float, target: float, speed: float = 0.5) -> float:
    """Exponential ease-out, same as RoboEyes' (current + target) / 2."""
    return current + (target - current) * speed


# ── Boot-up sequence ─────────────────────────────────────────────────

def _update_boot(fs: FaceState) -> None:
    """Drive the boot-up animation: grow → blink → curious look-around."""
    now = time.monotonic()
    elapsed = now - fs.fx.boot_timer

    if fs.fx.boot_phase == 0:
        # Phase 0: eyes grow from closed to open (0.0 → 1.0 over ~1s)
        progress = min(1.0, elapsed / 1.0)
        # Use ease-out curve
        eased = 1.0 - (1.0 - progress) ** 2
        fs.eye_l.openness = eased
        fs.eye_r.openness = eased
        fs.eye_l.openness_target = eased
        fs.eye_r.openness_target = eased
        if progress >= 1.0:
            fs.fx.boot_phase = 1
            fs.fx.boot_timer = now

    elif fs.fx.boot_phase == 1:
        # Phase 1: one slow blink at ~0.8s mark
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
        # Phase 2: curious look around (left → right → center)
        if elapsed < 0.5:
            t = elapsed / 0.5
            gx = -2.0 * t
        elif elapsed < 1.2:
            t = (elapsed - 0.5) / 0.7
            gx = -2.0 + 4.0 * t
        elif elapsed < 1.8:
            t = (elapsed - 1.2) / 0.6
            gx = 2.0 * (1.0 - t)
        else:
            gx = 0.0
            fs.fx.boot_active = False
        for eye in (fs.eye_l, fs.eye_r):
            eye.gaze_x = gx
            eye.gaze_x_target = gx
            eye.gaze_y = 0.0
            eye.gaze_y_target = 0.0


# ── State update (call once per frame) ───────────────────────────────

def face_state_update(fs: FaceState) -> None:
    """Advance all animations by one tick.  Call at your target FPS."""
    now = time.monotonic()

    # ── System display mode takes priority over everything ─────────
    if _update_system(fs):
        return

    # ── Boot-up sequence takes priority ─────────────────────────────
    if fs.fx.boot_active:
        if fs.fx.boot_timer == 0.0:
            fs.fx.boot_timer = now
        _update_boot(fs)
        _update_breathing(fs)
        _update_sparkle(fs)
        return

    # ── Mood → eyelid targets ────────────────────────────────────────
    fs.eyelids.tired_target = 1.0 if fs.mood == Mood.TIRED else 0.0
    fs.eyelids.angry_target = 1.0 if fs.mood == Mood.ANGRY else 0.0
    fs.eyelids.happy_target = 1.0 if fs.mood == Mood.HAPPY else 0.0

    # ── Mood → mouth targets ───────────────────────────────────────
    if fs.mood == Mood.HAPPY:
        fs.mouth_curve_target = 0.8
    elif fs.mood == Mood.ANGRY:
        fs.mouth_curve_target = -0.6
    elif fs.mood == Mood.TIRED:
        fs.mouth_curve_target = -0.3
    else:
        fs.mouth_curve_target = 0.2   # slight default smile

    # ── Auto-blink ───────────────────────────────────────────────────
    if fs.anim.autoblink and now >= fs.anim.next_blink:
        face_blink(fs)
        fs.anim.next_blink = (
            now + fs.anim.blink_interval + random.random() * fs.anim.blink_variation
        )

    # ── Re-open eyes after blink completes ───────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        if eye.is_open and eye.openness < 0.05:
            eye.openness_target = 1.0
        if not eye.is_open:
            eye.openness_target = 0.0

    # ── Idle gaze wander ─────────────────────────────────────────────
    if fs.anim.idle and now >= fs.anim.next_idle:
        gx = random.uniform(-MAX_GAZE, MAX_GAZE)
        gy = random.uniform(-MAX_GAZE * 0.6, MAX_GAZE * 0.6)
        fs.eye_l.gaze_x_target = gx
        fs.eye_l.gaze_y_target = gy
        fs.eye_r.gaze_x_target = gx
        fs.eye_r.gaze_y_target = gy
        fs.anim.next_idle = (
            now + fs.anim.idle_interval + random.random() * fs.anim.idle_variation
        )

    # ── Confused (horizontal shake) ──────────────────────────────────
    if fs.anim.confused:
        if fs.anim.confused_toggle:
            fs.anim.h_flicker = True
            fs.anim.h_flicker_amp = 1.5
            fs.anim.confused_timer = now
            fs.anim.confused_toggle = False
        elif now >= fs.anim.confused_timer + fs.anim.confused_duration:
            fs.anim.h_flicker = False
            fs.anim.confused_toggle = True
            fs.anim.confused = False

    # ── Laugh (vertical shake) ───────────────────────────────────────
    if fs.anim.laugh:
        if fs.anim.laugh_toggle:
            fs.anim.v_flicker = True
            fs.anim.v_flicker_amp = 1.5
            fs.anim.laugh_timer = now
            fs.anim.laugh_toggle = False
        elif now >= fs.anim.laugh_timer + fs.anim.laugh_duration:
            fs.anim.v_flicker = False
            fs.anim.laugh_toggle = True
            fs.anim.laugh = False

    # ── Surprise (wide eyes then settle) ─────────────────────────────
    if fs.anim.surprise:
        elapsed = now - fs.anim.surprise_timer
        if elapsed < 0.15:
            # Snap eyes wide with stretch
            for eye in (fs.eye_l, fs.eye_r):
                eye.width_scale_target = 1.3
                eye.height_scale_target = 1.25
        elif elapsed < fs.anim.surprise_duration:
            # Settle back
            for eye in (fs.eye_l, fs.eye_r):
                eye.width_scale_target = 1.0
                eye.height_scale_target = 1.0
        else:
            for eye in (fs.eye_l, fs.eye_r):
                eye.width_scale_target = 1.0
                eye.height_scale_target = 1.0
            fs.anim.surprise = False

    # ── Heart eyes ───────────────────────────────────────────────────
    if fs.anim.heart:
        elapsed = now - fs.anim.heart_timer
        if elapsed >= fs.anim.heart_duration:
            fs.anim.heart = False

    # ── X eyes (dizzy/KO) ───────────────────────────────────────────
    if fs.anim.x_eyes:
        elapsed = now - fs.anim.x_eyes_timer
        if elapsed >= fs.anim.x_eyes_duration:
            fs.anim.x_eyes = False

    # ── Rage (fiery red eyes) ──────────────────────────────────────────
    if fs.anim.rage:
        elapsed = now - fs.anim.rage_timer
        if elapsed < fs.anim.rage_duration:
            # Slam angry eyelids on hard + slight vibration
            fs.eyelids.angry_target = 1.0
            # Subtle shake
            shake = math.sin(elapsed * 30.0) * 0.4
            for eye in (fs.eye_l, fs.eye_r):
                eye.gaze_x_target = shake
        else:
            fs.eyelids.angry_target = 0.0
            fs.anim.rage = False
            fs.fx.fire_pixels.clear()

    # ── Sleepy drift ─────────────────────────────────────────────────
    if fs.anim.sleepy:
        elapsed = now - fs.anim.sleepy_timer
        if elapsed < fs.anim.sleepy_duration:
            # Slowly droop lids and sway
            droop = min(1.0, elapsed / 1.5)
            fs.eyelids.tired_target = droop
            sway = math.sin(elapsed * 2.0) * 1.5
            for eye in (fs.eye_l, fs.eye_r):
                eye.gaze_x_target = sway
                eye.gaze_y_target = droop * 1.0
        else:
            fs.eyelids.tired_target = 0.0
            fs.anim.sleepy = False

    # ── Gesture → mouth overrides ─────────────────────────────────────
    # Default new-param targets (gestures override below)
    fs.mouth_wave_target = 0.0
    fs.mouth_offset_x_target = 0.0
    fs.mouth_width_target = 1.0

    if fs.anim.surprise:
        # Pucker: narrow O-mouth
        fs.mouth_curve_target = 0.0
        fs.mouth_open_target = 0.8
        fs.mouth_width_target = 0.5
    elif fs.anim.laugh:
        # Chatter: big smile with rapid open/close
        fs.mouth_curve_target = 1.0
        elapsed = now - fs.anim.laugh_timer
        # Drive mouth_open directly (bypass tween) for snappy chatter
        chatter = 0.2 + 0.3 * max(0.0, math.sin(elapsed * 50.0))
        fs.mouth_open = chatter
        fs.mouth_open_target = chatter
    elif fs.anim.heart:
        fs.mouth_curve_target = 1.0
        fs.mouth_open_target = 0.0
    elif fs.anim.rage:
        # Snarl: frown with wave wobble (bared teeth)
        fs.mouth_curve_target = -1.0
        fs.mouth_open_target = 0.3
        fs.mouth_wave_target = 0.7
    elif fs.anim.x_eyes:
        # KO face: X eyes + O mouth
        fs.mouth_curve_target = 0.0   # flat (circular, not smiling/frowning)
        fs.mouth_open_target = 0.8    # wide open O
        fs.mouth_width_target = 0.5   # narrow for round O shape
    elif fs.anim.sleepy:
        # Yawn: ramp open wide midway through, hold, then close
        elapsed = now - fs.anim.sleepy_timer
        dur = fs.anim.sleepy_duration
        yawn_start = dur * 0.2   # yawn begins at 20%
        yawn_peak = dur * 0.4    # peak at 40%
        yawn_end = dur * 0.7     # closes by 70%
        if elapsed < yawn_start:
            fs.mouth_open_target = 0.0
            fs.mouth_curve_target = fs.mouth_curve_target  # keep mood
        elif elapsed < yawn_peak:
            # Ramp open
            t = (elapsed - yawn_start) / (yawn_peak - yawn_start)
            fs.mouth_open_target = t * 1.0
            fs.mouth_curve_target = 0.0  # flatten curve for O shape
            fs.mouth_width_target = 0.7  # slightly narrower
        elif elapsed < yawn_end:
            # Hold open
            fs.mouth_open_target = 1.0
            fs.mouth_curve_target = 0.0
            fs.mouth_width_target = 0.7
        else:
            # Close slowly
            t = (elapsed - yawn_end) / (dur - yawn_end)
            fs.mouth_open_target = max(0.0, 1.0 - t * 1.5)
            fs.mouth_curve_target = fs.mouth_curve_target  # back to mood
    elif fs.anim.confused:
        # Smirk: mouth shifts to one side
        elapsed = now - fs.anim.confused_timer
        fs.mouth_offset_x_target = 1.5 * math.sin(elapsed * 12.0)
        fs.mouth_curve_target = -0.2
        fs.mouth_open_target = 0.0
    else:
        fs.mouth_open_target = 0.0

    # ── Squash & stretch on blink ────────────────────────────────────
    for eye in (fs.eye_l, fs.eye_r):
        if eye.openness_target < 0.1 and eye.openness > 0.3:
            # Closing: squash (wider, shorter)
            eye.width_scale_target = 1.15
            eye.height_scale_target = 0.85
        elif eye.openness_target > 0.9 and eye.openness < 0.7:
            # Opening: stretch (taller, narrower)
            eye.width_scale_target = 0.9
            eye.height_scale_target = 1.1
        elif eye.openness > 0.9:
            # Back to normal
            eye.width_scale_target = 1.0
            eye.height_scale_target = 1.0

    # ── Tween all continuous values ──────────────────────────────────
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

    # ── Apply flicker offsets (added to gaze after tween) ────────────
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

    # ── Effects ──────────────────────────────────────────────────────
    _update_breathing(fs)
    _update_sparkle(fs)
    _update_fire(fs)


# ── Effects helpers ──────────────────────────────────────────────────

def _update_breathing(fs: FaceState) -> None:
    """Advance breathing phase — a gentle rhythmic scale pulse."""
    if not fs.fx.breathing:
        return
    fs.fx.breath_phase += fs.fx.breath_speed / 60.0  # assume ~60fps
    if fs.fx.breath_phase > math.tau:
        fs.fx.breath_phase -= math.tau


def _update_sparkle(fs: FaceState) -> None:
    """Manage sparkle pixel lifetimes and spawn new ones."""
    if not fs.fx.sparkle:
        fs.fx.sparkle_pixels.clear()
        return
    # Age existing sparkles
    fs.fx.sparkle_pixels = [
        (x, y, life - 1) for x, y, life in fs.fx.sparkle_pixels if life > 1
    ]
    # Maybe spawn a new one
    if random.random() < fs.fx.sparkle_chance:
        x = random.randint(0, GRID_SIZE - 1)
        y = random.randint(0, GRID_SIZE - 1)
        life = random.randint(4, 12)
        fs.fx.sparkle_pixels.append((x, y, life))


def _update_fire(fs: FaceState) -> None:
    """Manage fire particles that rise above the eyes during rage."""
    if not fs.anim.rage:
        fs.fx.fire_pixels.clear()
        return
    # Age existing fire particles: rise upward, lose life
    fs.fx.fire_pixels = [
        (x + random.uniform(-0.3, 0.3), y - 0.5, life - 1, heat * 0.9)
        for x, y, life, heat in fs.fx.fire_pixels if life > 1 and y > 0
    ]
    # Spawn new fire particles along the top edge of each eye
    # Left eye top: around x=1..7, y=1..3  Right eye top: around x=9..15, y=1..3
    for _ in range(3):
        if random.random() < 0.7:
            x = random.uniform(1.0, 7.0)
            y = random.uniform(1.0, 3.5)
            life = random.randint(4, 10)
            heat = random.uniform(0.7, 1.0)
            fs.fx.fire_pixels.append((x, y, life, heat))
        if random.random() < 0.7:
            x = random.uniform(9.0, 15.0)
            y = random.uniform(1.0, 3.5)
            life = random.randint(4, 10)
            heat = random.uniform(0.7, 1.0)
            fs.fx.fire_pixels.append((x, y, life, heat))


def get_breath_scale(fs: FaceState) -> float:
    """Return current breathing scale factor (e.g. 0.94..1.06)."""
    if not fs.fx.breathing:
        return 1.0
    return 1.0 + math.sin(fs.fx.breath_phase) * fs.fx.breath_amount


def get_emotion_color(fs: FaceState) -> tuple[int, int, int]:
    """Return the current eye color based on mood/gesture state."""
    if not fs.fx.color_emotion:
        return (30, 120, 255)  # default blue

    # Rage → hot red with flicker
    if fs.anim.rage:
        flicker = random.randint(-20, 20)
        return (min(255, 230 + flicker), max(0, 30 + flicker), 0)

    # Heart eyes → pink
    if fs.anim.heart:
        return (255, 60, 140)

    # X eyes → red-ish
    if fs.anim.x_eyes:
        return (200, 40, 40)

    # Surprise → bright white-blue flash
    if fs.anim.surprise:
        elapsed = time.monotonic() - fs.anim.surprise_timer
        if elapsed < 0.15:
            return (200, 220, 255)

    # Mood-based tints
    if fs.mood == Mood.HAPPY:
        return (50, 180, 255)   # warm cyan
    elif fs.mood == Mood.TIRED:
        return (20, 60, 160)    # deep navy
    elif fs.mood == Mood.ANGRY:
        return (60, 80, 220)    # cooler blue-violet
    else:
        return (30, 120, 255)   # default blue


# ── Convenience triggers (mirror RoboEyes API) ──────────────────────

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
    """Set gaze target.  x/y in range -3..+3."""
    x = max(-MAX_GAZE, min(MAX_GAZE, x))
    y = max(-MAX_GAZE, min(MAX_GAZE, y))
    fs.eye_l.gaze_x_target = x
    fs.eye_l.gaze_y_target = y
    fs.eye_r.gaze_x_target = x
    fs.eye_r.gaze_y_target = y


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


# ── System mode triggers ─────────────────────────────────────────────

def face_set_system_mode(fs: FaceState, mode: SystemMode,
                         param: float = 0.0) -> None:
    """Enter a system display mode.  param is mode-specific (e.g. battery %)."""
    fs.system.mode = mode
    fs.system.timer = time.monotonic()
    fs.system.phase = 0
    fs.system.param = param


def _update_system(fs: FaceState) -> bool:
    """Update system-mode animation.  Returns True if system mode is active
    (meaning the normal face should NOT be rendered this frame)."""
    if fs.system.mode == SystemMode.NONE:
        return False

    now = time.monotonic()
    elapsed = now - fs.system.timer

    if fs.system.mode == SystemMode.BOOTING:
        # 3-second expanding ring sequence then auto-exit
        if elapsed >= 3.0:
            fs.system.mode = SystemMode.NONE
            return False

    elif fs.system.mode == SystemMode.SHUTTING_DOWN:
        # 2-second shrink-to-dot then stays dark
        pass  # rendering handled in face_render

    # All other modes (ERROR, LOW_BATTERY, UPDATING) persist until cleared
    return True
