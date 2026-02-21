import { useQuery } from '@tanstack/react-query'
import type { ClocksDebug } from '../types'

export function useClocks() {
  return useQuery<ClocksDebug>({
    queryKey: ['debug-clocks'],
    queryFn: async () => {
      const res = await fetch('/debug/clocks')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
  })
}
