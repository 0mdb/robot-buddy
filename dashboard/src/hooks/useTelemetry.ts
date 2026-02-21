import { useCallback, useRef, useSyncExternalStore } from 'react'
import { type TelemetryState, useTelemetryStore } from '../stores/telemetryStore'

/**
 * Throttled telemetry selector.
 * Subscribes to the store but only triggers a React re-render at most every `throttleMs`.
 * This prevents 20 Hz WS updates from causing 20 Hz React renders.
 */
export function useTelemetry<T>(selector: (state: TelemetryState) => T, throttleMs = 100): T {
  const lastRenderRef = useRef(0)
  const cachedRef = useRef<T>(selector(useTelemetryStore.getState()))
  const versionRef = useRef(0)

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      return useTelemetryStore.subscribe((state) => {
        const now = performance.now()
        if (now - lastRenderRef.current < throttleMs) return
        const next = selector(state)
        if (next !== cachedRef.current || state.version !== versionRef.current) {
          cachedRef.current = next
          versionRef.current = state.version
          lastRenderRef.current = now
          onStoreChange()
        }
      })
    },
    [selector, throttleMs],
  )

  const getSnapshot = useCallback(() => cachedRef.current, [])

  return useSyncExternalStore(subscribe, getSnapshot)
}

/**
 * Direct snapshot access (no throttle) — for components that need immediate values.
 */
export function useSnapshot(): Record<string, unknown> {
  return useTelemetryStore((s) => s.snapshot)
}

/**
 * Get the current version (for forcing re-renders on any telemetry update).
 */
export function useTelemetryVersion(): number {
  return useTelemetryStore((s) => s.version)
}
