import { useQuery } from '@tanstack/react-query'
import type { McpDebugSnapshot } from '../types'

export function useMcpDebug() {
  return useQuery<McpDebugSnapshot>({
    queryKey: ['debug-mcp'],
    queryFn: async () => {
      const res = await fetch('/debug/mcp')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
  })
}
