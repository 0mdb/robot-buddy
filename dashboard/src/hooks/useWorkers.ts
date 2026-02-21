import { useQuery } from '@tanstack/react-query'
import type { WorkersDebug } from '../types'

export function useWorkers() {
  return useQuery<WorkersDebug>({
    queryKey: ['debug-workers'],
    queryFn: async () => {
      const res = await fetch('/debug/workers')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
  })
}
