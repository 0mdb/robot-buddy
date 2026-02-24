/**
 * Single source of truth for all face sim tunable values.
 *
 * Ported from tools/face_sim_v3/state/constants.py.
 * Values must match MCU config.h + face_state.cpp exactly.
 */

// ═══════════════════════════════════════════════════════════════════
// DISPLAY
// ═══════════════════════════════════════════════════════════════════
export const SCREEN_W = 320
export const SCREEN_H = 240
export const ANIM_FPS = 30
export const BG_COLOR: RGB = [0, 0, 0]

// ═══════════════════════════════════════════════════════════════════
// EYE GEOMETRY
// ═══════════════════════════════════════════════════════════════════
export const EYE_WIDTH = 80.0
export const EYE_HEIGHT = 85.0
export const EYE_CORNER_R = 25.0
export const PUPIL_R = 20.0
export const PUPIL_COLOR: RGB = [10, 15, 30]

export const LEFT_EYE_CX = 90.0
export const LEFT_EYE_CY = 85.0
export const RIGHT_EYE_CX = 230.0
export const RIGHT_EYE_CY = 85.0

// ═══════════════════════════════════════════════════════════════════
// GAZE
// ═══════════════════════════════════════════════════════════════════
export const MAX_GAZE = 12.0
export const GAZE_EYE_SHIFT = 3.0
export const GAZE_PUPIL_SHIFT = 8.0

// ═══════════════════════════════════════════════════════════════════
// MOUTH GEOMETRY
// ═══════════════════════════════════════════════════════════════════
export const MOUTH_CX = 160.0
export const MOUTH_CY = 185.0
export const MOUTH_HALF_W = 60.0
export const MOUTH_THICKNESS = 8.0

// ═══════════════════════════════════════════════════════════════════
// SPRING DYNAMICS (gaze)
// ═══════════════════════════════════════════════════════════════════
export const SPRING_K = 0.25
export const SPRING_D = 0.65

// ═══════════════════════════════════════════════════════════════════
// TWEEN SPEEDS (per-frame exponential interpolation)
// ═══════════════════════════════════════════════════════════════════
export const TWEEN_EYE_SCALE = 0.2
export const TWEEN_OPENNESS = 0.4
export const TWEEN_EYELID_TOP_CLOSING = 0.6
export const TWEEN_EYELID_TOP_OPENING = 0.4
export const TWEEN_EYELID_BOT = 0.3
export const TWEEN_EYELID_SLOPE = 0.3
export const TWEEN_MOUTH_CURVE = 0.2
export const TWEEN_MOUTH_OPEN = 0.4
export const TWEEN_MOUTH_WIDTH = 0.2
export const TWEEN_MOUTH_WAVE = 0.1
export const TWEEN_MOUTH_OFFSET_X = 0.2

// ═══════════════════════════════════════════════════════════════════
// BLINK TIMING
// ═══════════════════════════════════════════════════════════════════
export const BLINK_INTERVAL = 2.0
export const BLINK_VARIATION = 3.0
export const BLINK_DURATION = 0.18

// ═══════════════════════════════════════════════════════════════════
// IDLE GAZE WANDER
// ═══════════════════════════════════════════════════════════════════
export const IDLE_INTERVAL = 1.5
export const IDLE_VARIATION = 2.5
export const IDLE_GAZE_HOLD_MIN = 1.0
export const IDLE_GAZE_HOLD_RANGE = 2.0
export const SACCADE_INTERVAL_MIN = 0.1
export const SACCADE_INTERVAL_MAX = 0.4
export const SACCADE_JITTER = 0.5

// ═══════════════════════════════════════════════════════════════════
// BREATHING
// ═══════════════════════════════════════════════════════════════════
export const BREATH_SPEED = 1.8
export const BREATH_AMOUNT = 0.04

// ═══════════════════════════════════════════════════════════════════
// SPARKLE
// ═══════════════════════════════════════════════════════════════════
export const SPARKLE_CHANCE = 0.05
export const MAX_SPARKLE_PIXELS = 48
export const SPARKLE_LIFE_MIN = 5
export const SPARKLE_LIFE_MAX = 15

// ═══════════════════════════════════════════════════════════════════
// EDGE GLOW
// ═══════════════════════════════════════════════════════════════════
export const EDGE_GLOW_FALLOFF = 0.4

// ═══════════════════════════════════════════════════════════════════
// TALKING
// ═══════════════════════════════════════════════════════════════════
export const TALKING_PHASE_SPEED = 15.0
export const TALKING_BASE_OPEN = 0.2
export const TALKING_OPEN_MOD = 0.5
export const TALKING_WIDTH_MOD = 0.3
export const TALKING_BOUNCE_MOD = 0.05

// Speech rhythm sync
export const SPEECH_EYE_PULSE_THRESHOLD = 0.7
export const SPEECH_EYE_PULSE_FRAMES = 3
export const SPEECH_EYE_PULSE_AMOUNT = 0.04
export const SPEECH_EYE_PULSE_DECAY = 0.85
export const SPEECH_BREATH_MOD = 0.8
export const SPEECH_BREATH_MIN = 1.5
export const SPEECH_BREATH_MAX = 2.2
export const SPEECH_PAUSE_THRESHOLD = 0.05
export const SPEECH_PAUSE_FRAMES = 15
export const SPEECH_PAUSE_GAZE_SHIFT = 2.0

// Idle micro-expressions
export const MICRO_EXPR_MIN_INTERVAL = 30.0
export const MICRO_EXPR_RANGE = 60.0
export const MICRO_EXPR_CURIOUS_DUR = 0.5
export const MICRO_EXPR_SIGH_DUR = 0.8
export const MICRO_EXPR_FIDGET_DUR = 0.4

// ═══════════════════════════════════════════════════════════════════
// ENUMS
// ═══════════════════════════════════════════════════════════════════

export enum Mood {
  NEUTRAL = 0,
  HAPPY = 1,
  EXCITED = 2,
  CURIOUS = 3,
  SAD = 4,
  SCARED = 5,
  ANGRY = 6,
  SURPRISED = 7,
  SLEEPY = 8,
  LOVE = 9,
  SILLY = 10,
  THINKING = 11,
  CONFUSED = 12,
}

export enum GestureId {
  BLINK = 0,
  WINK_L = 1,
  WINK_R = 2,
  CONFUSED = 3,
  LAUGH = 4,
  SURPRISE = 5,
  HEART = 6,
  X_EYES = 7,
  SLEEPY = 8,
  RAGE = 9,
  NOD = 10,
  HEADSHAKE = 11,
  WIGGLE = 12,
  // Sim-only (deferred from firmware)
  PEEK_A_BOO = 13,
  SHY = 14,
  EYE_ROLL = 15,
  DIZZY = 16,
  CELEBRATE = 17,
  STARTLE_RELIEF = 18,
  THINKING_HARD = 19,
}

export enum SystemMode {
  NONE = 0,
  BOOTING = 1,
  ERROR_DISPLAY = 2,
  LOW_BATTERY = 3,
  UPDATING = 4,
  SHUTTING_DOWN = 5,
}

// ═══════════════════════════════════════════════════════════════════
// FEATURE FLAGS (bitmask, matches protocol.h)
// ═══════════════════════════════════════════════════════════════════
export const FLAG_IDLE_WANDER = 0x01
export const FLAG_AUTOBLINK = 0x02
export const FLAG_SOLID_EYE = 0x04
export const FLAG_SHOW_MOUTH = 0x08
export const FLAG_EDGE_GLOW = 0x10
export const FLAG_SPARKLE = 0x20
export const FLAG_AFTERGLOW = 0x40
export const FLAGS_ALL =
  FLAG_IDLE_WANDER |
  FLAG_AUTOBLINK |
  FLAG_SOLID_EYE |
  FLAG_SHOW_MOUTH |
  FLAG_EDGE_GLOW |
  FLAG_SPARKLE |
  FLAG_AFTERGLOW
export const FLAGS_DEFAULT = FLAGS_ALL & ~FLAG_AFTERGLOW

// ═══════════════════════════════════════════════════════════════════
// GESTURE DURATIONS (seconds)
// ═══════════════════════════════════════════════════════════════════
export const GESTURE_DURATIONS: Record<number, number> = {
  [GestureId.BLINK]: 0.18,
  [GestureId.WINK_L]: 0.2,
  [GestureId.WINK_R]: 0.2,
  [GestureId.CONFUSED]: 0.5,
  [GestureId.LAUGH]: 0.5,
  [GestureId.SURPRISE]: 0.8,
  [GestureId.HEART]: 2.0,
  [GestureId.X_EYES]: 2.5,
  [GestureId.SLEEPY]: 3.0,
  [GestureId.RAGE]: 3.0,
  [GestureId.NOD]: 0.35,
  [GestureId.HEADSHAKE]: 0.35,
  [GestureId.WIGGLE]: 0.6,
  [GestureId.PEEK_A_BOO]: 1.5,
  [GestureId.SHY]: 2.0,
  [GestureId.EYE_ROLL]: 1.0,
  [GestureId.DIZZY]: 2.0,
  [GestureId.CELEBRATE]: 2.5,
  [GestureId.STARTLE_RELIEF]: 1.5,
  [GestureId.THINKING_HARD]: 3.0,
}

// ═══════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════
export type RGB = [number, number, number]
