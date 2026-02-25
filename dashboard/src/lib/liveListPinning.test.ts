// @vitest-environment node

import { describe, expect, it } from 'vitest'
import { countVisiblePrepends, isAtPinnedEdge } from './liveListPinning'

describe('isAtPinnedEdge', () => {
  it('uses top edge when newest-first', () => {
    expect(
      isAtPinnedEdge({
        scrollTop: 0,
        clientHeight: 200,
        scrollHeight: 800,
        rowHeight: 24,
        newestFirst: true,
      }),
    ).toBe(true)
    expect(
      isAtPinnedEdge({
        scrollTop: 40,
        clientHeight: 200,
        scrollHeight: 800,
        rowHeight: 24,
        newestFirst: true,
      }),
    ).toBe(false)
  })

  it('uses bottom edge when oldest-first', () => {
    expect(
      isAtPinnedEdge({
        scrollTop: 600,
        clientHeight: 200,
        scrollHeight: 800,
        rowHeight: 24,
        newestFirst: false,
      }),
    ).toBe(true)
    expect(
      isAtPinnedEdge({
        scrollTop: 500,
        clientHeight: 200,
        scrollHeight: 800,
        rowHeight: 24,
        newestFirst: false,
      }),
    ).toBe(false)
  })
})

describe('countVisiblePrepends', () => {
  it('returns zero when pinned or not newest-first', () => {
    const entries = [1, 2, 3]
    const matches = (n: number) => n > 0

    expect(
      countVisiblePrepends({
        pinned: true,
        newestFirst: true,
        versionDelta: 2,
        entries,
        matches,
      }),
    ).toBe(0)

    expect(
      countVisiblePrepends({
        pinned: false,
        newestFirst: false,
        versionDelta: 2,
        entries,
        matches,
      }),
    ).toBe(0)
  })

  it('counts only newly inserted visible entries in newest-first mode', () => {
    const entries = ['old-a', 'old-b', 'new-info', 'new-error']
    const matches = (s: string) => s.startsWith('new-')

    expect(
      countVisiblePrepends({
        pinned: false,
        newestFirst: true,
        versionDelta: 2,
        entries,
        matches,
      }),
    ).toBe(2)
  })

  it('handles filtered inserts and capped buffers', () => {
    const entries = ['new-debug', 'new-error']
    const matches = (s: string) => s.endsWith('error')

    expect(
      countVisiblePrepends({
        pinned: false,
        newestFirst: true,
        versionDelta: 5,
        entries,
        matches,
      }),
    ).toBe(1)
  })
})
