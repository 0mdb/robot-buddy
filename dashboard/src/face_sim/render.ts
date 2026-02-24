/**
 * Face renderer — eyes, mouth, system modes, effects into ImageData pixel buffer.
 *
 * Ported from tools/face_sim_v3/render/face.py + effects.py.
 * Phases 1-5: eyes, mouth, heart/X-eyes SDF, system modes,
 * fire, afterglow, snow, confetti, rosy cheeks, border integration.
 */

import {
  AFTERGLOW_DECAY,
  BG_COLOR,
  EDGE_GLOW_FALLOFF,
  EYE_CORNER_R,
  EYE_HEIGHT,
  EYE_WIDTH,
  GAZE_EYE_SHIFT,
  GAZE_PUPIL_SHIFT,
  HEART_PUPIL_SCALE,
  HEART_SOLID_SCALE,
  HOLIDAY_CONFETTI_COLORS,
  HolidayMode,
  LEFT_EYE_CX,
  LEFT_EYE_CY,
  MOUTH_CX,
  MOUTH_CY,
  MOUTH_HALF_W,
  MOUTH_THICKNESS,
  PUPIL_COLOR,
  PUPIL_R,
  type RGB,
  RIGHT_EYE_CX,
  RIGHT_EYE_CY,
  ROSY_CHEEK_ALPHA,
  ROSY_CHEEK_COLOR,
  ROSY_CHEEK_R,
  ROSY_CHEEK_X_OFFSET,
  ROSY_CHEEK_Y_OFFSET,
  SCREEN_H,
  SCREEN_W,
  SystemMode,
} from './constants'
import {
  sdCircle,
  sdCross,
  sdEquilateralTriangle,
  sdfAlpha,
  sdHeart,
  sdRoundedBox,
  setPxBlend,
  smoothstep,
} from './sdf'
import { getBreathScale, getEmotionColor } from './state'
import type { FaceState } from './types'

function clamp(x: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, x))
}

// ── System animation face drivers ─────────────────────────────

function sysBooting(fs: FaceState): void {
  const elapsed = performance.now() / 1000.0 - fs.system.timer
  const BOOT_DUR = 3.0
  const t = clamp(elapsed / BOOT_DUR, 0.0, 1.0)

  if (t < 0.4) {
    const p = t / 0.4
    const droop = 0.6 * (1.0 - p)
    fs.eyelids.top_l = droop
    fs.eyelids.top_r = droop
    fs.eye_l.height_scale = 0.7 + 0.15 * p
    fs.eye_r.height_scale = 0.7 + 0.15 * p
    fs.eyelids.slope = -0.2 * (1.0 - p)
    fs.mood_color_override = [
      (70 + (50 - 70) * p) | 0,
      (90 + (150 - 90) * p) | 0,
      (140 + (255 - 140) * p) | 0,
    ]
  } else if (t < 0.65) {
    const p = (t - 0.4) / 0.25
    const yawn = Math.sin(p * Math.PI)
    fs.mouth_open = 0.6 * yawn
    fs.mouth_width = 1.0 + 0.2 * yawn
    fs.mouth_curve = -0.1 * yawn
    fs.eyelids.top_l = 0.15 * yawn
    fs.eyelids.top_r = 0.15 * yawn
    fs.eye_l.height_scale = 0.85 - 0.1 * yawn
    fs.eye_r.height_scale = 0.85 - 0.1 * yawn
    fs.mood_color_override = [50, 150, 255]
  } else if (t < 0.85) {
    const p = (t - 0.65) / 0.2
    const blink_p = Math.abs(p - 0.5) * 2.0
    fs.eyelids.top_l = p > 0.4 && p < 0.6 ? 0.7 * (1.0 - blink_p) : 0.0
    fs.eyelids.top_r = fs.eyelids.top_l
    fs.eye_l.height_scale = 1.0
    fs.eye_r.height_scale = 1.0
    fs.mood_color_override = [50, 150, 255]
  } else {
    const p = (t - 0.85) / 0.15
    const bounce = Math.sin(p * Math.PI) * 0.05
    fs.eye_l.height_scale = 1.0 + bounce
    fs.eye_r.height_scale = 1.0 + bounce
    fs.mouth_curve = 0.3 * Math.sin(p * Math.PI)
    fs.mood_color_override = [
      (50 + (0 - 50) * p) | 0,
      (150 + (255 - 150) * p) | 0,
      (255 + (200 - 255) * p) | 0,
    ]
  }
  fs.fx.breathing = t > 0.7
}

function sysShutdown(fs: FaceState): void {
  const elapsed = performance.now() / 1000.0 - fs.system.timer
  const SHUT_DUR = 2.5
  const t = clamp(elapsed / SHUT_DUR, 0.0, 1.0)

  if (t < 0.3) {
    const p = t / 0.3
    const yawn = Math.sin(p * Math.PI)
    fs.mouth_open = 0.5 * yawn
    fs.mouth_width = 1.0 + 0.15 * yawn
    fs.eyelids.top_l = 0.1 * yawn
    fs.eyelids.top_r = 0.1 * yawn
    fs.eye_l.height_scale = 1.0 - 0.1 * yawn
    fs.eye_r.height_scale = 1.0 - 0.1 * yawn
  } else if (t < 0.6) {
    const p = (t - 0.3) / 0.3
    const droop = 0.15 + 0.35 * p
    fs.eyelids.top_l = droop
    fs.eyelids.top_r = droop
    fs.eye_l.height_scale = 0.9 - 0.15 * p
    fs.eye_r.height_scale = 0.9 - 0.15 * p
    fs.eyelids.slope = -0.2 * p
    const sway_amp = 3.0 * (1.0 - p)
    const sway = Math.sin(elapsed * 2.0) * sway_amp
    fs.eye_l.gaze_x = sway
    fs.eye_r.gaze_x = sway
  } else if (t < 0.85) {
    const p = (t - 0.6) / 0.25
    fs.eyelids.top_l = 0.5 + 0.5 * p
    fs.eyelids.top_r = 0.5 + 0.5 * p
    fs.eye_l.height_scale = 0.75 - 0.35 * p
    fs.eye_r.height_scale = 0.75 - 0.35 * p
    fs.eyelids.slope = -0.2
    fs.mouth_curve = 0.3 * p
  } else {
    const p = (t - 0.85) / 0.15
    fs.eyelids.top_l = 1.0
    fs.eyelids.top_r = 1.0
    fs.eye_l.height_scale = 0.4
    fs.eye_r.height_scale = 0.4
    fs.mouth_curve = 0.3
    fs.brightness = 1.0 - p
  }

  if (t < 0.6) {
    const frac = t / 0.6
    fs.mood_color_override = [
      (50 * (1.0 - frac) + 70 * frac) | 0,
      (150 * (1.0 - frac) + 90 * frac) | 0,
      (255 * (1.0 - frac) + 140 * frac) | 0,
    ]
  } else {
    const frac = (t - 0.6) / 0.4
    fs.mood_color_override = [
      (70 * (1.0 - frac)) | 0,
      (90 * (1.0 - frac)) | 0,
      (140 * (1.0 - frac)) | 0,
    ]
  }
  fs.fx.breathing = t < 0.5
}

function sysError(fs: FaceState): void {
  const elapsed = performance.now() / 1000.0 - fs.system.timer
  fs.eyelids.slope = 0.2
  fs.eyelids.top_l = 0.1
  fs.eyelids.top_r = 0.1
  fs.mouth_curve = -0.2
  fs.mouth_offset_x = 2.0 * Math.sin(elapsed * 3.0)
  const shake = Math.sin(elapsed * 4.0) * 3.0
  fs.eye_l.gaze_x = shake
  fs.eye_r.gaze_x = shake
  fs.mood_color_override = [220, 160, 60]
  fs.expression_intensity = 0.7
}

function sysBattery(fs: FaceState): void {
  const elapsed = performance.now() / 1000.0 - fs.system.timer
  const lvl = clamp(fs.system.param, 0.0, 1.0)
  const droop = 0.4 + 0.2 * (1.0 - lvl)
  fs.eyelids.top_l = droop
  fs.eyelids.top_r = droop
  fs.eyelids.slope = -0.2
  fs.eye_l.height_scale = 0.75
  fs.eye_r.height_scale = 0.75
  if (lvl < 0.2) {
    const yawn_cycle = elapsed % 6.0
    if (yawn_cycle < 1.5) {
      const yawn = Math.sin((yawn_cycle / 1.5) * Math.PI)
      fs.mouth_open = 0.5 * yawn
      fs.mouth_width = 1.0 + 0.1 * yawn
      fs.eyelids.top_l = Math.min(0.8, droop + 0.2 * yawn)
      fs.eyelids.top_r = Math.min(0.8, droop + 0.2 * yawn)
    }
  }
  fs.fx.breathing = true
  const dim = 0.6 + 0.4 * lvl
  fs.mood_color_override = [(70 * dim) | 0, (90 * dim) | 0, (140 * dim) | 0]
  fs.brightness = 0.7 + 0.3 * lvl
}

function sysUpdating(fs: FaceState): void {
  const elapsed = performance.now() / 1000.0 - fs.system.timer
  fs.eyelids.slope = 0.4
  fs.eyelids.top_l = 0.2
  fs.eyelids.top_r = 0.2
  fs.mouth_curve = -0.1
  fs.mouth_offset_x = 1.5
  const drift_x = Math.sin(elapsed * 0.8) * 2.0
  const drift_y = Math.cos(elapsed * 0.6) * 1.5
  fs.eye_l.gaze_x = 6.0 + drift_x
  fs.eye_r.gaze_x = 6.0 + drift_x
  fs.eye_l.gaze_y = -4.0 + drift_y
  fs.eye_r.gaze_y = -4.0 + drift_y
  fs.mood_color_override = [80, 135, 220]
  fs.expression_intensity = 0.6
}

// ── System mode icon overlays ─────────────────────────────────

function sysErrorIcon(buf: Uint8ClampedArray): void {
  const icon_cx = SCREEN_W - 22
  const icon_cy = SCREEN_H - 22
  const icon_r = 10.0
  const x0 = Math.max(0, icon_cx - 14)
  const x1 = Math.min(SCREEN_W, icon_cx + 14)
  const y0 = Math.max(0, icon_cy - 14)
  const y1 = Math.min(SCREEN_H, icon_cy + 14)

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5
      const d_tri = sdEquilateralTriangle(px, py, icon_cx, icon_cy, icon_r)
      const alpha = 1.0 - smoothstep(0.0, 1.5, d_tri)
      if (alpha > 0.01) {
        setPxBlend(buf, row + x, 255, 180, 50, alpha)
      }
      const d_bar = sdRoundedBox(px, py, icon_cx, icon_cy - 2, 1.5, 4.0, 0.5)
      const d_dot = sdCircle(px, py, icon_cx, icon_cy + 4.5, 1.5)
      const d_mark = Math.min(d_bar, d_dot)
      const alpha_m = 1.0 - smoothstep(0.0, 1.0, d_mark)
      if (alpha_m > 0.01) {
        setPxBlend(buf, row + x, 0, 0, 0, alpha_m)
      }
    }
  }
}

function sysBatteryIcon(buf: Uint8ClampedArray, lvl: number): void {
  const bx = SCREEN_W - 24
  const by = SCREEN_H - 18
  const bw = 16
  const bh = 10
  let col: RGB
  if (lvl > 0.5) col = [0, 220, 100]
  else if (lvl > 0.2) col = [220, 180, 0]
  else col = [220, 40, 40]

  const x0 = Math.max(0, bx - 12)
  const x1 = Math.min(SCREEN_W, bx + 18)
  const y0 = Math.max(0, by - 8)
  const y1 = Math.min(SCREEN_H, by + 8)

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5
      const d_out = sdRoundedBox(px, py, bx, by, bw / 2, bh / 2, 1.5)
      const d_in = sdRoundedBox(px, py, bx, by, bw / 2 - 1.5, bh / 2 - 1.5, 0.5)
      const d_tip = sdRoundedBox(px, py, bx + bw / 2 + 2, by, 1.5, 3.0, 0.5)
      const d_shell = Math.min(Math.max(d_out, -d_in), d_tip)
      const alpha_s = 1.0 - smoothstep(0.0, 1.0, d_shell)
      if (alpha_s > 0.01) {
        setPxBlend(buf, row + x, 180, 180, 190, alpha_s)
      }
      const fill_right = bx - bw / 2 + 1.5 + (bw - 3) * lvl
      if (d_in < 0 && px < fill_right) {
        setPxBlend(buf, row + x, col[0], col[1], col[2], 0.9)
      }
    }
  }
}

function sysUpdatingBar(buf: Uint8ClampedArray, progress: number): void {
  const bar_y = SCREEN_H - 4
  const bar_h = 2
  const bar_x0 = 20
  const bar_x1 = SCREEN_W - 20
  const fill_x = (bar_x0 + (bar_x1 - bar_x0) * clamp(progress, 0.0, 1.0)) | 0

  for (let y = bar_y; y < Math.min(SCREEN_H, bar_y + bar_h); y++) {
    const row = y * SCREEN_W
    for (let x = bar_x0; x < bar_x1; x++) {
      if (x < fill_x) {
        setPxBlend(buf, row + x, 80, 135, 220, 0.8)
      } else {
        setPxBlend(buf, row + x, 30, 40, 60, 0.8)
      }
    }
  }
}

// ── Eye rendering ──────────────────────────────────────────────

function renderEye(buf: Uint8ClampedArray, fs: FaceState, isLeft: boolean): void {
  const eye = isLeft ? fs.eye_l : fs.eye_r
  const cxBase = isLeft ? LEFT_EYE_CX : RIGHT_EYE_CX
  const cyBase = isLeft ? LEFT_EYE_CY : RIGHT_EYE_CY
  const breath = getBreathScale(fs)
  const w = (EYE_WIDTH / 2.0) * eye.width_scale * breath
  const h = (EYE_HEIGHT / 2.0) * eye.height_scale * breath

  const maxOffsetX = w - PUPIL_R - 5.0
  const maxOffsetY = h - PUPIL_R - 5.0
  const shiftX = clamp(eye.gaze_x * GAZE_PUPIL_SHIFT, -maxOffsetX, maxOffsetX)
  const shiftY = clamp(eye.gaze_y * GAZE_PUPIL_SHIFT, -maxOffsetY, maxOffsetY)

  const cx = cxBase + eye.gaze_x * GAZE_EYE_SHIFT
  const cy = cyBase + eye.gaze_y * GAZE_EYE_SHIFT
  const pupilCx = cxBase + shiftX
  const pupilCy = cyBase + shiftY

  const lidTop = isLeft ? fs.eyelids.top_l : fs.eyelids.top_r
  const lidBot = isLeft ? fs.eyelids.bottom_l : fs.eyelids.bottom_r
  const lidSlope = fs.eyelids.slope

  const baseColor = getEmotionColor(fs)

  const x0 = Math.max(0, (cx - w - 10) | 0)
  const x1 = Math.min(SCREEN_W, (cx + w + 10) | 0)
  const y0 = Math.max(0, (cy - h - 10) | 0)
  const y1 = Math.min(SCREEN_H, (cy + h + 10) | 0)

  const br = fs.brightness

  // Solid-mode heart override — replace entire eye with heart SDF
  if (fs.solid_eye && fs.anim.heart) {
    const heartSize = Math.min(w, h) * HEART_SOLID_SCALE
    const drawR = (baseColor[0] * br) | 0
    const drawG = (baseColor[1] * br) | 0
    const drawB = (baseColor[2] * br) | 0
    for (let y = y0; y < y1; y++) {
      const rowIdx = y * SCREEN_W
      for (let x = x0; x < x1; x++) {
        const val = sdHeart(x + 0.5, y + 0.5, cxBase, cyBase, heartSize)
        const alpha = 1.0 - smoothstep(-0.5, 0.5, val)
        if (alpha > 0.01) {
          setPxBlend(buf, rowIdx + x, drawR, drawG, drawB, alpha)
        }
      }
    }
    return
  }

  // Solid-mode X-eyes override
  if (fs.solid_eye && fs.anim.x_eyes) {
    const xSize = Math.min(w, h) * 0.8
    const drawR = (baseColor[0] * br) | 0
    const drawG = (baseColor[1] * br) | 0
    const drawB = (baseColor[2] * br) | 0
    for (let y = y0; y < y1; y++) {
      const rowIdx = y * SCREEN_W
      for (let x = x0; x < x1; x++) {
        const dist_x = sdCross(x + 0.5, y + 0.5, cxBase, cyBase, xSize, 6.0)
        const alpha = 1.0 - smoothstep(-0.5, 0.5, dist_x)
        if (alpha > 0.01) {
          setPxBlend(buf, rowIdx + x, drawR, drawG, drawB, alpha)
        }
      }
    }
    return
  }

  // Normal eye rendering
  const maxWH = Math.max(w, h) * 1.5
  const hasEdgeGlow = fs.fx.edge_glow

  for (let y = y0; y < y1; y++) {
    const rowIdx = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5

      const distBox = sdRoundedBox(px, py, cx, cy, w, h, EYE_CORNER_R)
      const alphaShape = 1.0 - smoothstep(-0.5, 0.5, distBox)
      if (alphaShape <= 0.01) continue

      let normX = (px - cx) / w
      if (!isLeft) normX = -normX

      const slopeOff = lidSlope * 20.0 * normX
      const lidLimitT = cy - h + h * 2.0 * lidTop + slopeOff
      const lidLimitB = cy + h - h * 2.0 * lidBot

      const alphaLid = smoothstep(-1.0, 1.0, py - lidLimitT)
      const alphaLidB = smoothstep(-1.0, 1.0, lidLimitB - py)

      const finalAlpha = alphaShape * alphaLid * alphaLidB
      if (finalAlpha <= 0.01) continue

      let grad = 1.0
      if (hasEdgeGlow) {
        const distCenter = Math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
        grad = clamp(1.0 - EDGE_GLOW_FALLOFF * (distCenter / maxWH), 0.4, 1.0)
      }

      let r = (baseColor[0] * grad) | 0
      let g = (baseColor[1] * grad) | 0
      let b = (baseColor[2] * grad) | 0

      // Fade pupil as eyelids close
      const lidVis = 1.0 - smoothstep(0.25, 0.55, lidTop)

      if (!fs.solid_eye && lidVis > 0.01) {
        let alphaPupil: number
        if (fs.anim.heart) {
          const val = sdHeart(px, py, pupilCx, pupilCy, PUPIL_R * HEART_PUPIL_SCALE)
          alphaPupil = 1.0 - smoothstep(-0.5, 0.5, val)
        } else if (fs.anim.x_eyes) {
          const dist_x = sdCross(px, py, pupilCx, pupilCy, PUPIL_R, 6.0)
          alphaPupil = 1.0 - smoothstep(-0.5, 0.5, dist_x)
        } else {
          const distPupil = sdCircle(px, py, pupilCx, pupilCy, PUPIL_R)
          alphaPupil = 1.0 - smoothstep(-0.5, 0.5, distPupil)
        }
        alphaPupil *= finalAlpha * lidVis
        if (alphaPupil > 0) {
          r = (r * (1.0 - alphaPupil) + PUPIL_COLOR[0] * alphaPupil) | 0
          g = (g * (1.0 - alphaPupil) + PUPIL_COLOR[1] * alphaPupil) | 0
          b = (b * (1.0 - alphaPupil) + PUPIL_COLOR[2] * alphaPupil) | 0
        }
      }

      setPxBlend(buf, rowIdx + x, (r * br) | 0, (g * br) | 0, (b * br) | 0, finalAlpha)
    }
  }
}

// ── Mouth rendering ────────────────────────────────────────────

function renderMouth(buf: Uint8ClampedArray, fs: FaceState): void {
  if (!fs.show_mouth) return

  const col = getEmotionColor(fs)
  const br = fs.brightness
  const drawR = (col[0] * br) | 0
  const drawG = (col[1] * br) | 0
  const drawB = (col[2] * br) | 0

  const cx = MOUTH_CX + fs.mouth_offset_x * 10.0
  const cy = MOUTH_CY
  const w = MOUTH_HALF_W * fs.mouth_width
  const thick = MOUTH_THICKNESS
  const curve = fs.mouth_curve * 40.0
  const openness = fs.mouth_open * 40.0

  const x0 = (cx - w - thick) | 0
  const x1 = (cx + w + thick) | 0
  const y0 = (cy - Math.abs(curve) - openness - thick) | 0
  const y1 = (cy + Math.abs(curve) + openness + thick) | 0

  const halfThick = thick / 2.0

  for (let y = Math.max(0, y0); y < Math.min(SCREEN_H, y1); y++) {
    const rowIdx = y * SCREEN_W
    for (let x = Math.max(0, x0); x < Math.min(SCREEN_W, x1); x++) {
      const px = x + 0.5
      const py = y + 0.5
      const nx = (px - cx) / w
      if (Math.abs(nx) > 1.0) continue

      const shape = 1.0 - nx * nx
      const curveY = curve * shape
      const upperY = cy + curveY - openness * shape
      const lowerY = cy + curveY + openness * shape

      let dist: number
      if (openness > 1.0 && upperY < py && py < lowerY) {
        dist = 0.0
      } else {
        dist = Math.min(Math.abs(py - upperY), Math.abs(py - lowerY))
      }

      const alpha = 1.0 - smoothstep(halfThick - 1.0, halfThick + 1.0, dist)
      if (alpha > 0) {
        setPxBlend(buf, rowIdx + x, drawR, drawG, drawB, alpha)
      }
    }
  }
}

// ── Effects rendering ──────────────────────────────────────────

function renderSparkles(buf: Uint8ClampedArray, fs: FaceState): void {
  for (const [sx, sy, life] of fs.fx.sparkle_pixels) {
    if (sx >= 0 && sx < SCREEN_W && sy >= 0 && sy < SCREEN_H) {
      const idx = sy * SCREEN_W + sx
      setPxBlend(buf, idx, 255, 255, 255, Math.min(1.0, life / 5.0))
    }
  }
}

function renderFire(buf: Uint8ClampedArray, fs: FaceState): void {
  for (const [fx, fy, life, heat] of fs.fx.fire_pixels) {
    const ix = fx | 0
    const iy = fy | 0
    let r: number
    let g: number
    let b: number
    if (heat > 0.85) {
      r = 255
      g = 220
      b = 120
    } else if (heat > 0.65) {
      r = 255
      g = 140
      b = 20
    } else if (heat > 0.4) {
      r = 220
      g = 50
      b = 0
    } else {
      r = 130
      g = 20
      b = 0
    }
    const fade = Math.min(1.0, life / 5.0)
    const fr = (r * fade) | 0
    const fg = (g * fade) | 0
    const fb = (b * fade) | 0
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        const px = ix + dx
        const py = iy + dy
        if (px >= 0 && px < SCREEN_W && py >= 0 && py < SCREEN_H) {
          const idx = py * SCREEN_W + px
          const off = idx * 4
          // Max-blend (additive fire effect)
          buf[off] = Math.max(buf[off], fr)
          buf[off + 1] = Math.max(buf[off + 1], fg)
          buf[off + 2] = Math.max(buf[off + 2], fb)
        }
      }
    }
  }
}

function applyAfterglow(buf: Uint8ClampedArray, fs: FaceState): void {
  const prev = fs.fx.afterglow_buf
  if (!prev) return

  for (let i = 0; i < SCREEN_W * SCREEN_H; i++) {
    const off = i * 4
    const cr = buf[off]
    const cg = buf[off + 1]
    const cb = buf[off + 2]
    const pr = prev[off]
    const pg = prev[off + 1]
    const pb = prev[off + 2]
    // Only apply afterglow where current pixel is background-dark
    if (cr <= BG_COLOR[0] && cg <= BG_COLOR[1] && cb <= BG_COLOR[2]) {
      if (pr > BG_COLOR[0] || pg > BG_COLOR[1] || pb > BG_COLOR[2]) {
        buf[off] = Math.max(BG_COLOR[0], (pr * AFTERGLOW_DECAY) | 0)
        buf[off + 1] = Math.max(BG_COLOR[1], (pg * AFTERGLOW_DECAY) | 0)
        buf[off + 2] = Math.max(BG_COLOR[2], (pb * AFTERGLOW_DECAY) | 0)
      }
    }
  }
}

function renderSnow(buf: Uint8ClampedArray, fs: FaceState): void {
  for (const [sx, sy, life] of fs.fx.snow_pixels) {
    const ix = sx | 0
    const iy = sy | 0
    if (ix >= 0 && ix < SCREEN_W && iy >= 0 && iy < SCREEN_H) {
      const fade = Math.min(1.0, life / 10.0)
      const idx = iy * SCREEN_W + ix
      if (ix % 2 === 0) {
        setPxBlend(buf, idx, 220, 230, 255, fade)
      } else {
        setPxBlend(buf, idx, 255, 255, 255, fade)
      }
    }
  }
}

function renderConfetti(buf: Uint8ClampedArray, fs: FaceState): void {
  for (const [cx, cy, life, ci] of fs.fx.confetti_pixels) {
    const ix = cx | 0
    const iy = cy | 0
    const color = HOLIDAY_CONFETTI_COLORS[ci % HOLIDAY_CONFETTI_COLORS.length]
    const fade = Math.min(1.0, life / 8.0)
    for (let dx = 0; dx < 2; dx++) {
      for (let dy = 0; dy < 2; dy++) {
        const px = ix + dx
        const py = iy + dy
        if (px >= 0 && px < SCREEN_W && py >= 0 && py < SCREEN_H) {
          setPxBlend(buf, py * SCREEN_W + px, color[0], color[1], color[2], fade)
        }
      }
    }
  }
}

function renderRosyCheeks(buf: Uint8ClampedArray): void {
  const cheeks: [number, number][] = [
    [LEFT_EYE_CX + ROSY_CHEEK_X_OFFSET, LEFT_EYE_CY + ROSY_CHEEK_Y_OFFSET],
    [RIGHT_EYE_CX - ROSY_CHEEK_X_OFFSET, LEFT_EYE_CY + ROSY_CHEEK_Y_OFFSET],
  ]
  for (const [ccx, ccy] of cheeks) {
    const x0 = Math.max(0, (ccx - ROSY_CHEEK_R - 2) | 0)
    const x1 = Math.min(SCREEN_W, (ccx + ROSY_CHEEK_R + 2) | 0)
    const y0 = Math.max(0, (ccy - ROSY_CHEEK_R - 2) | 0)
    const y1 = Math.min(SCREEN_H, (ccy + ROSY_CHEEK_R + 2) | 0)
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const d = sdCircle(x + 0.5, y + 0.5, ccx, ccy, ROSY_CHEEK_R)
        const a = sdfAlpha(d, 2.0) * ROSY_CHEEK_ALPHA
        if (a > 0.01) {
          setPxBlend(
            buf,
            y * SCREEN_W + x,
            ROSY_CHEEK_COLOR[0],
            ROSY_CHEEK_COLOR[1],
            ROSY_CHEEK_COLOR[2],
            a,
          )
        }
      }
    }
  }
}

// ── Main render entry point ────────────────────────────────────

export function renderFace(
  fs: FaceState,
  imageData: ImageData,
  borderRenderFn?: (buf: Uint8ClampedArray) => void,
  borderButtonsFn?: (buf: Uint8ClampedArray) => void,
): void {
  const buf = imageData.data

  // Clear to black (ImageData is RGBA)
  buf.fill(0)
  // Set alpha channel to 255 for all pixels
  for (let i = 3; i < buf.length; i += 4) {
    buf[i] = 255
  }

  // System mode: drive face state
  const mode = fs.system.mode
  fs.mood_color_override = null
  if (mode !== SystemMode.NONE) {
    if (mode === SystemMode.BOOTING) sysBooting(fs)
    else if (mode === SystemMode.ERROR_DISPLAY) sysError(fs)
    else if (mode === SystemMode.LOW_BATTERY) sysBattery(fs)
    else if (mode === SystemMode.UPDATING) sysUpdating(fs)
    else if (mode === SystemMode.SHUTTING_DOWN) sysShutdown(fs)
  }

  // Border background layer (behind eyes) — suppress during system modes
  const showBorder = mode === SystemMode.NONE
  if (showBorder && borderRenderFn) {
    borderRenderFn(buf)
  }

  // Eyes + mouth
  renderEye(buf, fs, true)
  renderEye(buf, fs, false)
  renderMouth(buf, fs)

  // Post-processing effects
  if (fs.fx.afterglow) {
    applyAfterglow(buf, fs)
  }
  if (fs.anim.rage) {
    renderFire(buf, fs)
  }
  renderSparkles(buf, fs)

  // Holiday overlays
  if (fs.holiday_mode === HolidayMode.CHRISTMAS) {
    renderSnow(buf, fs)
    renderRosyCheeks(buf)
  } else if (fs.holiday_mode === HolidayMode.NEW_YEAR) {
    renderConfetti(buf, fs)
  }

  // System mode icon overlays (drawn on top of face)
  if (mode === SystemMode.ERROR_DISPLAY) {
    sysErrorIcon(buf)
  } else if (mode === SystemMode.LOW_BATTERY) {
    sysBatteryIcon(buf, clamp(fs.system.param, 0.0, 1.0))
  } else if (mode === SystemMode.UPDATING) {
    sysUpdatingBar(buf, clamp(fs.system.param, 0.0, 1.0))
  }

  // Corner buttons — suppress during system modes
  if (showBorder && borderButtonsFn) {
    borderButtonsFn(buf)
  }

  // Store frame for afterglow
  if (fs.fx.afterglow) {
    if (!fs.fx.afterglow_buf || fs.fx.afterglow_buf.length !== buf.length) {
      fs.fx.afterglow_buf = new Uint8ClampedArray(buf.length)
    }
    fs.fx.afterglow_buf.set(buf)
  }
}
