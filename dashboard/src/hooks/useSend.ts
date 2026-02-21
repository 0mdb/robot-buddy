import { useCallback } from 'react'
import { wsManager } from '../lib/wsManager'

/**
 * Returns a stable `send` function for WS commands.
 */
export function useSend() {
  return useCallback((msg: Record<string, unknown>) => {
    wsManager.send(msg)
  }, [])
}
