/**
 * SDF (Signed Distance Field) primitive library.
 *
 * All functions return float: negative = inside shape, positive = outside.
 * Ported from tools/face_sim_v3/render/sdf.py.
 */

import { SCREEN_H, SCREEN_W } from './constants'

export function sdRoundedBox(
  px: number,
  py: number,
  cx: number,
  cy: number,
  hw: number,
  hh: number,
  r: number,
): number {
  const dx = Math.abs(px - cx) - hw + r
  const dy = Math.abs(py - cy) - hh + r
  return (
    Math.min(Math.max(dx, dy), 0.0) + Math.sqrt(Math.max(dx, 0.0) ** 2 + Math.max(dy, 0.0) ** 2) - r
  )
}

export function sdCircle(px: number, py: number, cx: number, cy: number, r: number): number {
  return Math.sqrt((px - cx) ** 2 + (py - cy) ** 2) - r
}

export function sdHeart(px: number, py: number, cx: number, cy: number, size: number): number {
  const x = Math.abs(px - cx) / size
  const y = (cy - py) / size + 0.5

  let d: number
  if (y + x > 1.0) {
    const dx = x - 0.25
    const dy = y - 0.75
    d = Math.sqrt(dx * dx + dy * dy) - 0.35355339 // sqrt(2)/4
  } else {
    const dy1 = y - 1.0
    const d1 = x * x + dy1 * dy1
    const t = Math.max(x + y, 0.0) * 0.5
    const dx2 = x - t
    const dy2 = y - t
    const d2 = dx2 * dx2 + dy2 * dy2
    d = Math.sqrt(Math.min(d1, d2))
    if (x < y) d = -d
  }
  return d * size
}

export function sdCross(
  px: number,
  py: number,
  cx: number,
  cy: number,
  size: number,
  thick: number,
): number {
  const rx = (px - cx) * Math.SQRT1_2 - (py - cy) * Math.SQRT1_2
  const ry = (px - cx) * Math.SQRT1_2 + (py - cy) * Math.SQRT1_2
  const d1 = sdRoundedBox(rx, ry, 0, 0, thick, size, 1.0)
  const d2 = sdRoundedBox(rx, ry, 0, 0, size, thick, 1.0)
  return Math.min(d1, d2)
}

export function smoothstep(edge0: number, edge1: number, x: number): number {
  if (edge1 === edge0) return x < edge0 ? 0.0 : 1.0
  const t = Math.max(0.0, Math.min(1.0, (x - edge0) / (edge1 - edge0)))
  return t * t * (3.0 - 2.0 * t)
}

export function sdfAlpha(dist: number, aaWidth = 1.0): number {
  return 1.0 - smoothstep(-aaWidth / 2, aaWidth / 2, dist)
}

// ── Color utilities ─────────────────────────────────────────────

export function clampColor(r: number, g: number, b: number): [number, number, number] {
  return [
    Math.max(0, Math.min(255, r | 0)),
    Math.max(0, Math.min(255, g | 0)),
    Math.max(0, Math.min(255, b | 0)),
  ]
}

/**
 * Alpha-blend color onto pixel buffer (RGBA ImageData).
 * buf = Uint8ClampedArray from ImageData, idx = pixel index (not byte index).
 */
export function setPxBlend(
  buf: Uint8ClampedArray,
  idx: number,
  r: number,
  g: number,
  b: number,
  alpha: number,
): void {
  if (alpha <= 0.0 || idx < 0 || idx >= SCREEN_W * SCREEN_H) return
  const off = idx * 4
  if (alpha >= 1.0) {
    buf[off] = r
    buf[off + 1] = g
    buf[off + 2] = b
    // alpha channel stays 255
  } else {
    const inv = 1.0 - alpha
    buf[off] = (buf[off] * inv + r * alpha) | 0
    buf[off + 1] = (buf[off + 1] * inv + g * alpha) | 0
    buf[off + 2] = (buf[off + 2] * inv + b * alpha) | 0
  }
}
