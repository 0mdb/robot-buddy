import { create } from 'zustand'

const MAX_PACKETS = 5000
const BACKOFF_BASE = 500
const BACKOFF_MAX = 8000

export interface CapturedPacket {
  ts_mono_ms: number
  direction: 'TX' | 'RX'
  device: 'reflex' | 'face'
  pkt_type: number
  type_name: string
  seq: number
  fields: Record<string, unknown>
  raw_hex: string
  size: number
}

interface ProtocolStore {
  packets: CapturedPacket[]
  version: number
  connected: boolean
  paused: boolean
  push: (packet: CapturedPacket) => void
  setConnected: (connected: boolean) => void
  setPaused: (paused: boolean) => void
  clear: () => void
}

export const useProtocolStore = create<ProtocolStore>()((set, get) => ({
  packets: [],
  version: 0,
  connected: false,
  paused: false,

  push: (packet: CapturedPacket) => {
    const state = get()
    if (state.paused) return
    const packets =
      state.packets.length >= MAX_PACKETS
        ? [...state.packets.slice(state.packets.length - MAX_PACKETS + 1), packet]
        : [...state.packets, packet]
    set({ packets, version: state.version + 1 })
  },

  setConnected: (connected: boolean) => set({ connected }),
  setPaused: (paused: boolean) => set({ paused }),
  clear: () => set({ packets: [], version: 0 }),
}))

class WsProtocolManager {
  private ws: WebSocket | null = null
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  connect(): void {
    if (this.disposed) return
    this.disposed = false
    this.cleanup()

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws/protocol`

    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.attempt = 0
      useProtocolStore.getState().setConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const packet = JSON.parse(event.data as string) as CapturedPacket
        if (packet.ts_mono_ms !== undefined && packet.type_name) {
          useProtocolStore.getState().push(packet)
        }
      } catch {
        // Ignore malformed
      }
    }

    ws.onclose = () => {
      useProtocolStore.getState().setConnected(false)
      this.scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose fires after
    }
  }

  dispose(): void {
    this.disposed = true
    this.cleanup()
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    useProtocolStore.getState().setConnected(false)
  }

  private cleanup(): void {
    if (this.ws) {
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onclose = null
      this.ws.onerror = null
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close()
      }
      this.ws = null
    }
  }

  private scheduleReconnect(): void {
    if (this.disposed) return
    const delay = Math.min(BACKOFF_BASE * 2 ** this.attempt, BACKOFF_MAX)
    this.attempt++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }
}

export const wsProtocolManager = new WsProtocolManager()
