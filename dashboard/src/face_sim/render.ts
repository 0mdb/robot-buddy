/**
 * Face renderer — eyes, mouth rendering into ImageData pixel buffer.
 *
 * Ported from tools/face_sim_v3/render/face.py.
 * Phase 1: eyes + mouth. System modes, border, effects deferred.
 */

import {
  EDGE_GLOW_FALLOFF,
  EYE_CORNER_R,
  EYE_HEIGHT,
  EYE_WIDTH,
  GAZE_EYE_SHIFT,
  GAZE_PUPIL_SHIFT,
  LEFT_EYE_CX,
  LEFT_EYE_CY,
  MOUTH_CX,
  MOUTH_CY,
  MOUTH_HALF_W,
  MOUTH_THICKNESS,
  PUPIL_COLOR,
  PUPIL_R,
  RIGHT_EYE_CX,
  RIGHT_EYE_CY,
  SCREEN_H,
  SCREEN_W,
} from './constants'
import { sdCircle, sdRoundedBox, setPxBlend, smoothstep } from './sdf'
import { getBreathScale, getEmotionColor } from './state'
import type { FaceState } from './types'

function clamp(x: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, x))
}

// ── Eye rendering ──────────────────────────────────────────────

function renderEye(buf: Uint8ClampedArray, fs: FaceState, isLeft: boolean): void {
  const eye = isLeft ? fs.eye_l : fs.eye_r
  const cxBase = isLeft ? LEFT_EYE_CX : RIGHT_EYE_CX
  const cyBase = isLeft ? LEFT_EYE_CY : RIGHT_EYE_CY
  const breath = getBreathScale(fs)
  const w = (EYE_WIDTH / 2.0) * eye.width_scale * breath
  const h = (EYE_HEIGHT / 2.0) * eye.height_scale * breath

  // Clamp pupil offset inside the eye
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
        const distPupil = sdCircle(px, py, pupilCx, pupilCy, PUPIL_R)
        const alphaPupil = (1.0 - smoothstep(-0.5, 0.5, distPupil)) * finalAlpha * lidVis
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

// ── Sparkle rendering (simple white dots) ──────────────────────

function renderSparkles(buf: Uint8ClampedArray, fs: FaceState): void {
  for (const [sx, sy, life] of fs.fx.sparkle_pixels) {
    if (sx >= 0 && sx < SCREEN_W && sy >= 0 && sy < SCREEN_H) {
      const idx = sy * SCREEN_W + sx
      setPxBlend(buf, idx, 255, 255, 255, Math.min(1.0, life / 5.0))
    }
  }
}

// ── Main render entry point ────────────────────────────────────

export function renderFace(fs: FaceState, imageData: ImageData): void {
  const buf = imageData.data

  // Clear to black (ImageData is RGBA)
  buf.fill(0)
  // Set alpha channel to 255 for all pixels
  for (let i = 3; i < buf.length; i += 4) {
    buf[i] = 255
  }

  // Eyes + mouth
  renderEye(buf, fs, true)
  renderEye(buf, fs, false)
  renderMouth(buf, fs)

  // Sparkles (simple effect included in Phase 1)
  renderSparkles(buf, fs)
}
