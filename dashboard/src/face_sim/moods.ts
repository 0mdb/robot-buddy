/**
 * Per-mood parameter tables: targets, colors, eye scales, special offsets.
 *
 * Ported from tools/face_sim_v3/state/constants.py mood sections.
 */

import { Mood, type RGB } from './constants'

// Neutral baseline values (mood targets blend from these)
export const NEUTRAL_MOUTH_CURVE = 0.1
export const NEUTRAL_MOUTH_WIDTH = 1.0
export const NEUTRAL_MOUTH_OPEN = 0.0
export const NEUTRAL_LID_SLOPE = 0.0
export const NEUTRAL_LID_TOP = 0.0
export const NEUTRAL_LID_BOT = 0.0
export const NEUTRAL_COLOR: RGB = [50, 150, 255]

/** Per-mood (mouth_curve, mouth_width, mouth_open, lid_slope, lid_top, lid_bot) */
export type MoodTarget = [number, number, number, number, number, number]

export const MOOD_TARGETS: Record<number, MoodTarget> = {
  [Mood.NEUTRAL]: [0.1, 1.0, 0.0, 0.0, 0.0, 0.0],
  [Mood.HAPPY]: [0.8, 1.1, 0.0, 0.0, 0.0, 0.4],
  [Mood.EXCITED]: [0.9, 1.2, 0.2, 0.0, 0.0, 0.3],
  [Mood.CURIOUS]: [0.0, 0.9, 0.1, 0.0, 0.0, 0.0],
  [Mood.SAD]: [-0.5, 1.0, 0.0, -0.6, 0.3, 0.0],
  [Mood.SCARED]: [-0.3, 0.8, 0.3, 0.0, 0.0, 0.0],
  [Mood.ANGRY]: [-0.6, 1.0, 0.0, 0.8, 0.4, 0.0],
  [Mood.SURPRISED]: [0.0, 0.4, 0.6, 0.0, 0.0, 0.0],
  [Mood.SLEEPY]: [0.0, 1.0, 0.0, -0.2, 0.6, 0.0],
  [Mood.LOVE]: [0.6, 1.0, 0.0, 0.0, 0.0, 0.3],
  [Mood.SILLY]: [0.5, 1.1, 0.0, 0.0, 0.0, 0.0],
  [Mood.THINKING]: [-0.1, 1.0, 0.0, 0.4, 0.2, 0.0],
  [Mood.CONFUSED]: [-0.2, 1.0, 0.0, 0.2, 0.1, 0.0],
}

export const MOOD_COLORS: Record<number, RGB> = {
  [Mood.NEUTRAL]: [50, 150, 255],
  [Mood.HAPPY]: [0, 255, 200],
  [Mood.EXCITED]: [100, 255, 100],
  [Mood.CURIOUS]: [255, 180, 50],
  [Mood.SAD]: [70, 110, 210],
  [Mood.SCARED]: [180, 50, 255],
  [Mood.ANGRY]: [255, 0, 0],
  [Mood.SURPRISED]: [255, 255, 200],
  [Mood.SLEEPY]: [70, 90, 140],
  [Mood.LOVE]: [255, 100, 150],
  [Mood.SILLY]: [200, 255, 50],
  [Mood.THINKING]: [80, 135, 220],
  [Mood.CONFUSED]: [200, 160, 80],
}

/** Per-mood eye scale (width_scale, height_scale) */
export const MOOD_EYE_SCALE: Record<number, [number, number]> = {
  [Mood.NEUTRAL]: [1.0, 1.0],
  [Mood.HAPPY]: [1.05, 0.9],
  [Mood.EXCITED]: [1.15, 1.1],
  [Mood.CURIOUS]: [1.05, 1.15],
  [Mood.SAD]: [0.95, 0.85],
  [Mood.SCARED]: [0.9, 1.15],
  [Mood.ANGRY]: [1.1, 0.65],
  [Mood.SURPRISED]: [1.2, 1.2],
  [Mood.SLEEPY]: [0.95, 0.7],
  [Mood.LOVE]: [1.05, 1.05],
  [Mood.SILLY]: [1.1, 1.0],
  [Mood.THINKING]: [1.0, 1.0],
  [Mood.CONFUSED]: [1.0, 1.05],
}

// Gesture color overrides
export const GESTURE_COLOR_RAGE: RGB = [255, 30, 0]
export const GESTURE_COLOR_HEART: RGB = [255, 105, 180]
export const GESTURE_COLOR_X_EYES: RGB = [200, 40, 40]
export const GESTURE_COLOR_SHY: RGB = [255, 180, 200]
export const GESTURE_COLOR_CELEBRATE_A: RGB = [0, 255, 200]
export const GESTURE_COLOR_CELEBRATE_B: RGB = [100, 255, 100]
export const GESTURE_COLOR_CELEBRATE_C: RGB = [255, 255, 200]

// Thinking-mood offsets
export const THINKING_GAZE_X = 6.0
export const THINKING_GAZE_Y = -4.0
export const THINKING_MOUTH_OFFSET_X = 1.5

// Curious asymmetric brow
export const CURIOUS_BROW_OFFSET = 0.25

// Confused persistent mouth offset
export const CONFUSED_MOOD_MOUTH_OFFSET_X = 2.0

// Love convergence + stillness
export const LOVE_CONVERGENCE_X = 2.5
export const LOVE_IDLE_HOLD_MIN = 2.5
export const LOVE_IDLE_HOLD_RANGE = 3.0
export const LOVE_IDLE_AMPLITUDE = 0.4

// Silly cross-eye targets
export const SILLY_CROSS_EYE_A: [number, number] = [8.0, -8.0]
export const SILLY_CROSS_EYE_B: [number, number] = [-6.0, 6.0]
