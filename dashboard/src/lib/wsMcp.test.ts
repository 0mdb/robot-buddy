// @vitest-environment node

import { beforeEach, describe, expect, it } from 'vitest'
import type { McpAuditEntry } from '../types'
import { handleMcpMessage, useMcpStore } from './wsMcp'

function makeEntry(over: Partial<McpAuditEntry> = {}): McpAuditEntry {
  return {
    ts_mono: 1.0,
    tool: 'get_state',
    args: {},
    ok: true,
    latency_ms: 2.5,
    result_summary: 'mode=IDLE',
    error: '',
    client: '',
    ...over,
  }
}

describe('handleMcpMessage', () => {
  beforeEach(() => {
    useMcpStore.getState().clear()
  })

  it('replaces entries when a snapshot frame arrives', () => {
    // Seed a stray entry so replace() truly overrides.
    useMcpStore.getState().push(makeEntry({ tool: 'stale' }))
    expect(useMcpStore.getState().entries).toHaveLength(1)

    const snapshot = {
      type: 'snapshot',
      entries: [makeEntry({ ts_mono: 10 }), makeEntry({ ts_mono: 11, tool: 'get_memory' })],
    }
    handleMcpMessage(JSON.stringify(snapshot))

    const entries = useMcpStore.getState().entries
    expect(entries).toHaveLength(2)
    expect(entries[0].ts_mono).toBe(10)
    expect(entries[1].tool).toBe('get_memory')
    expect(entries.some((e) => e.tool === 'stale')).toBe(false)
  })

  it('pushes individual entries from live frames', () => {
    handleMcpMessage(JSON.stringify(makeEntry({ tool: 'a' })))
    handleMcpMessage(JSON.stringify(makeEntry({ tool: 'b' })))
    const entries = useMcpStore.getState().entries
    expect(entries.map((e) => e.tool)).toEqual(['a', 'b'])
  })

  it('drops malformed JSON silently', () => {
    handleMcpMessage('not json')
    handleMcpMessage('{"ts_mono": "not a number"}')
    expect(useMcpStore.getState().entries).toHaveLength(0)
  })

  it('caps the ring buffer on push', () => {
    const state = useMcpStore.getState()
    // Prime with 5000 entries.
    for (let i = 0; i < 5000; i++) {
      state.push(makeEntry({ ts_mono: i }))
    }
    expect(useMcpStore.getState().entries).toHaveLength(5000)

    state.push(makeEntry({ ts_mono: 9999, tool: 'newest' }))
    const entries = useMcpStore.getState().entries
    expect(entries).toHaveLength(5000)
    expect(entries[entries.length - 1].ts_mono).toBe(9999)
    // The oldest entry (ts_mono=0) must have been evicted.
    expect(entries[0].ts_mono).toBe(1)
  })

  it('caps the ring buffer on replace', () => {
    const big = Array.from({ length: 6000 }, (_, i) => makeEntry({ ts_mono: i }))
    handleMcpMessage(JSON.stringify({ type: 'snapshot', entries: big }))
    const entries = useMcpStore.getState().entries
    expect(entries).toHaveLength(5000)
    // Should retain the newest 5000.
    expect(entries[0].ts_mono).toBe(1000)
    expect(entries[entries.length - 1].ts_mono).toBe(5999)
  })

  it('snapshot with mixed valid/invalid entries keeps only valid', () => {
    const snapshot = {
      type: 'snapshot',
      entries: [
        makeEntry({ tool: 'keep1' }),
        { tool: 'missing_required_fields' },
        makeEntry({ tool: 'keep2' }),
      ],
    }
    handleMcpMessage(JSON.stringify(snapshot))
    const entries = useMcpStore.getState().entries
    expect(entries.map((e) => e.tool)).toEqual(['keep1', 'keep2'])
  })
})
