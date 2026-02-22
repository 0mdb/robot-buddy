"""Single source of truth for all face sim tunable values.

This file is read by the CI parity check (tools/check_face_parity.py).
Values must match MCU config.h + face_state.cpp exactly.
Conversation/border values come from face-communication-spec-stage2.md.
"""

from __future__ import annotations

from enum import IntEnum

# ══════════════════════════════════════════════════════════════════════
# DISPLAY
# ══════════════════════════════════════════════════════════════════════
SCREEN_W = 320
SCREEN_H = 240
ANIM_FPS = 30
PIXEL_SCALE = 2  # Display scale factor (sim only, not MCU)
BG_COLOR = (0, 0, 0)  # Pure black (MCU value; V2 sim used (10,10,14))

# ══════════════════════════════════════════════════════════════════════
# EYE GEOMETRY
# ══════════════════════════════════════════════════════════════════════
EYE_WIDTH = 80.0
EYE_HEIGHT = 85.0
EYE_CORNER_R = 25.0
PUPIL_R = 20.0
PUPIL_COLOR = (10, 15, 30)

LEFT_EYE_CX = 90.0
LEFT_EYE_CY = 85.0
RIGHT_EYE_CX = 230.0
RIGHT_EYE_CY = 85.0

# ══════════════════════════════════════════════════════════════════════
# GAZE
# ══════════════════════════════════════════════════════════════════════
MAX_GAZE = 12.0
GAZE_EYE_SHIFT = 3.0  # Eye body shift per unit gaze
GAZE_PUPIL_SHIFT = 8.0  # Pupil shift per unit gaze

# ══════════════════════════════════════════════════════════════════════
# MOUTH GEOMETRY
# ══════════════════════════════════════════════════════════════════════
MOUTH_CX = 160.0
MOUTH_CY = 185.0
MOUTH_HALF_W = 60.0
MOUTH_THICKNESS = 8.0

# ══════════════════════════════════════════════════════════════════════
# SPRING DYNAMICS (gaze)
# ══════════════════════════════════════════════════════════════════════
SPRING_K = 0.25
SPRING_D = 0.65

# ══════════════════════════════════════════════════════════════════════
# TWEEN SPEEDS (per-frame exponential interpolation)
# ══════════════════════════════════════════════════════════════════════
TWEEN_EYE_SCALE = 0.2
TWEEN_OPENNESS = 0.4
TWEEN_EYELID_TOP_CLOSING = 0.6  # Closing: faster
TWEEN_EYELID_TOP_OPENING = 0.4  # Opening: slower
TWEEN_EYELID_BOT = 0.3
TWEEN_EYELID_SLOPE = 0.3
TWEEN_MOUTH_CURVE = 0.2
TWEEN_MOUTH_OPEN = 0.4
TWEEN_MOUTH_WIDTH = 0.2
TWEEN_MOUTH_WAVE = 0.1
TWEEN_MOUTH_OFFSET_X = 0.2

# ══════════════════════════════════════════════════════════════════════
# BLINK TIMING
# ══════════════════════════════════════════════════════════════════════
BLINK_INTERVAL = 2.0  # Base seconds between blinks (MCU value)
BLINK_VARIATION = 3.0  # Random extra seconds (total range: 2.0-5.0)
BLINK_DURATION = 0.18  # 180 ms (gesture default)

# ══════════════════════════════════════════════════════════════════════
# IDLE GAZE WANDER
# ══════════════════════════════════════════════════════════════════════
IDLE_INTERVAL = 1.5  # Base seconds between gaze wanders (MCU value)
IDLE_VARIATION = 2.5  # Random extra seconds (total range: 1.5-4.0)
IDLE_GAZE_HOLD_MIN = 1.0  # MCU: 1.0 + randf() * 2.0
IDLE_GAZE_HOLD_RANGE = 2.0
SACCADE_INTERVAL_MIN = 0.1
SACCADE_INTERVAL_MAX = 0.4
SACCADE_JITTER = 0.5  # +/- gaze units

# ══════════════════════════════════════════════════════════════════════
# BREATHING
# ══════════════════════════════════════════════════════════════════════
BREATH_SPEED = 1.8  # rad/s
BREATH_AMOUNT = 0.04  # +/- 4% scale

# ══════════════════════════════════════════════════════════════════════
# SPARKLE
# ══════════════════════════════════════════════════════════════════════
SPARKLE_CHANCE = 0.05  # Per-frame chance
MAX_SPARKLE_PIXELS = 48
SPARKLE_LIFE_MIN = 5  # Frames
SPARKLE_LIFE_MAX = 15  # Frames

# ══════════════════════════════════════════════════════════════════════
# FIRE (rage effect)
# ══════════════════════════════════════════════════════════════════════
MAX_FIRE_PIXELS = 64
FIRE_SPAWN_CHANCE = 0.3
FIRE_RISE_SPEED = 3.0  # px per frame
FIRE_DRIFT = 1.5  # max horizontal drift per frame
FIRE_HEAT_DECAY = 0.9  # per frame

# ══════════════════════════════════════════════════════════════════════
# AFTERGLOW
# ══════════════════════════════════════════════════════════════════════
AFTERGLOW_DECAY = 0.4  # Blend ratio of prev frame (2/5)

# ══════════════════════════════════════════════════════════════════════
# EDGE GLOW
# ══════════════════════════════════════════════════════════════════════
EDGE_GLOW_FALLOFF = 0.4
EDGE_GLOW_OFFSET = 2  # Pixels outward from eye edge

# ══════════════════════════════════════════════════════════════════════
# TALKING
# ══════════════════════════════════════════════════════════════════════
TALKING_PHASE_SPEED = 15.0  # rad/s (MCU fixed value)
TALKING_BASE_OPEN = 0.2
TALKING_OPEN_MOD = 0.5
TALKING_WIDTH_MOD = 0.3
TALKING_BOUNCE_MOD = 0.05
TALKING_TIMEOUT_MS = 450  # MCU auto-stops after 450ms with no update

# ══════════════════════════════════════════════════════════════════════
# MOODS
# ══════════════════════════════════════════════════════════════════════


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
    CONFUSED = 12  # New: PE alignment report


# Neutral baseline values (mood targets blend from these)
NEUTRAL_MOUTH_CURVE = 0.1
NEUTRAL_MOUTH_WIDTH = 1.0
NEUTRAL_MOUTH_OPEN = 0.0
NEUTRAL_LID_SLOPE = 0.0
NEUTRAL_LID_TOP = 0.0
NEUTRAL_LID_BOT = 0.0
NEUTRAL_COLOR = (50, 150, 255)

# Per-mood parameter targets at full intensity (1.0):
#   (mouth_curve, mouth_width, mouth_open, lid_slope, lid_top, lid_bot)
MOOD_TARGETS: dict[Mood, tuple[float, float, float, float, float, float]] = {
    Mood.NEUTRAL: (0.1, 1.0, 0.0, 0.0, 0.0, 0.0),
    Mood.HAPPY: (0.8, 1.1, 0.0, 0.0, 0.0, 0.4),
    Mood.EXCITED: (0.9, 1.2, 0.2, 0.0, 0.0, 0.3),
    Mood.CURIOUS: (
        0.0,
        0.9,
        0.1,
        0.0,
        0.0,
        0.0,
    ),  # No slope; curiosity from asymmetric brow
    Mood.SAD: (-0.5, 1.0, 0.0, -0.6, 0.3, 0.0),
    Mood.SCARED: (-0.3, 0.8, 0.3, 0.0, 0.0, 0.0),
    Mood.ANGRY: (-0.6, 1.0, 0.0, 0.8, 0.4, 0.0),
    Mood.SURPRISED: (0.0, 0.4, 0.6, 0.0, 0.0, 0.0),
    Mood.SLEEPY: (0.0, 1.0, 0.0, -0.2, 0.6, 0.0),
    Mood.LOVE: (0.6, 1.0, 0.0, 0.0, 0.0, 0.3),
    Mood.SILLY: (0.5, 1.1, 0.0, 0.0, 0.0, 0.0),
    Mood.THINKING: (-0.1, 1.0, 0.0, 0.4, 0.2, 0.0),
    Mood.CONFUSED: (
        -0.2,
        1.0,
        0.0,
        0.2,
        0.1,
        0.0,
    ),  # Inner furrow (was -0.15 outer droop)
}

# Per-mood face colors at full intensity
MOOD_COLORS: dict[Mood, tuple[int, int, int]] = {
    Mood.NEUTRAL: (50, 150, 255),
    Mood.HAPPY: (0, 255, 200),
    Mood.EXCITED: (100, 255, 100),
    Mood.CURIOUS: (255, 180, 50),
    Mood.SAD: (70, 110, 210),  # Brightened for TN luma floor (was 50,80,200)
    Mood.SCARED: (180, 50, 255),
    Mood.ANGRY: (255, 0, 0),
    Mood.SURPRISED: (255, 255, 200),
    Mood.SLEEPY: (70, 90, 140),  # Brightened for TN luma floor (was 40,60,100)
    Mood.LOVE: (255, 100, 150),
    Mood.SILLY: (200, 255, 50),
    Mood.THINKING: (80, 135, 220),
    Mood.CONFUSED: (200, 160, 80),  # Provisional
}

# Gesture-driven color overrides (take priority over mood)
GESTURE_COLOR_RAGE = (255, 30, 0)
GESTURE_COLOR_HEART = (255, 105, 180)
GESTURE_COLOR_X_EYES = (200, 40, 40)

# Per-mood eye scale targets (width_scale, height_scale)
# See docs/face-visual-language.md §5.1 for design rationale.
# [Provisional] — sim-authored, pending visual review + T3/T4 evaluation.
MOOD_EYE_SCALE: dict[Mood, tuple[float, float]] = {
    Mood.NEUTRAL: (1.0, 1.0),  # Baseline
    Mood.HAPPY: (1.05, 0.9),  # Wider, squished (happy squint)
    Mood.EXCITED: (1.15, 1.1),  # Big wide eyes
    Mood.CURIOUS: (1.05, 1.15),  # Taller (attentive)
    Mood.SAD: (0.95, 0.85),  # Smaller, deflated
    Mood.SCARED: (0.9, 1.15),  # Narrow-tall (tense, frozen)
    Mood.ANGRY: (1.1, 0.65),  # Wide, compressed slit (glare)
    Mood.SURPRISED: (1.2, 1.2),  # Biggest (matches MCU)
    Mood.SLEEPY: (0.95, 0.7),  # Narrow slits
    Mood.LOVE: (1.05, 1.05),  # Slightly enlarged (soft)
    Mood.SILLY: (1.1, 1.0),  # Wider (goofy)
    Mood.THINKING: (1.0, 1.0),  # Neutral size (gaze aversion carries distinctiveness)
    Mood.CONFUSED: (1.0, 1.05),  # Slightly taller (puzzled)
}

# Thinking-mood gaze and mouth offset
THINKING_GAZE_X = 6.0
THINKING_GAZE_Y = -4.0
THINKING_MOUTH_OFFSET_X = 1.5

# Curious-mood asymmetric brow ("one eyebrow raised" look)
# Extra lid_top closure on right eye → left eye appears raised by contrast
CURIOUS_BROW_OFFSET = 0.25

# Confused-mood persistent mouth offset (asymmetric mouth sells "puzzled")
CONFUSED_MOOD_MOUTH_OFFSET_X = 2.0

# Love-mood pupil convergence + stillness
LOVE_CONVERGENCE_X = 2.5  # Per-eye inward gaze offset (mild soft focus)
LOVE_IDLE_HOLD_MIN = 2.5  # Longer hold between wanders (vs 1.0 normal)
LOVE_IDLE_HOLD_RANGE = 3.0  # Total range 2.5-5.5s (vs 1.0-3.0 normal)
LOVE_IDLE_AMPLITUDE = 0.4  # 40% of normal wander range (stillness)

# Silly-mood cross-eye gaze targets
SILLY_CROSS_EYE_A = (8.0, -8.0)  # (left_gaze_x, right_gaze_x)
SILLY_CROSS_EYE_B = (-6.0, 6.0)

# ══════════════════════════════════════════════════════════════════════
# GESTURES
# ══════════════════════════════════════════════════════════════════════


class GestureId(IntEnum):
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


# Default durations in seconds
GESTURE_DURATIONS: dict[GestureId, float] = {
    GestureId.BLINK: 0.18,
    GestureId.WINK_L: 0.20,
    GestureId.WINK_R: 0.20,
    GestureId.CONFUSED: 0.50,
    GestureId.LAUGH: 0.50,
    GestureId.SURPRISE: 0.80,
    GestureId.HEART: 2.00,
    GestureId.X_EYES: 2.50,
    GestureId.SLEEPY: 3.00,
    GestureId.RAGE: 3.00,
    GestureId.NOD: 0.35,
    GestureId.HEADSHAKE: 0.35,
    GestureId.WIGGLE: 0.60,
}

# Gesture-specific animation constants
SURPRISE_PEAK_W = 1.3
SURPRISE_PEAK_H = 1.25
SURPRISE_PEAK_TIME = 0.15  # seconds
LAUGH_CHATTER_FREQ = 50.0  # rad/s
LAUGH_CHATTER_BASE = 0.2
LAUGH_CHATTER_AMP = 0.3
RAGE_LID_SLOPE = 0.9
RAGE_SHAKE_FREQ = 30.0  # rad/s
RAGE_SHAKE_AMP = 0.4
RAGE_MOUTH_CURVE = -1.0
RAGE_MOUTH_OPEN = 0.3
RAGE_MOUTH_WAVE = 0.7
CONFUSED_OFFSET_FREQ = 12.0  # rad/s
CONFUSED_OFFSET_AMP = 1.5
CONFUSED_MOUTH_CURVE = -0.2
SLEEPY_SWAY_FREQ = 2.0  # rad/s
SLEEPY_SWAY_AMP = 6.0
SLEEPY_LID_SLOPE = -0.2
SLEEPY_MOUTH_WIDTH = 0.7
X_EYES_MOUTH_OPEN = 0.8
X_EYES_MOUTH_WIDTH = 0.5
HEART_MOUTH_CURVE = 1.0
FLICKER_AMP = 1.5
NOD_GAZE_Y_AMP = 4.0  # Vertical gaze displacement
NOD_FREQ = 12.0  # rad/s — ~2 nods in 350ms
NOD_LID_TOP_OFFSET = 0.15  # Slight upper lid follows gaze
HEADSHAKE_GAZE_X_AMP = 5.0  # Horizontal gaze displacement
HEADSHAKE_FREQ = 14.0  # rad/s — ~2.5 sweeps in 350ms
HEADSHAKE_MOUTH_CURVE = -0.2  # Slight frown during headshake

# ══════════════════════════════════════════════════════════════════════
# CONVERSATION STATES
# ══════════════════════════════════════════════════════════════════════


class ConvState(IntEnum):
    IDLE = 0
    ATTENTION = 1
    LISTENING = 2
    PTT = 3
    THINKING = 4
    SPEAKING = 5
    ERROR = 6
    DONE = 7


# Per-state border colors (spec section 4.2.2)
CONV_COLORS: dict[ConvState, tuple[int, int, int]] = {
    ConvState.IDLE: (0, 0, 0),
    ConvState.ATTENTION: (180, 240, 255),
    ConvState.LISTENING: (0, 200, 220),
    ConvState.PTT: (255, 200, 80),
    ConvState.THINKING: (120, 100, 255),
    ConvState.SPEAKING: (200, 240, 255),
    ConvState.ERROR: (255, 160, 60),
    ConvState.DONE: (0, 0, 0),
}

# Per-state gaze overrides (None = no override, uses idle wander)
CONV_GAZE: dict[ConvState, tuple[float, float] | None] = {
    ConvState.IDLE: None,
    ConvState.ATTENTION: (0.0, 0.0),
    ConvState.LISTENING: (0.0, 0.0),
    ConvState.PTT: (0.0, 0.0),
    ConvState.THINKING: (0.5, -0.3),  # Gaze aversion up-right (normalized)
    ConvState.SPEAKING: (0.0, 0.0),
    ConvState.ERROR: None,  # Micro-aversion handled separately
    ConvState.DONE: None,
}

# Per-state mood hints: (mood, intensity) or None
CONV_MOOD_HINTS: dict[ConvState, tuple[Mood, float] | None] = {
    ConvState.IDLE: None,
    ConvState.ATTENTION: None,
    ConvState.LISTENING: (Mood.NEUTRAL, 0.3),
    ConvState.PTT: (Mood.NEUTRAL, 0.3),
    ConvState.THINKING: (Mood.THINKING, 0.5),
    ConvState.SPEAKING: None,
    ConvState.ERROR: None,
    ConvState.DONE: None,
}

# Per-state flag overrides (spec section 9.3)
# -1 = no change (inherit from previous state)
CONV_FLAGS: dict[ConvState, int] = {
    ConvState.IDLE: 0x01 | 0x02 | 0x04 | 0x08 | 0x10 | 0x20,  # All defaults
    ConvState.ATTENTION: 0x02 | 0x04 | 0x08 | 0x10 | 0x20,  # Wander off
    ConvState.LISTENING: 0x02 | 0x04 | 0x08 | 0x10 | 0x20,
    ConvState.PTT: 0x02 | 0x04 | 0x08 | 0x10 | 0x20,
    ConvState.THINKING: 0x02 | 0x04 | 0x08 | 0x10,  # Wander off + sparkle off
    ConvState.SPEAKING: 0x02 | 0x04 | 0x08 | 0x10 | 0x20,
    ConvState.ERROR: -1,  # No change
    ConvState.DONE: 0x01 | 0x02 | 0x04 | 0x08 | 0x10 | 0x20,  # Restore idle
}

# ── Conversation border geometry ─────────────────────────────────────
BORDER_FRAME_W = 4  # Frame width in pixels
BORDER_GLOW_W = 3  # Inner glow width in pixels
BORDER_CORNER_R = 3.0

# ATTENTION animation
ATTENTION_DURATION = 0.4  # 400 ms
ATTENTION_DEPTH = 20  # Max inward sweep depth

# LISTENING animation
LISTENING_BREATH_FREQ = 1.5  # Hz
LISTENING_ALPHA_BASE = 0.6
LISTENING_ALPHA_MOD = 0.3

# PTT animation
PTT_PULSE_FREQ = 0.8  # Hz
PTT_ALPHA_BASE = 0.8
PTT_ALPHA_MOD = 0.1

# THINKING animation
THINKING_ORBIT_DOTS = 3
THINKING_ORBIT_SPACING = 0.12  # Fraction of perimeter
THINKING_ORBIT_SPEED = 0.5  # Revolutions per second
THINKING_ORBIT_DOT_R = 4.0
THINKING_BORDER_ALPHA = 0.3

# SPEAKING animation
SPEAKING_ALPHA_BASE = 0.3
SPEAKING_ALPHA_MOD = 0.7  # Multiplied by energy

# ERROR animation
ERROR_FLASH_DURATION = 0.1  # 100 ms
ERROR_DECAY_RATE = 5.0  # Exponential decay constant
ERROR_TOTAL_DURATION = 0.8  # 800 ms total
ERROR_AVERSION_DURATION = 0.2  # 200 ms gaze micro-aversion (spec §4.2.2)
ERROR_AVERSION_GAZE_X = -0.3  # Look-away direction (normalized)

# DONE animation
DONE_FADE_DURATION = 0.5  # 500 ms
DONE_FADE_SPEED = 2.0  # Alpha per second

# LED scaling
LED_SCALE = 0.16  # border_color * 0.16

# Border blend rate
BORDER_BLEND_RATE = 8.0  # per-second color/alpha interpolation

# ══════════════════════════════════════════════════════════════════════
# FEATURE FLAGS (bitmask, matches protocol.h)
# ══════════════════════════════════════════════════════════════════════
FLAG_IDLE_WANDER = 0x01
FLAG_AUTOBLINK = 0x02
FLAG_SOLID_EYE = 0x04
FLAG_SHOW_MOUTH = 0x08
FLAG_EDGE_GLOW = 0x10
FLAG_SPARKLE = 0x20
FLAG_AFTERGLOW = 0x40
FLAGS_ALL = (
    FLAG_IDLE_WANDER
    | FLAG_AUTOBLINK
    | FLAG_SOLID_EYE
    | FLAG_SHOW_MOUTH
    | FLAG_EDGE_GLOW
    | FLAG_SPARKLE
    | FLAG_AFTERGLOW
)
FLAGS_DEFAULT = FLAGS_ALL & ~FLAG_AFTERGLOW  # Afterglow off by default (matches MCU)

# ══════════════════════════════════════════════════════════════════════
# MOOD SEQUENCER (spec section 5.1.1)
# ══════════════════════════════════════════════════════════════════════
SEQ_ANTICIPATION_DURATION = 0.100  # 100 ms blink
SEQ_RAMP_DOWN_DURATION = 0.150  # 150 ms linear ramp
SEQ_RAMP_UP_DURATION = 0.200  # 200 ms linear ramp
SEQ_MIN_HOLD = 0.500  # 500 ms minimum hold before next transition

# ══════════════════════════════════════════════════════════════════════
# GUARDRAILS (spec section 7)
# ══════════════════════════════════════════════════════════════════════
GUARDRAIL_MAX_DURATION: dict[Mood, float] = {
    Mood.SAD: 4.0,
    Mood.SCARED: 2.0,
    Mood.ANGRY: 2.0,
    Mood.SURPRISED: 3.0,  # Startle reflex safety (spec section 7.4)
}

GUARDRAIL_INTENSITY_CAP: dict[Mood, float] = {
    Mood.SAD: 0.7,
    Mood.SCARED: 0.6,
    Mood.ANGRY: 0.5,
    Mood.SURPRISED: 0.8,
}

GUARDRAIL_RECOVERY_DURATION: dict[Mood, float] = {
    Mood.SAD: 0.500,
    Mood.SCARED: 0.300,
    Mood.ANGRY: 0.300,
    Mood.SURPRISED: 0.400,
}

# Negative moods blocked outside conversation by context gate
NEGATIVE_MOODS: frozenset[Mood] = frozenset({Mood.SAD, Mood.SCARED, Mood.ANGRY})

# PE worker stale snapshot threshold for tick-loop backstop
PE_STALE_THRESHOLD_MS = 3000

# ══════════════════════════════════════════════════════════════════════
# SYSTEM MODES
# ══════════════════════════════════════════════════════════════════════


class SystemMode(IntEnum):
    NONE = 0
    BOOTING = 1
    ERROR_DISPLAY = 2
    LOW_BATTERY = 3
    UPDATING = 4
    SHUTTING_DOWN = 5


# ══════════════════════════════════════════════════════════════════════
# BUTTON GEOMETRY (sim rendering)
# ══════════════════════════════════════════════════════════════════════
BTN_VISIBLE = 36
BTN_HITBOX = 48
BTN_MARGIN = 6
BTN_RADIUS = BTN_VISIBLE // 2
PTT_CX = BTN_MARGIN + BTN_HITBOX // 2  # 30
PTT_CY = SCREEN_H - BTN_MARGIN - BTN_HITBOX // 2  # 210
CANCEL_CX = SCREEN_W - BTN_MARGIN - BTN_HITBOX // 2  # 290
CANCEL_CY = SCREEN_H - BTN_MARGIN - BTN_HITBOX // 2  # 210

# ══════════════════════════════════════════════════════════════════════
# BRIGHTNESS
# ══════════════════════════════════════════════════════════════════════
DEFAULT_BRIGHTNESS = 200  # 0-255 TFT backlight via LEDC PWM
