import { create } from 'zustand'
import type { LogEntry } from '../types'

const MAX_LOG_ENTRIES = 5000
const BACKOFF_BASE = 500
const BACKOFF_MAX = 8000

interface LogStore {
  entries: LogEntry[]
  version: number
  connected: boolean
  push: (entry: LogEntry) => void
  setConnected: (connected: boolean) => void
  clear: () => void
}

export const useLogStore = create<LogStore>()((set, get) => ({
  entries: [],
  version: 0,
  connected: false,

  push: (entry: LogEntry) => {
    const state = get()
    const entries =
      state.entries.length >= MAX_LOG_ENTRIES
        ? [...state.entries.slice(state.entries.length - MAX_LOG_ENTRIES + 1), entry]
        : [...state.entries, entry]
    set({ entries, version: state.version + 1 })
  },

  setConnected: (connected: boolean) => set({ connected }),

  clear: () => set({ entries: [], version: 0 }),
}))

class WsLogsManager {
  private ws: WebSocket | null = null
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  connect(): void {
    if (this.disposed) return
    this.cleanup()

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws/logs`

    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.attempt = 0
      useLogStore.getState().setConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data as string) as LogEntry
        if (entry.ts && entry.level && entry.msg) {
          useLogStore.getState().push(entry)
        }
      } catch {
        // Ignore malformed
      }
    }

    ws.onclose = () => {
      useLogStore.getState().setConnected(false)
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

export const wsLogsManager = new WsLogsManager()
