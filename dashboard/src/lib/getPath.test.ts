import { describe, expect, it } from 'vitest'
import { getPath } from './getPath'

describe('getPath', () => {
  it('reads top-level fields', () => {
    expect(getPath({ a: 1 }, 'a')).toBe(1)
  })

  it('walks nested paths', () => {
    expect(getPath({ power: { voltage_mv: 7400 } }, 'power.voltage_mv')).toBe(7400)
  })

  it('returns undefined for missing segments', () => {
    expect(getPath({ power: {} }, 'power.voltage_mv')).toBeUndefined()
    expect(getPath({}, 'power.voltage_mv')).toBeUndefined()
  })

  it('returns undefined for non-object intermediates', () => {
    expect(getPath({ power: 7400 }, 'power.voltage_mv')).toBeUndefined()
  })

  it('returns undefined for null / undefined input', () => {
    expect(getPath(null, 'power.voltage_mv')).toBeUndefined()
    expect(getPath(undefined, 'power.voltage_mv')).toBeUndefined()
  })
})
