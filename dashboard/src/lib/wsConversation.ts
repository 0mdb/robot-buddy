import { create } from 'zustand'

const MAX_EVENTS = 2000
const BACKOFF_BASE = 500
const BACKOFF_MAX = 8000

export interface ConversationEvent {
  ts_mono_ms: number
  type: string
  [key: string]: unknown
}

interface ConversationStore {
  events: ConversationEvent[]
  version: number
  connected: boolean
  paused: boolean
  push: (event: ConversationEvent) => void
  setConnected: (connected: boolean) => void
  setPaused: (paused: boolean) => void
  clear: () => void
}

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  events: [],
  version: 0,
  connected: false,
  paused: false,

  push: (event: ConversationEvent) => {
    const state = get()
    if (state.paused) return
    const events =
      state.events.length >= MAX_EVENTS
        ? [...state.events.slice(state.events.length - MAX_EVENTS + 1), event]
        : [...state.events, event]
    set({ events, version: state.version + 1 })
  },

  setConnected: (connected: boolean) => set({ connected }),
  setPaused: (paused: boolean) => set({ paused }),
  clear: () => set({ events: [], version: 0 }),
}))

class WsConversationManager {
  private ws: WebSocket | null = null
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  connect(): void {
    this.disposed = false
    this.cleanup()

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws/conversation`

    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.attempt = 0
      useConversationStore.getState().setConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string) as ConversationEvent
        if (payload.ts_mono_ms !== undefined && payload.type) {
          useConversationStore.getState().push(payload)
        }
      } catch {
        // Ignore malformed
      }
    }

    ws.onclose = () => {
      useConversationStore.getState().setConnected(false)
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
    useConversationStore.getState().setConnected(false)
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

export const wsConversationManager = new WsConversationManager()
