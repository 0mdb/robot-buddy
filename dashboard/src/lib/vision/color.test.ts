// @vitest-environment node

import { describe, expect, it } from 'vitest'
import { hsvRangeFromSample, hueRangeWithWrap, rgbToOpenCvHsv } from './color'

describe('rgbToOpenCvHsv', () => {
  it('converts primary colors', () => {
    expect(rgbToOpenCvHsv(255, 0, 0)).toEqual({ h: 0, s: 255, v: 255 })
    expect(rgbToOpenCvHsv(0, 255, 0)).toEqual({ h: 60, s: 255, v: 255 })
    expect(rgbToOpenCvHsv(0, 0, 255)).toEqual({ h: 120, s: 255, v: 255 })
  })

  it('handles grayscale', () => {
    expect(rgbToOpenCvHsv(255, 255, 255)).toEqual({ h: 0, s: 0, v: 255 })
    expect(rgbToOpenCvHsv(0, 0, 0)).toEqual({ h: 0, s: 0, v: 0 })
  })
})

describe('hueRangeWithWrap', () => {
  it('returns a normal (non-wrapped) range when within bounds', () => {
    expect(hueRangeWithWrap(10, 5)).toEqual({ low: 5, high: 15 })
  })

  it('represents wrap-around with low > high', () => {
    expect(hueRangeWithWrap(175, 10)).toEqual({ low: 165, high: 5 })
    expect(hueRangeWithWrap(0, 10)).toEqual({ low: 170, high: 10 })
  })
})

describe('hsvRangeFromSample', () => {
  it('clamps S/V bounds to 0..255', () => {
    const r = hsvRangeFromSample({ h: 0, s: 5, v: 5 }, { dh: 0, ds: 40, dv: 40 })
    expect(r.sLow).toBe(0)
    expect(r.vLow).toBe(0)
    expect(r.sHigh).toBe(45)
    expect(r.vHigh).toBe(45)
  })
})
