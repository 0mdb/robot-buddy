import { create } from 'zustand'
import type { McpAuditEntry } from '../types'

const MAX_MCP_ENTRIES = 5000
const BACKOFF_BASE = 500
const BACKOFF_MAX = 8000

interface McpStore {
  entries: McpAuditEntry[]
  version: number
  connected: boolean
  push: (entry: McpAuditEntry) => void
  replace: (entries: McpAuditEntry[]) => void
  setConnected: (connected: boolean) => void
  clear: () => void
}

export const useMcpStore = create<McpStore>()((set, get) => ({
  entries: [],
  version: 0,
  connected: false,

  push: (entry: McpAuditEntry) => {
    const state = get()
    const entries =
      state.entries.length >= MAX_MCP_ENTRIES
        ? [...state.entries.slice(state.entries.length - MAX_MCP_ENTRIES + 1), entry]
        : [...state.entries, entry]
    set({ entries, version: state.version + 1 })
  },

  replace: (entries: McpAuditEntry[]) => {
    const capped =
      entries.length > MAX_MCP_ENTRIES ? entries.slice(entries.length - MAX_MCP_ENTRIES) : entries
    set({ entries: [...capped], version: get().version + 1 })
  },

  setConnected: (connected: boolean) => set({ connected }),

  clear: () => set({ entries: [], version: 0 }),
}))

// Shape guard for a live audit frame — mirror of the server's
// McpAuditEntry.to_dict() payload.
function isAuditEntry(v: unknown): v is McpAuditEntry {
  if (!v || typeof v !== 'object') return false
  const r = v as Record<string, unknown>
  return (
    typeof r.ts_mono === 'number' &&
    typeof r.tool === 'string' &&
    typeof r.ok === 'boolean' &&
    typeof r.latency_ms === 'number'
  )
}

// Exported for unit testing — handles both initial snapshot frame
// ({type: "snapshot", entries: [...]}) and per-entry live frames.
export function handleMcpMessage(raw: string, store = useMcpStore.getState()): void {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return
  }
  if (
    parsed &&
    typeof parsed === 'object' &&
    (parsed as Record<string, unknown>).type === 'snapshot'
  ) {
    const entries = (parsed as { entries?: unknown }).entries
    if (Array.isArray(entries)) {
      store.replace(entries.filter(isAuditEntry))
    }
    return
  }
  if (isAuditEntry(parsed)) {
    store.push(parsed)
  }
}

class WsMcpManager {
  private ws: WebSocket | null = null
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false

  connect(): void {
    if (this.disposed) return
    this.cleanup()

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws/mcp`

    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.attempt = 0
      useMcpStore.getState().setConnected(true)
    }

    ws.onmessage = (event) => {
      handleMcpMessage(event.data as string)
    }

    ws.onclose = () => {
      useMcpStore.getState().setConnected(false)
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

export const wsMcpManager = new WsMcpManager()
