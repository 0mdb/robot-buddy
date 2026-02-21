import { useTelemetryStore } from '../stores/telemetryStore'
import type { WsEnvelope } from '../types'

const BACKOFF_BASE = 500
const BACKOFF_MAX = 8000

/**
 * WebSocket manager with exponential backoff reconnect.
 * Writes exclusively to TelemetryStore — no DOM touching.
 */
class WsManager {
  private ws: WebSocket | null = null
  private attempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false
  private receivedFirstMessage = false

  connect(): void {
    if (this.disposed) return
    this.cleanup()

    const store = useTelemetryStore.getState()
    store.setWsState('connecting')
    store.resetSeqGaps()
    this.receivedFirstMessage = false

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws`

    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      // Don't set 'open' yet — wait for first valid message
      this.attempt = 0
    }

    ws.onmessage = (event) => {
      try {
        const envelope = JSON.parse(event.data as string) as WsEnvelope
        if (envelope.type !== 'telemetry' || !envelope.payload) return

        if (!this.receivedFirstMessage) {
          this.receivedFirstMessage = true
          useTelemetryStore.getState().setWsState('open')
        }

        useTelemetryStore
          .getState()
          .push(envelope.payload as unknown as Record<string, unknown>, envelope.ts_ms)
      } catch {
        // Malformed message — ignore
      }
    }

    ws.onclose = () => {
      useTelemetryStore.getState().setWsState('closed')
      this.scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose will fire after this
    }
  }

  /** Send a command message over the WebSocket. */
  send(msg: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
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
    useTelemetryStore.getState().incrementReconnects()

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }
}

// Singleton
export const wsManager = new WsManager()
