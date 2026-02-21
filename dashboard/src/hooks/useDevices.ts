import { useQuery } from '@tanstack/react-query'
import type { DeviceDebug } from '../types'

export function useDevices() {
  return useQuery<DeviceDebug>({
    queryKey: ['debug-devices'],
    queryFn: async () => {
      const res = await fetch('/debug/devices')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 2000,
    refetchOnWindowFocus: true,
  })
}
