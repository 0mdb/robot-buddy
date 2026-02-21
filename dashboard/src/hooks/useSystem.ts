import { useQuery } from '@tanstack/react-query'
import type { SystemDebug } from '../types'

export function useSystem() {
  return useQuery<SystemDebug>({
    queryKey: ['debug-system'],
    queryFn: async () => {
      const res = await fetch('/debug/system')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  })
}
