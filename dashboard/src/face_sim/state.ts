/**
 * Face animation state machine — per-frame update logic.
 *
 * Ported from tools/face_sim_v3/state/face_state.py.
 * Phases 1-5: core update, gesture overrides, fire/holiday/effects.
 */

import {
  BLINK_INTERVAL,
  BLINK_VARIATION,
  BREATH_AMOUNT,
  BREATH_SPEED,
  CELEBRATE_EYE_SCALE,
  CELEBRATE_MOUTH_CURVE,
  CELEBRATE_SPARKLE_BOOST,
  CONFUSED_MOUTH_CURVE,
  CONFUSED_OFFSET_AMP,
  CONFUSED_OFFSET_FREQ,
  DIZZY_FREQ,
  DIZZY_GAZE_R_MAX,
  DIZZY_MOUTH_WAVE,
  EYE_ROLL_GAZE_R,
  EYE_ROLL_LID_PEAK,
  FIRE_DRIFT,
  FIRE_HEAT_DECAY,
  FIRE_RISE_SPEED,
  FIRE_SPAWN_CHANCE,
  FLICKER_AMP,
  GESTURE_DURATIONS,
  GestureId,
  HEADSHAKE_FREQ,
  HEADSHAKE_GAZE_X_AMP,
  HEADSHAKE_MOUTH_CURVE,
  HEART_MOUTH_CURVE,
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
  HolidayMode,
  IDLE_GAZE_HOLD_MIN,
  IDLE_GAZE_HOLD_RANGE,
  LAUGH_CHATTER_AMP,
  LAUGH_CHATTER_BASE,
  LAUGH_CHATTER_FREQ,
  LEFT_EYE_CX,
  LEFT_EYE_CY,
  MAX_GAZE,
  MICRO_EXPR_CURIOUS_DUR,
  MICRO_EXPR_FIDGET_DUR,
  MICRO_EXPR_MIN_INTERVAL,
  MICRO_EXPR_RANGE,
  MICRO_EXPR_SIGH_DUR,
  Mood,
  NOD_FREQ,
  NOD_GAZE_Y_AMP,
  NOD_LID_TOP_OFFSET,
  PEEK_A_BOO_CLOSE_TIME,
  PEEK_A_BOO_PEAK_H,
  PEEK_A_BOO_PEAK_W,
  RAGE_LID_SLOPE,
  RAGE_MOUTH_CURVE,
  RAGE_MOUTH_OPEN,
  RAGE_MOUTH_WAVE,
  RAGE_SHAKE_AMP,
  RAGE_SHAKE_FREQ,
  type RGB,
  RIGHT_EYE_CX,
  SACCADE_INTERVAL_MAX,
  SACCADE_INTERVAL_MIN,
  SACCADE_JITTER,
  SCREEN_H,
  SCREEN_W,
  SHY_GAZE_X,
  SHY_GAZE_Y,
  SHY_LID_BOT,
  SHY_MOUTH_CURVE,
  SHY_PEEK_FRAC,
  SLEEPY_LID_SLOPE,
  SLEEPY_MOUTH_WIDTH,
  SLEEPY_SWAY_AMP,
  SLEEPY_SWAY_FREQ,
  SPARKLE_CHANCE,
  SPARKLE_LIFE_MAX,
  SPARKLE_LIFE_MIN,
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
  SPRING_D,
  SPRING_K,
  STARTLE_PEAK_H,
  STARTLE_PEAK_TIME,
  STARTLE_PEAK_W,
  SURPRISE_PEAK_H,
  SURPRISE_PEAK_TIME,
  SURPRISE_PEAK_W,
  SystemMode,
  TALKING_BASE_OPEN,
  TALKING_BOUNCE_MOD,
  TALKING_OPEN_MOD,
  TALKING_PHASE_SPEED,
  TALKING_WIDTH_MOD,
  THINKING_HARD_FREQ,
  THINKING_HARD_GAZE_A,
  THINKING_HARD_GAZE_B,
  THINKING_HARD_LID_SLOPE,
  THINKING_HARD_MOUTH_OFFSET_FREQ,
  TWEEN_EYE_SCALE,
  TWEEN_EYELID_BOT,
  TWEEN_EYELID_SLOPE,
  TWEEN_EYELID_TOP_CLOSING,
  TWEEN_EYELID_TOP_OPENING,
  TWEEN_MOUTH_CURVE,
  TWEEN_MOUTH_OFFSET_X,
  TWEEN_MOUTH_OPEN,
  TWEEN_MOUTH_WAVE,
  TWEEN_MOUTH_WIDTH,
  TWEEN_OPENNESS,
  X_EYES_MOUTH_OPEN,
  X_EYES_MOUTH_WIDTH,
} from './constants'
import {
  CONFUSED_MOOD_MOUTH_OFFSET_X,
  CURIOUS_BROW_OFFSET,
  GESTURE_COLOR_CELEBRATE_A,
  GESTURE_COLOR_CELEBRATE_B,
  GESTURE_COLOR_CELEBRATE_C,
  GESTURE_COLOR_HEART,
  GESTURE_COLOR_RAGE,
  GESTURE_COLOR_SHY,
  GESTURE_COLOR_X_EYES,
  LOVE_CONVERGENCE_X,
  LOVE_IDLE_AMPLITUDE,
  LOVE_IDLE_HOLD_MIN,
  LOVE_IDLE_HOLD_RANGE,
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
  SILLY_CROSS_EYE_A,
  SILLY_CROSS_EYE_B,
  THINKING_GAZE_X,
  THINKING_GAZE_Y,
  THINKING_MOUTH_OFFSET_X,
} from './moods'
import type { FaceState } from './types'

// ── Physics ────────────────────────────────────────────────────

function tween(current: number, target: number, speed: number): number {
  return current + (target - current) * speed
}

function spring(
  current: number,
  target: number,
  vel: number,
  k = SPRING_K,
  d = SPRING_D,
): [number, number] {
  const force = (target - current) * k
  const newVel = (vel + force) * d
  return [current + newVel, newVel]
}

// ── Public API ─────────────────────────────────────────────────

export function getBreathScale(fs: FaceState): number {
  if (!fs.fx.breathing) return 1.0
  return 1.0 + Math.sin(fs.fx.breath_phase) * BREATH_AMOUNT
}

export function getEmotionColor(fs: FaceState): RGB {
  if (fs.mood_color_override !== null) return fs.mood_color_override

  // Gesture color overrides
  let moodColor: RGB
  if (fs.anim.rage) {
    moodColor = GESTURE_COLOR_RAGE
  } else if (fs.anim.heart) {
    moodColor = GESTURE_COLOR_HEART
  } else if (fs.anim.x_eyes) {
    moodColor = GESTURE_COLOR_X_EYES
  } else if (fs.anim.shy) {
    moodColor = GESTURE_COLOR_SHY
  } else if (fs.anim.celebrate) {
    // Color cycling: teal → green → warm white
    const elapsedG = performance.now() / 1000.0 - fs.anim.celebrate_timer
    const cycle = (elapsedG * 3.0) | 0
    const colors = [GESTURE_COLOR_CELEBRATE_A, GESTURE_COLOR_CELEBRATE_B, GESTURE_COLOR_CELEBRATE_C]
    moodColor = colors[cycle % 3]
  } else {
    moodColor = MOOD_COLORS[fs.mood] ?? NEUTRAL_COLOR
  }

  // Intensity blending: neutral + (mood - neutral) * intensity
  const intensity = Math.max(0.0, Math.min(1.0, fs.expression_intensity))
  const [nr, ng, nb] = NEUTRAL_COLOR
  const [mr, mg, mb] = moodColor
  return [
    Math.max(0, Math.min(255, (nr + (mr - nr) * intensity) | 0)),
    Math.max(0, Math.min(255, (ng + (mg - ng) * intensity) | 0)),
    Math.max(0, Math.min(255, (nb + (mb - nb) * intensity) | 0)),
  ]
}

export function faceBlink(fs: FaceState): void {
  fs.eye_l.is_open = false
  fs.eye_r.is_open = false
  fs.eye_l.openness_target = 0.0
  fs.eye_r.openness_target = 0.0
  setActiveGesture(fs, GestureId.BLINK, 0.18)
}

function setActiveGesture(fs: FaceState, gesture: number, duration: number): void {
  fs.active_gesture = gesture
  fs.active_gesture_until = performance.now() / 1000.0 + duration
}

export function faceTriggerGesture(fs: FaceState, gesture: number, durationMs = 0): void {
  const now = performance.now() / 1000.0
  const defaultDur = GESTURE_DURATIONS[gesture] ?? 0.5
  const dur = durationMs > 0 ? Math.max(0.08, durationMs / 1000.0) : defaultDur

  if (gesture === GestureId.BLINK) {
    faceBlink(fs)
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.WINK_L) {
    fs.eye_l.is_open = false
    fs.eye_l.openness_target = 0.0
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.WINK_R) {
    fs.eye_r.is_open = false
    fs.eye_r.openness_target = 0.0
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.NOD) {
    fs.anim.nod = true
    fs.anim.nod_timer = now
    fs.anim.nod_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.HEADSHAKE) {
    fs.anim.headshake = true
    fs.anim.headshake_timer = now
    fs.anim.headshake_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.LAUGH) {
    fs.anim.laugh = true
    fs.anim.laugh_timer = now
    fs.anim.laugh_toggle = true
    fs.anim.laugh_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.CONFUSED) {
    fs.anim.confused = true
    fs.anim.confused_timer = now
    fs.anim.confused_toggle = true
    fs.anim.confused_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.RAGE) {
    fs.anim.rage = true
    fs.anim.rage_timer = now
    fs.anim.rage_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.HEART) {
    fs.anim.heart = true
    fs.anim.heart_timer = now
    fs.anim.heart_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.X_EYES) {
    fs.anim.x_eyes = true
    fs.anim.x_eyes_timer = now
    fs.anim.x_eyes_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.SLEEPY) {
    fs.anim.sleepy = true
    fs.anim.sleepy_timer = now
    fs.anim.sleepy_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.SURPRISE) {
    fs.anim.surprise = true
    fs.anim.surprise_timer = now
    fs.anim.surprise_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.WIGGLE) {
    fs.anim.confused = true
    fs.anim.confused_timer = now
    fs.anim.confused_toggle = true
    fs.anim.confused_duration = dur
    fs.anim.laugh = true
    fs.anim.laugh_timer = now
    fs.anim.laugh_toggle = true
    fs.anim.laugh_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.PEEK_A_BOO) {
    fs.anim.peek_a_boo = true
    fs.anim.peek_a_boo_timer = now
    fs.anim.peek_a_boo_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.SHY) {
    fs.anim.shy = true
    fs.anim.shy_timer = now
    fs.anim.shy_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.EYE_ROLL) {
    fs.anim.eye_roll = true
    fs.anim.eye_roll_timer = now
    fs.anim.eye_roll_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.DIZZY) {
    fs.anim.dizzy = true
    fs.anim.dizzy_timer = now
    fs.anim.dizzy_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.CELEBRATE) {
    fs.anim.celebrate = true
    fs.anim.celebrate_timer = now
    fs.anim.celebrate_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.STARTLE_RELIEF) {
    fs.anim.startle_relief = true
    fs.anim.startle_relief_timer = now
    fs.anim.startle_relief_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else if (gesture === GestureId.THINKING_HARD) {
    fs.anim.thinking_hard = true
    fs.anim.thinking_hard_timer = now
    fs.anim.thinking_hard_duration = dur
    setActiveGesture(fs, gesture, dur)
  } else {
    setActiveGesture(fs, gesture, dur)
  }
}

export function faceSetFlags(fs: FaceState, flags: number): void {
  fs.anim.idle = !!(flags & 0x01)
  fs.anim.autoblink = !!(flags & 0x02)
  fs.solid_eye = !!(flags & 0x04)
  fs.show_mouth = !!(flags & 0x08)
  fs.fx.edge_glow = !!(flags & 0x10)
  fs.fx.sparkle = !!(flags & 0x20)
  fs.fx.afterglow = !!(flags & 0x40)
}

// ── Per-frame update ───────────────────────────────────────────

export function faceStateUpdate(fs: FaceState, dt: number): void {
  const now = performance.now() / 1000.0

  // Skip update if system mode is active
  if (fs.system.mode !== SystemMode.NONE) return

  // ── 0. HOLIDAY MODE ──────────────────────────────────────
  updateHoliday(fs, now)

  // ── 1. MOOD TARGETS with intensity blending ──────────────
  const targets = MOOD_TARGETS[fs.mood] ?? MOOD_TARGETS[Mood.NEUTRAL]
  let [tCurve, tWidth, tOpen, tLidSlope, tLidTop, tLidBot] = targets

  const intensity = Math.max(0.0, Math.min(1.0, fs.expression_intensity))
  tCurve = NEUTRAL_MOUTH_CURVE + (tCurve - NEUTRAL_MOUTH_CURVE) * intensity
  tWidth = NEUTRAL_MOUTH_WIDTH + (tWidth - NEUTRAL_MOUTH_WIDTH) * intensity
  tOpen = NEUTRAL_MOUTH_OPEN + (tOpen - NEUTRAL_MOUTH_OPEN) * intensity
  tLidSlope = NEUTRAL_LID_SLOPE + (tLidSlope - NEUTRAL_LID_SLOPE) * intensity
  tLidTop = NEUTRAL_LID_TOP + (tLidTop - NEUTRAL_LID_TOP) * intensity
  tLidBot = NEUTRAL_LID_BOT + (tLidBot - NEUTRAL_LID_BOT) * intensity

  // Reset eye scale targets each frame
  fs.eye_l.width_scale_target = 1.0
  fs.eye_l.height_scale_target = 1.0
  fs.eye_r.width_scale_target = 1.0
  fs.eye_r.height_scale_target = 1.0

  // Per-mood eye scale with intensity blending
  const eyeScale = MOOD_EYE_SCALE[fs.mood] ?? [1.0, 1.0]
  const ws = 1.0 + (eyeScale[0] - 1.0) * intensity
  const hs = 1.0 + (eyeScale[1] - 1.0) * intensity
  fs.eye_l.width_scale_target = ws
  fs.eye_r.width_scale_target = ws
  fs.eye_l.height_scale_target = hs
  fs.eye_r.height_scale_target = hs

  fs.mouth_curve_target = tCurve
  fs.mouth_width_target = tWidth
  fs.mouth_open_target = tOpen
  fs.mouth_wave_target = 0.0
  fs.mouth_offset_x_target = 0.0
  fs.eyelids.slope_target = tLidSlope

  // Thinking: gaze up-and-aside + mouth offset
  if (fs.mood === Mood.THINKING) {
    fs.mouth_offset_x_target = THINKING_MOUTH_OFFSET_X
    fs.eye_l.gaze_x_target = THINKING_GAZE_X
    fs.eye_l.gaze_y_target = THINKING_GAZE_Y
    fs.eye_r.gaze_x_target = THINKING_GAZE_X
    fs.eye_r.gaze_y_target = THINKING_GAZE_Y
  }

  // Confused: persistent mouth offset
  if (fs.mood === Mood.CONFUSED) {
    fs.mouth_offset_x_target = CONFUSED_MOOD_MOUTH_OFFSET_X
  }

  // Love: pupil convergence
  if (fs.mood === Mood.LOVE) {
    const li = Math.max(0.0, Math.min(1.0, fs.expression_intensity))
    fs.eye_l.gaze_x_target = LOVE_CONVERGENCE_X * li
    fs.eye_r.gaze_x_target = -LOVE_CONVERGENCE_X * li
  }

  // ── 2. GESTURE OVERRIDES ─────────────────────────────────
  if (fs.anim.surprise) {
    const elapsedG = now - fs.anim.surprise_timer
    if (elapsedG < SURPRISE_PEAK_TIME) {
      fs.eye_l.width_scale_target = SURPRISE_PEAK_W
      fs.eye_l.height_scale_target = SURPRISE_PEAK_H
      fs.eye_r.width_scale_target = SURPRISE_PEAK_W
      fs.eye_r.height_scale_target = SURPRISE_PEAK_H
    }
    fs.mouth_curve_target = 0.0
    fs.mouth_open_target = 0.6
    fs.mouth_width_target = 0.5
  }

  if (fs.anim.laugh) {
    fs.mouth_curve_target = 1.0
    const elapsedG = now - fs.anim.laugh_timer
    const chatter =
      LAUGH_CHATTER_BASE +
      LAUGH_CHATTER_AMP * Math.max(0.0, Math.sin(elapsedG * LAUGH_CHATTER_FREQ))
    fs.mouth_open_target = Math.max(fs.mouth_open_target, chatter)
  }

  if (fs.anim.rage) {
    const elapsedG = now - fs.anim.rage_timer
    fs.eyelids.slope_target = RAGE_LID_SLOPE
    tLidTop = Math.max(tLidTop, 0.4)
    const shake = Math.sin(elapsedG * RAGE_SHAKE_FREQ) * RAGE_SHAKE_AMP
    fs.eye_l.gaze_x_target = shake
    fs.eye_r.gaze_x_target = shake
    fs.mouth_curve_target = RAGE_MOUTH_CURVE
    fs.mouth_open_target = RAGE_MOUTH_OPEN
    fs.mouth_wave_target = RAGE_MOUTH_WAVE
  }

  if (fs.anim.x_eyes) {
    fs.mouth_curve_target = 0.0
    fs.mouth_open_target = X_EYES_MOUTH_OPEN
    fs.mouth_width_target = X_EYES_MOUTH_WIDTH
  }

  if (fs.anim.heart) {
    fs.mouth_curve_target = HEART_MOUTH_CURVE
    fs.mouth_open_target = 0.0
  }

  if (fs.anim.sleepy) {
    const elapsedG = now - fs.anim.sleepy_timer
    const droop = Math.min(1.0, elapsedG / Math.max(0.15, fs.anim.sleepy_duration * 0.5))
    tLidTop = Math.max(tLidTop, droop * 0.6)
    fs.eyelids.slope_target = SLEEPY_LID_SLOPE
    const sway = Math.sin(elapsedG * SLEEPY_SWAY_FREQ) * SLEEPY_SWAY_AMP
    fs.eye_l.gaze_x_target = sway
    fs.eye_r.gaze_x_target = sway
    fs.eye_l.gaze_y_target = droop * 3.0
    fs.eye_r.gaze_y_target = droop * 3.0
    // Yawn sequence
    const dur = Math.max(0.2, fs.anim.sleepy_duration)
    const ys = dur * 0.2
    const yp = dur * 0.4
    const ye = dur * 0.7
    if (elapsedG < ys) {
      // nothing
    } else if (elapsedG < yp) {
      fs.mouth_open_target = (elapsedG - ys) / (yp - ys)
      fs.mouth_curve_target = 0.0
      fs.mouth_width_target = SLEEPY_MOUTH_WIDTH
    } else if (elapsedG < ye) {
      fs.mouth_open_target = 1.0
      fs.mouth_curve_target = 0.0
      fs.mouth_width_target = SLEEPY_MOUTH_WIDTH
    } else {
      const t2 = (elapsedG - ye) / Math.max(0.001, dur - ye)
      fs.mouth_open_target = Math.max(0.0, 1.0 - t2 * 1.5)
    }
  }

  if (fs.anim.confused) {
    const elapsedG = now - fs.anim.confused_timer
    fs.mouth_offset_x_target = CONFUSED_OFFSET_AMP * Math.sin(elapsedG * CONFUSED_OFFSET_FREQ)
    fs.mouth_curve_target = CONFUSED_MOUTH_CURVE
    fs.mouth_open_target = 0.0
  }

  if (fs.anim.peek_a_boo) {
    const elapsedG = now - fs.anim.peek_a_boo_timer
    const dur = Math.max(0.01, fs.anim.peek_a_boo_duration)
    const frac = elapsedG / dur
    if (frac < PEEK_A_BOO_CLOSE_TIME) {
      tLidTop = 1.0
    } else if (frac < PEEK_A_BOO_CLOSE_TIME + 0.2) {
      fs.eye_l.width_scale_target = PEEK_A_BOO_PEAK_W
      fs.eye_l.height_scale_target = PEEK_A_BOO_PEAK_H
      fs.eye_r.width_scale_target = PEEK_A_BOO_PEAK_W
      fs.eye_r.height_scale_target = PEEK_A_BOO_PEAK_H
      fs.mouth_open_target = 0.4
      fs.mouth_curve_target = 0.0
    }
  }

  if (fs.anim.shy) {
    const elapsedG = now - fs.anim.shy_timer
    const dur = Math.max(0.01, fs.anim.shy_duration)
    const frac = elapsedG / dur
    fs.eye_l.gaze_x_target = SHY_GAZE_X
    fs.eye_l.gaze_y_target = SHY_GAZE_Y
    fs.eye_r.gaze_x_target = SHY_GAZE_X
    fs.eye_r.gaze_y_target = SHY_GAZE_Y
    tLidBot = Math.max(tLidBot, SHY_LID_BOT)
    fs.mouth_curve_target = SHY_MOUTH_CURVE
    if (SHY_PEEK_FRAC < frac && frac < SHY_PEEK_FRAC + 0.15) {
      fs.eye_l.gaze_y_target = -2.0
      fs.eye_r.gaze_y_target = -2.0
    }
  }

  if (fs.anim.eye_roll) {
    const elapsedG = now - fs.anim.eye_roll_timer
    const dur = Math.max(0.01, fs.anim.eye_roll_duration)
    const frac = elapsedG / dur
    if (frac < 0.8) {
      const angle = (frac / 0.8) * 2.0 * Math.PI
      const gy = -EYE_ROLL_GAZE_R * Math.cos(angle)
      if (gy < -EYE_ROLL_GAZE_R * 0.5) {
        tLidTop = Math.max(tLidTop, EYE_ROLL_LID_PEAK)
      }
    }
  }

  if (fs.anim.dizzy) {
    fs.mouth_wave_target = DIZZY_MOUTH_WAVE
  }

  if (fs.anim.celebrate) {
    const elapsedG = now - fs.anim.celebrate_timer
    const dur = Math.max(0.01, fs.anim.celebrate_duration)
    const frac = elapsedG / dur
    fs.eye_l.width_scale_target = CELEBRATE_EYE_SCALE
    fs.eye_l.height_scale_target = CELEBRATE_EYE_SCALE
    fs.eye_r.width_scale_target = CELEBRATE_EYE_SCALE
    fs.eye_r.height_scale_target = CELEBRATE_EYE_SCALE
    fs.mouth_curve_target = CELEBRATE_MOUTH_CURVE
    // Rapid alternating winks
    const winkFracs = [0.2, 0.4, 0.6]
    for (let idx = 0; idx < winkFracs.length; idx++) {
      const wf = winkFracs[idx]
      if (wf <= frac && frac < wf + 0.05) {
        if (idx % 2 === 0 && fs.eye_l.is_open) {
          fs.eye_l.is_open = false
          fs.eye_l.openness_target = 0.0
        } else if (idx % 2 === 1 && fs.eye_r.is_open) {
          fs.eye_r.is_open = false
          fs.eye_r.openness_target = 0.0
        }
      }
    }
  }

  if (fs.anim.startle_relief) {
    const elapsedG = now - fs.anim.startle_relief_timer
    const dur = Math.max(0.01, fs.anim.startle_relief_duration)
    const frac = elapsedG / dur
    const startleFrac = STARTLE_PEAK_TIME / dur
    if (frac < startleFrac) {
      // Phase 1: Startle — wide eyes, O mouth
      fs.eye_l.width_scale_target = STARTLE_PEAK_W
      fs.eye_l.height_scale_target = STARTLE_PEAK_H
      fs.eye_r.width_scale_target = STARTLE_PEAK_W
      fs.eye_r.height_scale_target = STARTLE_PEAK_H
      fs.mouth_curve_target = 0.0
      fs.mouth_open_target = 0.6
      fs.mouth_width_target = 0.5
    } else {
      // Phase 2: Relief — happy squint, big smile, gaze down
      fs.mouth_curve_target = 0.8
      fs.eye_l.width_scale_target = 1.05
      fs.eye_l.height_scale_target = 0.9
      fs.eye_r.width_scale_target = 1.05
      fs.eye_r.height_scale_target = 0.9
      tLidBot = Math.max(tLidBot, 0.3)
      fs.eye_l.gaze_y_target = 2.0
      fs.eye_r.gaze_y_target = 2.0
    }
  }

  if (fs.anim.thinking_hard) {
    const elapsedG = now - fs.anim.thinking_hard_timer
    const tOsc = (Math.sin(elapsedG * THINKING_HARD_FREQ) + 1.0) * 0.5
    const gx = THINKING_HARD_GAZE_A[0] + (THINKING_HARD_GAZE_B[0] - THINKING_HARD_GAZE_A[0]) * tOsc
    const gy = THINKING_HARD_GAZE_A[1] + (THINKING_HARD_GAZE_B[1] - THINKING_HARD_GAZE_A[1]) * tOsc
    fs.eye_l.gaze_x_target = gx
    fs.eye_r.gaze_x_target = gx
    fs.eye_l.gaze_y_target = gy
    fs.eye_r.gaze_y_target = gy
    fs.eyelids.slope_target = THINKING_HARD_LID_SLOPE
    fs.mouth_offset_x_target = 2.0 * Math.sin(elapsedG * THINKING_HARD_MOUTH_OFFSET_FREQ)
    fs.eye_l.height_scale_target = 0.9
    fs.eye_r.height_scale_target = 0.9
  }

  if (fs.anim.nod) {
    const elapsedG = now - fs.anim.nod_timer
    const lidOffset = NOD_LID_TOP_OFFSET * Math.max(0.0, Math.sin(elapsedG * NOD_FREQ))
    tLidTop = Math.max(tLidTop, lidOffset)
  }

  if (fs.anim.headshake) {
    fs.mouth_curve_target = HEADSHAKE_MOUTH_CURVE
  }

  // ── 3. GESTURE TIMEOUTS ──────────────────────────────────
  if (fs.anim.heart && now > fs.anim.heart_timer + fs.anim.heart_duration) fs.anim.heart = false
  if (fs.anim.x_eyes && now > fs.anim.x_eyes_timer + fs.anim.x_eyes_duration) fs.anim.x_eyes = false
  if (fs.anim.rage && now > fs.anim.rage_timer + fs.anim.rage_duration) {
    fs.anim.rage = false
    fs.fx.fire_pixels.length = 0
  }
  if (fs.anim.surprise && now > fs.anim.surprise_timer + fs.anim.surprise_duration)
    fs.anim.surprise = false
  if (fs.anim.sleepy && now > fs.anim.sleepy_timer + fs.anim.sleepy_duration) fs.anim.sleepy = false
  if (fs.anim.nod && now > fs.anim.nod_timer + fs.anim.nod_duration) fs.anim.nod = false
  if (fs.anim.headshake && now > fs.anim.headshake_timer + fs.anim.headshake_duration)
    fs.anim.headshake = false
  if (fs.anim.confused) {
    if (fs.anim.confused_toggle) {
      fs.anim.h_flicker = true
      fs.anim.h_flicker_amp = FLICKER_AMP
      fs.anim.confused_toggle = false
    }
    if (now > fs.anim.confused_timer + fs.anim.confused_duration) {
      fs.anim.confused = false
      fs.anim.h_flicker = false
      fs.anim.confused_toggle = true
    }
  }
  if (fs.anim.laugh) {
    if (fs.anim.laugh_toggle) {
      fs.anim.v_flicker = true
      fs.anim.v_flicker_amp = FLICKER_AMP
      fs.anim.laugh_toggle = false
    }
    if (now > fs.anim.laugh_timer + fs.anim.laugh_duration) {
      fs.anim.laugh = false
      fs.anim.v_flicker = false
      fs.anim.laugh_toggle = true
    }
  }
  if (fs.anim.peek_a_boo && now > fs.anim.peek_a_boo_timer + fs.anim.peek_a_boo_duration)
    fs.anim.peek_a_boo = false
  if (fs.anim.shy && now > fs.anim.shy_timer + fs.anim.shy_duration) fs.anim.shy = false
  if (fs.anim.eye_roll && now > fs.anim.eye_roll_timer + fs.anim.eye_roll_duration)
    fs.anim.eye_roll = false
  if (fs.anim.dizzy && now > fs.anim.dizzy_timer + fs.anim.dizzy_duration) fs.anim.dizzy = false
  if (fs.anim.celebrate && now > fs.anim.celebrate_timer + fs.anim.celebrate_duration)
    fs.anim.celebrate = false
  if (
    fs.anim.startle_relief &&
    now > fs.anim.startle_relief_timer + fs.anim.startle_relief_duration
  )
    fs.anim.startle_relief = false
  if (fs.anim.thinking_hard && now > fs.anim.thinking_hard_timer + fs.anim.thinking_hard_duration)
    fs.anim.thinking_hard = false

  // ── 4. BLINK LOGIC ───────────────────────────────────────
  if (fs.anim.autoblink && now >= fs.anim.next_blink) {
    faceBlink(fs)
    fs.anim.next_blink = now + BLINK_INTERVAL + Math.random() * BLINK_VARIATION
  }

  // Per-eye blink reopening
  if (!fs.eye_l.is_open && fs.eyelids.top_l > 0.95) fs.eye_l.is_open = true
  if (!fs.eye_r.is_open && fs.eyelids.top_r > 0.95) fs.eye_r.is_open = true

  const closureL = fs.eye_l.is_open ? 0.0 : 1.0
  const closureR = fs.eye_r.is_open ? 0.0 : 1.0
  const finalTopL = Math.max(tLidTop, closureL)
  let finalTopR = Math.max(tLidTop, closureR)

  // Curious: asymmetric brow
  if (fs.mood === Mood.CURIOUS) {
    const ci = Math.max(0.0, Math.min(1.0, fs.expression_intensity))
    finalTopR = Math.max(finalTopR, CURIOUS_BROW_OFFSET * ci)
  }

  const speedL = finalTopL > fs.eyelids.top_l ? TWEEN_EYELID_TOP_CLOSING : TWEEN_EYELID_TOP_OPENING
  const speedR = finalTopR > fs.eyelids.top_r ? TWEEN_EYELID_TOP_CLOSING : TWEEN_EYELID_TOP_OPENING
  fs.eyelids.top_l = tween(fs.eyelids.top_l, finalTopL, speedL)
  fs.eyelids.top_r = tween(fs.eyelids.top_r, finalTopR, speedR)
  fs.eyelids.bottom_l = tween(fs.eyelids.bottom_l, tLidBot, TWEEN_EYELID_BOT)
  fs.eyelids.bottom_r = tween(fs.eyelids.bottom_r, tLidBot, TWEEN_EYELID_BOT)
  fs.eyelids.slope = tween(fs.eyelids.slope, fs.eyelids.slope_target, TWEEN_EYELID_SLOPE)

  // ── 5. IDLE GAZE WANDER ──────────────────────────────────
  if (fs.anim.idle && now >= fs.anim.next_idle) {
    const targetX = (Math.random() * 2.0 - 1.0) * MAX_GAZE
    const targetY = (Math.random() * 2.0 - 1.0) * MAX_GAZE * 0.6

    if (fs.mood === Mood.SILLY) {
      const si = Math.max(0.0, Math.min(1.0, fs.expression_intensity))
      if (Math.random() < 0.5) {
        fs.eye_l.gaze_x_target = SILLY_CROSS_EYE_A[0] * si
        fs.eye_r.gaze_x_target = SILLY_CROSS_EYE_A[1] * si
      } else {
        fs.eye_l.gaze_x_target = SILLY_CROSS_EYE_B[0] * si
        fs.eye_r.gaze_x_target = SILLY_CROSS_EYE_B[1] * si
      }
    } else if (fs.mood === Mood.LOVE) {
      const amp = LOVE_IDLE_AMPLITUDE
      fs.eye_l.gaze_x_target = targetX * amp + LOVE_CONVERGENCE_X
      fs.eye_r.gaze_x_target = targetX * amp - LOVE_CONVERGENCE_X
    } else {
      fs.eye_l.gaze_x_target = targetX
      fs.eye_r.gaze_x_target = targetX
    }

    if (fs.mood === Mood.LOVE) {
      fs.eye_l.gaze_y_target = targetY * LOVE_IDLE_AMPLITUDE
      fs.eye_r.gaze_y_target = targetY * LOVE_IDLE_AMPLITUDE
      fs.anim.next_idle = now + LOVE_IDLE_HOLD_MIN + Math.random() * LOVE_IDLE_HOLD_RANGE
    } else {
      fs.eye_l.gaze_y_target = targetY
      fs.eye_r.gaze_y_target = targetY
      fs.anim.next_idle = now + IDLE_GAZE_HOLD_MIN + Math.random() * IDLE_GAZE_HOLD_RANGE
    }
  }

  // Saccade jitter
  if (now > fs.anim.next_saccade) {
    const jx = (Math.random() * 2.0 - 1.0) * SACCADE_JITTER
    const jy = (Math.random() * 2.0 - 1.0) * SACCADE_JITTER
    fs.eye_l.gaze_x += jx
    fs.eye_r.gaze_x += jx
    fs.eye_l.gaze_y += jy
    fs.eye_r.gaze_y += jy
    fs.anim.next_saccade =
      now + SACCADE_INTERVAL_MIN + Math.random() * (SACCADE_INTERVAL_MAX - SACCADE_INTERVAL_MIN)
  }

  // ── 5b. IDLE MICRO-EXPRESSIONS ───────────────────────────
  if (
    fs.anim.idle &&
    !fs.talking &&
    fs.active_gesture === 0xff &&
    fs.system.mode === SystemMode.NONE
  ) {
    if (!fs.anim.micro_expr_active) {
      if (fs.anim.micro_expr_next === 0.0) {
        fs.anim.micro_expr_next = now + MICRO_EXPR_MIN_INTERVAL + Math.random() * MICRO_EXPR_RANGE
      } else if (now >= fs.anim.micro_expr_next) {
        fs.anim.micro_expr_type = 1 + ((Math.random() * 3) | 0)
        fs.anim.micro_expr_timer = now
        fs.anim.micro_expr_active = true
      }
    } else {
      const elapsedM = now - fs.anim.micro_expr_timer
      const mtype = fs.anim.micro_expr_type
      let done = false

      if (mtype === 1) {
        // Curious glance
        if (elapsedM < MICRO_EXPR_CURIOUS_DUR) {
          const fracM = elapsedM / MICRO_EXPR_CURIOUS_DUR
          const brow = CURIOUS_BROW_OFFSET * Math.sin(fracM * Math.PI)
          fs.eyelids.top_r = Math.max(fs.eyelids.top_r, brow)
          const shift = 4.0 * Math.sin(fracM * Math.PI)
          fs.eye_l.gaze_x_target += shift
          fs.eye_r.gaze_x_target += shift
        } else {
          done = true
        }
      } else if (mtype === 2) {
        // Content sigh
        if (elapsedM < MICRO_EXPR_SIGH_DUR) {
          const fracM = elapsedM / MICRO_EXPR_SIGH_DUR
          const droopVal = 0.3 * Math.sin(fracM * Math.PI)
          tLidTop = Math.max(tLidTop, droopVal)
          fs.mouth_curve_target = Math.max(fs.mouth_curve_target, 0.3)
        } else {
          done = true
        }
      } else if (mtype === 3) {
        // Fidget (quick double-blink)
        if (elapsedM < MICRO_EXPR_FIDGET_DUR) {
          if (elapsedM < 0.05) faceBlink(fs)
          else if (elapsedM > 0.18 && elapsedM < 0.22) faceBlink(fs)
        } else {
          done = true
        }
      }

      if (done) {
        fs.anim.micro_expr_active = false
        fs.anim.micro_expr_type = 0
        fs.anim.micro_expr_next = now + MICRO_EXPR_MIN_INTERVAL + Math.random() * MICRO_EXPR_RANGE
      }
    }
  }

  // ── 6. TALKING ───────────────────────────────────────────
  if (fs.talking) {
    fs.talking_phase += TALKING_PHASE_SPEED * dt
    const e = Math.max(0.0, Math.min(1.0, fs.talking_energy))
    const noiseOpen = Math.sin(fs.talking_phase) + Math.sin(fs.talking_phase * 2.3)
    const noiseWidth = Math.cos(fs.talking_phase * 0.7)

    const baseOpen = TALKING_BASE_OPEN + TALKING_OPEN_MOD * e
    const modOpen = Math.abs(noiseOpen) * 0.6 * e
    const modWidth = noiseWidth * TALKING_WIDTH_MOD * e

    fs.mouth_open_target = Math.max(fs.mouth_open_target, baseOpen + modOpen)
    fs.mouth_width_target = 1.0 + modWidth

    const bounce = Math.abs(Math.sin(fs.talking_phase)) * TALKING_BOUNCE_MOD * e
    fs.eye_l.height_scale_target += bounce
    fs.eye_r.height_scale_target += bounce

    // Speech rhythm: eye energy pulses
    if (e > SPEECH_EYE_PULSE_THRESHOLD) {
      fs._speech_high_frames += 1
      if (fs._speech_high_frames >= SPEECH_EYE_PULSE_FRAMES) {
        fs._speech_eye_pulse = SPEECH_EYE_PULSE_AMOUNT
      }
    } else {
      fs._speech_high_frames = 0
    }
    if (fs._speech_eye_pulse > 0.001) {
      fs.eye_l.height_scale_target += fs._speech_eye_pulse
      fs.eye_r.height_scale_target += fs._speech_eye_pulse
      fs._speech_eye_pulse *= SPEECH_EYE_PULSE_DECAY
    }

    // Speech rhythm: pause gaze shift
    if (e < SPEECH_PAUSE_THRESHOLD) {
      fs._speech_low_frames += 1
      if (fs._speech_low_frames >= SPEECH_PAUSE_FRAMES && !fs._speech_pause_fired) {
        const shift = SPEECH_PAUSE_GAZE_SHIFT * (Math.random() < 0.5 ? 1.0 : -1.0)
        fs.eye_l.gaze_x_target += shift
        fs.eye_r.gaze_x_target += shift
        fs._speech_pause_fired = true
      }
    } else {
      fs._speech_low_frames = 0
      fs._speech_pause_fired = false
    }
  } else {
    fs._speech_high_frames = 0
    fs._speech_eye_pulse = 0.0
    fs._speech_low_frames = 0
    fs._speech_pause_fired = false
  }

  // ── 7. UPDATE TWEENS + SPRING ────────────────────────────
  for (const eye of [fs.eye_l, fs.eye_r]) {
    ;[eye.gaze_x, eye.vx] = spring(eye.gaze_x, eye.gaze_x_target, eye.vx)
    ;[eye.gaze_y, eye.vy] = spring(eye.gaze_y, eye.gaze_y_target, eye.vy)
    eye.width_scale = tween(eye.width_scale, eye.width_scale_target, TWEEN_EYE_SCALE)
    eye.height_scale = tween(eye.height_scale, eye.height_scale_target, TWEEN_EYE_SCALE)
    eye.openness_target = eye.is_open ? 1.0 : 0.0
    eye.openness = tween(eye.openness, eye.openness_target, TWEEN_OPENNESS)
    eye.width_scale_target = 1.0
    eye.height_scale_target = 1.0
  }

  fs.mouth_curve = tween(fs.mouth_curve, fs.mouth_curve_target, TWEEN_MOUTH_CURVE)
  fs.mouth_open = tween(fs.mouth_open, fs.mouth_open_target, TWEEN_MOUTH_OPEN)
  fs.mouth_width = tween(fs.mouth_width, fs.mouth_width_target, TWEEN_MOUTH_WIDTH)
  fs.mouth_offset_x = tween(fs.mouth_offset_x, fs.mouth_offset_x_target, TWEEN_MOUTH_OFFSET_X)
  fs.mouth_wave = tween(fs.mouth_wave, fs.mouth_wave_target, TWEEN_MOUTH_WAVE)

  // Flicker post-processing
  if (fs.anim.h_flicker) {
    const dx = fs.anim.h_flicker_alt ? fs.anim.h_flicker_amp : -fs.anim.h_flicker_amp
    fs.eye_l.gaze_x += dx
    fs.eye_r.gaze_x += dx
    fs.anim.h_flicker_alt = !fs.anim.h_flicker_alt
  }
  if (fs.anim.v_flicker) {
    const dy = fs.anim.v_flicker_alt ? fs.anim.v_flicker_amp : -fs.anim.v_flicker_amp
    fs.eye_l.gaze_y += dy
    fs.eye_r.gaze_y += dy
    fs.anim.v_flicker_alt = !fs.anim.v_flicker_alt
  }

  // NOD/HEADSHAKE post-spring gaze overrides
  if (fs.anim.nod) {
    const elapsedG = now - fs.anim.nod_timer
    const gazeY = NOD_GAZE_Y_AMP * Math.sin(elapsedG * NOD_FREQ)
    fs.eye_l.gaze_y = gazeY
    fs.eye_r.gaze_y = gazeY
  }
  if (fs.anim.headshake) {
    const elapsedG = now - fs.anim.headshake_timer
    const gazeX = HEADSHAKE_GAZE_X_AMP * Math.sin(elapsedG * HEADSHAKE_FREQ)
    fs.eye_l.gaze_x = gazeX
    fs.eye_r.gaze_x = gazeX
  }

  // EYE_ROLL / DIZZY post-spring gaze overrides
  if (fs.anim.eye_roll) {
    const elapsedG = now - fs.anim.eye_roll_timer
    const dur = Math.max(0.01, fs.anim.eye_roll_duration)
    const frac = elapsedG / dur
    if (frac < 0.8) {
      const angle = (frac / 0.8) * 2.0 * Math.PI
      const gx = EYE_ROLL_GAZE_R * Math.sin(angle)
      const gy = -EYE_ROLL_GAZE_R * Math.cos(angle)
      fs.eye_l.gaze_x = gx
      fs.eye_r.gaze_x = gx
      fs.eye_l.gaze_y = gy
      fs.eye_r.gaze_y = gy
    }
  }

  if (fs.anim.dizzy) {
    const elapsedG = now - fs.anim.dizzy_timer
    const dur = Math.max(0.01, fs.anim.dizzy_duration)
    const frac = elapsedG / dur
    let amp: number
    if (frac < 0.5) {
      amp = DIZZY_GAZE_R_MAX * (frac / 0.5)
    } else {
      amp = DIZZY_GAZE_R_MAX * (1.0 - (frac - 0.5) / 0.5)
    }
    const angle = elapsedG * DIZZY_FREQ
    const gx = amp * Math.sin(angle)
    const gy = amp * Math.cos(angle)
    fs.eye_l.gaze_x = gx + 1.0
    fs.eye_r.gaze_x = gx - 1.0
    fs.eye_l.gaze_y = gy
    fs.eye_r.gaze_y = gy
  }

  // ── 8. BREATHING ─────────────────────────────────────────
  if (fs.fx.breathing) {
    let speed = BREATH_SPEED
    if (fs.talking) {
      const e = Math.max(0.0, Math.min(1.0, fs.talking_energy))
      speed = BREATH_SPEED + (e - 0.5) * SPEECH_BREATH_MOD
      speed = Math.max(SPEECH_BREATH_MIN, Math.min(SPEECH_BREATH_MAX, speed))
    } else if (fs.holiday_mode === HolidayMode.CHRISTMAS) {
      speed = HOLIDAY_CHRISTMAS_BREATH_SPEED
    }
    fs.fx.breath_phase += speed / 30.0
    if (fs.fx.breath_phase > 6.28) fs.fx.breath_phase -= 6.28
  }

  // ── 9. SPARKLES ──────────────────────────────────────────
  if (fs.fx.sparkle) {
    fs.fx.sparkle_pixels = fs.fx.sparkle_pixels.filter(([_x, _y, life]) => life > 0)
    for (let i = 0; i < fs.fx.sparkle_pixels.length; i++) {
      const p = fs.fx.sparkle_pixels[i]
      fs.fx.sparkle_pixels[i] = [p[0], p[1], p[2] - 1]
    }
    let chance = SPARKLE_CHANCE
    if (fs.anim.celebrate) chance = CELEBRATE_SPARKLE_BOOST
    else if (fs.holiday_mode === HolidayMode.BIRTHDAY) chance = HOLIDAY_BIRTHDAY_SPARKLE
    if (Math.random() < chance) {
      fs.fx.sparkle_pixels.push([
        (Math.random() * SCREEN_W) | 0,
        (Math.random() * SCREEN_H) | 0,
        SPARKLE_LIFE_MIN + ((Math.random() * (SPARKLE_LIFE_MAX - SPARKLE_LIFE_MIN)) | 0),
      ])
    }
  } else {
    fs.fx.sparkle_pixels.length = 0
  }

  // ── 10. FIRE/SNOW/CONFETTI ───────────────────────────────
  updateFire(fs)
  updateSnow(fs)
  updateConfetti(fs)

  // Expire active gesture
  if (fs.active_gesture !== 0xff && now > fs.active_gesture_until) {
    fs.active_gesture = 0xff
  }
}

// ── Effects helpers ─────────────────────────────────────────────

function updateFire(fs: FaceState): void {
  if (!fs.anim.rage) {
    fs.fx.fire_pixels.length = 0
    return
  }
  fs.fx.fire_pixels = fs.fx.fire_pixels
    .filter(([_x, y, life]) => life > 1 && y > 0)
    .map(([x, y, life, heat]) => [
      x + (Math.random() * 2 - 1) * FIRE_DRIFT,
      y - FIRE_RISE_SPEED,
      life - 1,
      heat * FIRE_HEAT_DECAY,
    ])
  if (Math.random() < FIRE_SPAWN_CHANCE) {
    for (const cx of [LEFT_EYE_CX, RIGHT_EYE_CX]) {
      const x = cx + (Math.random() * 40 - 20)
      const y = LEFT_EYE_CY - 30
      fs.fx.fire_pixels.push([
        x,
        y,
        SPARKLE_LIFE_MIN + ((Math.random() * (SPARKLE_LIFE_MAX - SPARKLE_LIFE_MIN)) | 0),
        1.0,
      ])
    }
  }
}

function updateSnow(fs: FaceState): void {
  if (fs.holiday_mode !== HolidayMode.CHRISTMAS) {
    fs.fx.snow_pixels.length = 0
    return
  }
  fs.fx.snow_pixels = fs.fx.snow_pixels
    .filter(([_x, y, life]) => life > 0 && y < SCREEN_H)
    .map(([x, y, life, phase]) => [
      x + Math.sin(phase + y * 0.05) * HOLIDAY_SNOW_DRIFT_AMP,
      y + HOLIDAY_SNOW_FALL_SPEED,
      life - 1,
      phase,
    ])
  if (Math.random() < HOLIDAY_SNOW_SPAWN_CHANCE) {
    fs.fx.snow_pixels.push([
      (Math.random() * SCREEN_W) | 0,
      0.0,
      HOLIDAY_SNOW_LIFE_MIN +
        ((Math.random() * (HOLIDAY_SNOW_LIFE_MAX - HOLIDAY_SNOW_LIFE_MIN)) | 0),
      Math.random() * 6.28,
    ])
  }
}

function updateConfetti(fs: FaceState): void {
  if (fs.holiday_mode !== HolidayMode.NEW_YEAR) {
    fs.fx.confetti_pixels.length = 0
    return
  }
  fs.fx.confetti_pixels = fs.fx.confetti_pixels
    .filter(([_x, y, life]) => life > 0 && y < SCREEN_H)
    .map(([x, y, life, ci]) => [
      x + (Math.random() * 2 - 1) * HOLIDAY_CONFETTI_DRIFT,
      y + HOLIDAY_CONFETTI_FALL_SPEED,
      life - 1,
      ci,
    ])
  if (Math.random() < HOLIDAY_CONFETTI_SPAWN_CHANCE) {
    fs.fx.confetti_pixels.push([
      (Math.random() * SCREEN_W) | 0,
      0.0,
      HOLIDAY_CONFETTI_LIFE_MIN +
        ((Math.random() * (HOLIDAY_CONFETTI_LIFE_MAX - HOLIDAY_CONFETTI_LIFE_MIN)) | 0),
      (Math.random() * HOLIDAY_CONFETTI_COLORS.length) | 0,
    ])
  }
}

function updateHoliday(fs: FaceState, now: number): void {
  const mode = fs.holiday_mode
  if (mode === HolidayMode.NONE) return

  if (mode === HolidayMode.BIRTHDAY) {
    fs.mood = Mood.HAPPY
    fs.expression_intensity = 1.0
    const cycle = ((now * 1.5) | 0) % 2
    fs.mood_color_override =
      cycle === 0 ? [...HOLIDAY_BIRTHDAY_COLOR_A] : [...HOLIDAY_BIRTHDAY_COLOR_B]
    if (fs._holiday_timer === 0.0) {
      fs._holiday_timer = now + HOLIDAY_BIRTHDAY_CELEBRATE_INTERVAL
    } else if (now >= fs._holiday_timer) {
      faceTriggerGesture(fs, GestureId.CELEBRATE)
      fs._holiday_timer = now + HOLIDAY_BIRTHDAY_CELEBRATE_INTERVAL
    }
  } else if (mode === HolidayMode.HALLOWEEN) {
    const flicker = 1.0 + (Math.random() * 2 - 1) * HOLIDAY_HALLOWEEN_FLICKER
    const r = Math.min(255, (HOLIDAY_HALLOWEEN_COLOR[0] * flicker) | 0)
    const g = Math.min(255, (HOLIDAY_HALLOWEEN_COLOR[1] * flicker) | 0)
    const b = Math.min(255, (HOLIDAY_HALLOWEEN_COLOR[2] * flicker) | 0)
    fs.mood_color_override = [r, g, b]
    fs.eyelids.slope_target = HOLIDAY_HALLOWEEN_LID_SLOPE
    fs.mouth_wave_target = 1.0
    fs.mouth_curve_target = -0.3
    fs.mouth_open_target = 0.4
  } else if (mode === HolidayMode.CHRISTMAS) {
    fs.mood = Mood.HAPPY
    fs.expression_intensity = 0.5
    fs.mood_color_override = [...HOLIDAY_CHRISTMAS_COLOR]
  } else if (mode === HolidayMode.NEW_YEAR) {
    fs.mood = Mood.EXCITED
    fs.expression_intensity = 1.0
    fs.fx.afterglow = true
    if (fs._holiday_timer === 0.0) {
      fs._holiday_timer = now + 4.0
    } else if (now >= fs._holiday_timer) {
      faceTriggerGesture(fs, GestureId.CELEBRATE)
      fs._holiday_timer = now + 4.0 + Math.random() * 3.0
    }
  }
}
