import { useEffect, useRef, useState } from 'react'
import { useTelemetryStore, type WsMeta } from '../stores/telemetryStore'

interface WsHealth extends WsMeta {
  telemetryAgeMs: number
}

/**
 * WS health indicators, refreshed at 10 Hz.
 * Handles Page Visibility API to prevent false stale warnings
 * when the browser tab is backgrounded.
 */
export function useWsMeta(): WsHealth {
  const [health, setHealth] = useState<WsHealth>(() => ({
    ...useTelemetryStore.getState().meta,
    telemetryAgeMs: 0,
  }))

  const hiddenSinceRef = useRef<number | null>(null)

  useEffect(() => {
    const onVisChange = () => {
      if (document.hidden) {
        hiddenSinceRef.current = performance.now()
      } else {
        hiddenSinceRef.current = null
      }
    }
    document.addEventListener('visibilitychange', onVisChange)

    const interval = setInterval(() => {
      const meta = useTelemetryStore.getState().meta
      const now = performance.now()

      let age = 0
      if (meta.lastRxMs > 0) {
        age = now - meta.lastRxMs
        // If tab was hidden, don't count hidden time as staleness
        if (hiddenSinceRef.current !== null) {
          age = Math.max(0, age - (now - hiddenSinceRef.current))
        }
      }

      setHealth({
        ...meta,
        telemetryAgeMs: age,
      })
    }, 100) // 10 Hz

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisChange)
    }
  }, [])

  return health
}
