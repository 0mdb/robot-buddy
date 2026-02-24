/**
 * Face animation state machine — per-frame update logic.
 *
 * Ported from tools/face_sim_v3/state/face_state.py.
 * Phase 1-3: core update (mood targets, tweens, spring, blink, breathing,
 * idle wander, saccade, talking). Full gestures/effects/holidays deferred.
 */

import {
  BLINK_INTERVAL,
  BLINK_VARIATION,
  BREATH_AMOUNT,
  BREATH_SPEED,
  GESTURE_DURATIONS,
  GestureId,
  IDLE_GAZE_HOLD_MIN,
  IDLE_GAZE_HOLD_RANGE,
  MAX_GAZE,
  Mood,
  type RGB,
  SACCADE_INTERVAL_MAX,
  SACCADE_INTERVAL_MIN,
  SACCADE_JITTER,
  SCREEN_H,
  SCREEN_W,
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
  SystemMode,
  TALKING_BASE_OPEN,
  TALKING_BOUNCE_MOD,
  TALKING_OPEN_MOD,
  TALKING_PHASE_SPEED,
  TALKING_WIDTH_MOD,
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
} from './constants'
import {
  CONFUSED_MOOD_MOUTH_OFFSET_X,
  CURIOUS_BROW_OFFSET,
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
  } else {
    // Other gestures: just set active_gesture tracker
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
  // afterglow flag (0x40) — deferred, no afterglow buffer yet
}

// ── Per-frame update ───────────────────────────────────────────

export function faceStateUpdate(fs: FaceState, dt: number): void {
  const now = performance.now() / 1000.0

  // Skip update if system mode is active (deferred)
  if (fs.system.mode !== SystemMode.NONE) return

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

  // ── 2. GESTURE TIMEOUTS ──────────────────────────────────
  if (fs.anim.heart && now > fs.anim.heart_timer + fs.anim.heart_duration) fs.anim.heart = false
  if (fs.anim.x_eyes && now > fs.anim.x_eyes_timer + fs.anim.x_eyes_duration) fs.anim.x_eyes = false
  if (fs.anim.rage && now > fs.anim.rage_timer + fs.anim.rage_duration) fs.anim.rage = false
  if (fs.anim.surprise && now > fs.anim.surprise_timer + fs.anim.surprise_duration)
    fs.anim.surprise = false
  if (fs.anim.sleepy && now > fs.anim.sleepy_timer + fs.anim.sleepy_duration) fs.anim.sleepy = false
  if (fs.anim.nod && now > fs.anim.nod_timer + fs.anim.nod_duration) fs.anim.nod = false
  if (fs.anim.headshake && now > fs.anim.headshake_timer + fs.anim.headshake_duration)
    fs.anim.headshake = false
  if (fs.anim.confused) {
    if (fs.anim.confused_toggle) {
      fs.anim.h_flicker = true
      fs.anim.h_flicker_amp = 1.5
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
      fs.anim.v_flicker_amp = 1.5
      fs.anim.laugh_toggle = false
    }
    if (now > fs.anim.laugh_timer + fs.anim.laugh_duration) {
      fs.anim.laugh = false
      fs.anim.v_flicker = false
      fs.anim.laugh_toggle = true
    }
  }

  // ── 3. BLINK LOGIC ───────────────────────────────────────
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

  // ── 4. IDLE GAZE WANDER ──────────────────────────────────
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

  // ── 5. TALKING ───────────────────────────────────────────
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

  // ── 6. UPDATE TWEENS + SPRING ────────────────────────────
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
    const gazeY = 4.0 * Math.sin(elapsedG * 12.0)
    fs.eye_l.gaze_y = gazeY
    fs.eye_r.gaze_y = gazeY
  }
  if (fs.anim.headshake) {
    const elapsedG = now - fs.anim.headshake_timer
    const gazeX = 5.0 * Math.sin(elapsedG * 14.0)
    fs.eye_l.gaze_x = gazeX
    fs.eye_r.gaze_x = gazeX
  }

  // ── 7. BREATHING ─────────────────────────────────────────
  if (fs.fx.breathing) {
    let speed = BREATH_SPEED
    if (fs.talking) {
      const e = Math.max(0.0, Math.min(1.0, fs.talking_energy))
      speed = BREATH_SPEED + (e - 0.5) * SPEECH_BREATH_MOD
      speed = Math.max(SPEECH_BREATH_MIN, Math.min(SPEECH_BREATH_MAX, speed))
    }
    fs.fx.breath_phase += speed / 30.0
    if (fs.fx.breath_phase > 6.28) fs.fx.breath_phase -= 6.28
  }

  // ── 8. SPARKLES ──────────────────────────────────────────
  if (fs.fx.sparkle) {
    fs.fx.sparkle_pixels = fs.fx.sparkle_pixels.filter(([_x, _y, life]) => life > 0)
    for (let i = 0; i < fs.fx.sparkle_pixels.length; i++) {
      const p = fs.fx.sparkle_pixels[i]
      fs.fx.sparkle_pixels[i] = [p[0], p[1], p[2] - 1]
    }
    if (Math.random() < SPARKLE_CHANCE) {
      fs.fx.sparkle_pixels.push([
        (Math.random() * SCREEN_W) | 0,
        (Math.random() * SCREEN_H) | 0,
        SPARKLE_LIFE_MIN + ((Math.random() * (SPARKLE_LIFE_MAX - SPARKLE_LIFE_MIN)) | 0),
      ])
    }
  } else {
    fs.fx.sparkle_pixels.length = 0
  }

  // Expire active gesture
  if (fs.active_gesture !== 0xff && now > fs.active_gesture_until) {
    fs.active_gesture = 0xff
  }
}
