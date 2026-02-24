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
export const ANIM_FPS_OPTIONS = [30, 60] as const
export type AnimFps = (typeof ANIM_FPS_OPTIONS)[number]
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
// FIRE PARTICLES (RAGE gesture)
// ═══════════════════════════════════════════════════════════════════
export const FIRE_SPAWN_CHANCE = 0.3
export const FIRE_RISE_SPEED = 3.0
export const FIRE_DRIFT = 1.5
export const FIRE_HEAT_DECAY = 0.9

// ═══════════════════════════════════════════════════════════════════
// AFTERGLOW
// ═══════════════════════════════════════════════════════════════════
export const AFTERGLOW_DECAY = 0.4

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
// GESTURE VISUAL OVERRIDES
// ═══════════════════════════════════════════════════════════════════
export const SURPRISE_PEAK_W = 1.3
export const SURPRISE_PEAK_H = 1.25
export const SURPRISE_PEAK_TIME = 0.15

export const LAUGH_CHATTER_FREQ = 50.0
export const LAUGH_CHATTER_BASE = 0.2
export const LAUGH_CHATTER_AMP = 0.3

export const RAGE_LID_SLOPE = 0.9
export const RAGE_SHAKE_FREQ = 30.0
export const RAGE_SHAKE_AMP = 0.4
export const RAGE_MOUTH_CURVE = -1.0
export const RAGE_MOUTH_OPEN = 0.3
export const RAGE_MOUTH_WAVE = 0.7

export const CONFUSED_OFFSET_FREQ = 12.0
export const CONFUSED_OFFSET_AMP = 1.5
export const CONFUSED_MOUTH_CURVE = -0.2

export const SLEEPY_SWAY_FREQ = 2.0
export const SLEEPY_SWAY_AMP = 6.0
export const SLEEPY_LID_SLOPE = -0.2
export const SLEEPY_MOUTH_WIDTH = 0.7

export const X_EYES_MOUTH_OPEN = 0.8
export const X_EYES_MOUTH_WIDTH = 0.5

export const HEART_MOUTH_CURVE = 1.0
export const HEART_SOLID_SCALE = 1.0
export const HEART_PUPIL_SCALE = 2.5

export const FLICKER_AMP = 1.5

export const NOD_GAZE_Y_AMP = 4.0
export const NOD_FREQ = 12.0
export const NOD_LID_TOP_OFFSET = 0.15

export const HEADSHAKE_GAZE_X_AMP = 5.0
export const HEADSHAKE_FREQ = 14.0
export const HEADSHAKE_MOUTH_CURVE = -0.2

export const PEEK_A_BOO_CLOSE_TIME = 0.3
export const PEEK_A_BOO_PEAK_W = 1.2
export const PEEK_A_BOO_PEAK_H = 1.2

export const SHY_GAZE_X = -5.0
export const SHY_GAZE_Y = 3.0
export const SHY_LID_BOT = 0.2
export const SHY_MOUTH_CURVE = 0.4
export const SHY_PEEK_FRAC = 0.6

export const EYE_ROLL_GAZE_R = 5.0
export const EYE_ROLL_LID_PEAK = 0.15

export const DIZZY_GAZE_R_MAX = 4.0
export const DIZZY_FREQ = 10.0
export const DIZZY_MOUTH_WAVE = 0.4

export const CELEBRATE_EYE_SCALE = 1.15
export const CELEBRATE_MOUTH_CURVE = 0.9
export const CELEBRATE_SPARKLE_BOOST = 0.4

export const STARTLE_PEAK_TIME = 0.15
export const STARTLE_PEAK_W = 1.3
export const STARTLE_PEAK_H = 1.25

export const THINKING_HARD_GAZE_A: [number, number] = [6.0, -4.0]
export const THINKING_HARD_GAZE_B: [number, number] = [-6.0, -4.0]
export const THINKING_HARD_FREQ = 3.0
export const THINKING_HARD_LID_SLOPE = 0.5
export const THINKING_HARD_MOUTH_OFFSET_FREQ = 2.0

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

export enum HolidayMode {
  NONE = 0,
  BIRTHDAY = 1,
  HALLOWEEN = 2,
  CHRISTMAS = 3,
  NEW_YEAR = 4,
}

export enum ConvState {
  IDLE = 0,
  ATTENTION = 1,
  LISTENING = 2,
  PTT = 3,
  THINKING = 4,
  SPEAKING = 5,
  ERROR = 6,
  DONE = 7,
}

export enum ButtonIcon {
  NONE = 0,
  MIC = 1,
  X_MARK = 2,
  CHECK = 3,
  REPEAT = 4,
  STAR = 5,
  SPEAKER = 6,
}

export enum ButtonState {
  IDLE = 0,
  ACTIVE = 1,
  PRESSED = 2,
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
// CONVERSATION BORDER
// ═══════════════════════════════════════════════════════════════════
export const CONV_COLORS: Record<number, RGB> = {
  [ConvState.IDLE]: [0, 0, 0],
  [ConvState.ATTENTION]: [180, 240, 255],
  [ConvState.LISTENING]: [0, 200, 220],
  [ConvState.PTT]: [255, 200, 80],
  [ConvState.THINKING]: [120, 100, 255],
  [ConvState.SPEAKING]: [200, 240, 255],
  [ConvState.ERROR]: [255, 160, 60],
  [ConvState.DONE]: [0, 0, 0],
}

export const BORDER_FRAME_W = 4
export const BORDER_GLOW_W = 3
export const BORDER_CORNER_R = 3.0
export const BORDER_BLEND_RATE = 8.0

export const ATTENTION_DEPTH = 20

export const LISTENING_BREATH_FREQ = 1.5
export const LISTENING_ALPHA_BASE = 0.6
export const LISTENING_ALPHA_MOD = 0.3

export const PTT_PULSE_FREQ = 0.8
export const PTT_ALPHA_BASE = 0.8
export const PTT_ALPHA_MOD = 0.1

export const THINKING_ORBIT_DOTS = 3
export const THINKING_ORBIT_SPACING = 0.12
export const THINKING_ORBIT_SPEED = 0.5
export const THINKING_ORBIT_DOT_R = 4.0
export const THINKING_BORDER_ALPHA = 0.3

export const SPEAKING_ALPHA_BASE = 0.3
export const SPEAKING_ALPHA_MOD = 0.7

export const ERROR_FLASH_DURATION = 0.1
export const ERROR_DECAY_RATE = 5.0

export const DONE_FADE_SPEED = 2.0

export const LED_SCALE = 0.16

// ═══════════════════════════════════════════════════════════════════
// CORNER BUTTON ZONES
// ═══════════════════════════════════════════════════════════════════
export const BTN_CORNER_W = 60
export const BTN_CORNER_H = 46
export const BTN_CORNER_INNER_R = 8
export const BTN_ICON_SIZE = 18

export const BTN_ZONE_Y_TOP = SCREEN_H - BTN_CORNER_H
export const BTN_LEFT_ZONE_X1 = BTN_CORNER_W
export const BTN_RIGHT_ZONE_X0 = SCREEN_W - BTN_CORNER_W
export const BTN_LEFT_ICON_CX = (BTN_CORNER_W / 2) | 0
export const BTN_LEFT_ICON_CY = (SCREEN_H - BTN_CORNER_H / 2) | 0
export const BTN_RIGHT_ICON_CX = (SCREEN_W - BTN_CORNER_W / 2) | 0
export const BTN_RIGHT_ICON_CY = BTN_LEFT_ICON_CY

// ═══════════════════════════════════════════════════════════════════
// HOLIDAY MODES
// ═══════════════════════════════════════════════════════════════════

// Birthday
export const HOLIDAY_BIRTHDAY_SPARKLE = 0.3
export const HOLIDAY_BIRTHDAY_CELEBRATE_INTERVAL = 5.0
export const HOLIDAY_BIRTHDAY_COLOR_A: RGB = [255, 100, 150]
export const HOLIDAY_BIRTHDAY_COLOR_B: RGB = [0, 255, 200]

// Halloween
export const HOLIDAY_HALLOWEEN_COLOR: RGB = [255, 140, 0]
export const HOLIDAY_HALLOWEEN_FLICKER = 0.15
export const HOLIDAY_HALLOWEEN_LID_SLOPE = -0.8

// Christmas
export const HOLIDAY_CHRISTMAS_COLOR: RGB = [255, 220, 180]
export const HOLIDAY_CHRISTMAS_BREATH_SPEED = 1.2
export const HOLIDAY_SNOW_SPAWN_CHANCE = 0.15
export const HOLIDAY_SNOW_LIFE_MIN = 30
export const HOLIDAY_SNOW_LIFE_MAX = 60
export const HOLIDAY_SNOW_FALL_SPEED = 2.0
export const HOLIDAY_SNOW_DRIFT_AMP = 1.5

// New Year's
export const HOLIDAY_CONFETTI_SPAWN_CHANCE = 0.2
export const HOLIDAY_CONFETTI_LIFE_MIN = 20
export const HOLIDAY_CONFETTI_LIFE_MAX = 40
export const HOLIDAY_CONFETTI_FALL_SPEED = 3.0
export const HOLIDAY_CONFETTI_DRIFT = 1.0
export const HOLIDAY_CONFETTI_COLORS: RGB[] = [
  [255, 50, 50],
  [50, 255, 50],
  [50, 100, 255],
  [255, 255, 50],
  [255, 50, 255],
]

// Rosy cheeks (Christmas)
export const ROSY_CHEEK_R = 12.0
export const ROSY_CHEEK_Y_OFFSET = 35.0
export const ROSY_CHEEK_X_OFFSET = 10.0
export const ROSY_CHEEK_COLOR: RGB = [255, 150, 180]
export const ROSY_CHEEK_ALPHA = 0.3

// ═══════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════
export type RGB = [number, number, number]
