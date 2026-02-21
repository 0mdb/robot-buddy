import { create } from 'zustand'
import { RING_METRICS } from '../constants'
import { RingBuffer } from '../lib/ringBuffer'

const RING_CAPACITY = 1200 // 60s @ 20Hz

export interface WsMeta {
  lastRxMs: number
  lastSeq: number
  seqGaps: number
  reconnectCount: number
  wsState: 'connecting' | 'open' | 'closed'
}

export interface TelemetryState {
  snapshot: Record<string, unknown>
  rings: Map<string, RingBuffer>
  meta: WsMeta
  version: number // bumped on every push

  // Actions
  push: (payload: Record<string, unknown>, serverSeq?: number) => void
  ring: (metric: string) => RingBuffer
  setWsState: (state: WsMeta['wsState']) => void
  incrementReconnects: () => void
  resetSeqGaps: () => void
}

export const useTelemetryStore = create<TelemetryState>()((set, get) => {
  // Pre-allocate ring buffers for known metrics
  const rings = new Map<string, RingBuffer>()
  for (const m of RING_METRICS) {
    rings.set(m, new RingBuffer(RING_CAPACITY))
  }

  return {
    snapshot: {},
    rings,
    meta: {
      lastRxMs: 0,
      lastSeq: -1,
      seqGaps: 0,
      reconnectCount: 0,
      wsState: 'closed' as const,
    },
    version: 0,

    push: (payload: Record<string, unknown>, serverSeq?: number) => {
      const state = get()
      const now = performance.now()
      const ts = (payload.tick_mono_ms as number) ?? now

      // Push numeric fields into ring buffers
      for (const metric of RING_METRICS) {
        const v = payload[metric]
        if (typeof v === 'number') {
          state.ring(metric).push(v, ts)
        }
      }

      // Track sequence gaps
      let gaps = state.meta.seqGaps
      const lastSeq = state.meta.lastSeq
      if (serverSeq !== undefined && lastSeq >= 0 && serverSeq !== lastSeq + 1) {
        gaps += 1
      }

      set({
        snapshot: payload,
        version: state.version + 1,
        meta: {
          ...state.meta,
          lastRxMs: now,
          lastSeq: serverSeq ?? state.meta.lastSeq,
          seqGaps: gaps,
        },
      })
    },

    ring: (metric: string): RingBuffer => {
      const state = get()
      let r = state.rings.get(metric)
      if (!r) {
        r = new RingBuffer(RING_CAPACITY)
        state.rings.set(metric, r)
      }
      return r
    },

    setWsState: (wsState: WsMeta['wsState']) => {
      set((s) => ({ meta: { ...s.meta, wsState } }))
    },

    incrementReconnects: () => {
      set((s) => ({ meta: { ...s.meta, reconnectCount: s.meta.reconnectCount + 1 } }))
    },

    resetSeqGaps: () => {
      set((s) => ({ meta: { ...s.meta, seqGaps: 0, lastSeq: -1 } }))
    },
  }
})
