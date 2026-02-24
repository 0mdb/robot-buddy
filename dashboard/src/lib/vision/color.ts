export interface OpenCvHsv {
  h: number // 0..179
  s: number // 0..255
  v: number // 0..255
}

function clampInt(n: number, min: number, max: number): number {
  const x = Number.isFinite(n) ? Math.round(n) : min
  if (x < min) return min
  if (x > max) return max
  return x
}

function posMod(n: number, mod: number): number {
  return ((n % mod) + mod) % mod
}

/**
 * Convert sRGB (0..255 per channel) to OpenCV HSV.
 * OpenCV uses H in [0,179] (degrees/2), S/V in [0,255].
 */
export function rgbToOpenCvHsv(r: number, g: number, b: number): OpenCvHsv {
  const rn = clampInt(r, 0, 255) / 255
  const gn = clampInt(g, 0, 255) / 255
  const bn = clampInt(b, 0, 255) / 255

  const cMax = Math.max(rn, gn, bn)
  const cMin = Math.min(rn, gn, bn)
  const delta = cMax - cMin

  let hDeg = 0
  if (delta !== 0) {
    if (cMax === rn) {
      hDeg = 60 * posMod((gn - bn) / delta, 6)
    } else if (cMax === gn) {
      hDeg = 60 * ((bn - rn) / delta + 2)
    } else {
      hDeg = 60 * ((rn - gn) / delta + 4)
    }
  }

  const s = cMax === 0 ? 0 : delta / cMax
  const v = cMax

  return {
    h: clampInt(hDeg / 2, 0, 179),
    s: clampInt(s * 255, 0, 255),
    v: clampInt(v * 255, 0, 255),
  }
}

/**
 * Compute an OpenCV hue range (0..179) around a center hue with wrap-around.
 * If the range crosses the boundary, returns low > high to represent wrap-around.
 */
export function hueRangeWithWrap(centerH: number, deltaH: number): { low: number; high: number } {
  const H_MAX = 179
  const H_RANGE = 180
  const c = clampInt(centerH, 0, H_MAX)
  const d = clampInt(deltaH, 0, H_MAX)

  let low = c - d
  let high = c + d

  if (low < 0 || high > H_MAX) {
    low = posMod(low, H_RANGE)
    high = posMod(high, H_RANGE)
  } else {
    low = clampInt(low, 0, H_MAX)
    high = clampInt(high, 0, H_MAX)
  }

  return { low, high }
}

export function hsvRangeFromSample(
  sample: OpenCvHsv,
  deltas: { dh: number; ds: number; dv: number },
): {
  hLow: number
  hHigh: number
  sLow: number
  sHigh: number
  vLow: number
  vHigh: number
} {
  const { low: hLow, high: hHigh } = hueRangeWithWrap(sample.h, deltas.dh)
  const sLow = clampInt(sample.s - deltas.ds, 0, 255)
  const sHigh = clampInt(sample.s + deltas.ds, 0, 255)
  const vLow = clampInt(sample.v - deltas.dv, 0, 255)
  const vHigh = clampInt(sample.v + deltas.dv, 0, 255)

  return { hLow, hHigh, sLow, sHigh, vLow, vHigh }
}
