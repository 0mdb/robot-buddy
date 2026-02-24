import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { VisionMaskV1 } from '../types'

const QUERY_KEY = ['vision-mask']

export function useVisionMask() {
  return useQuery<VisionMaskV1>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const res = await fetch('/api/vision/mask')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchOnWindowFocus: true,
  })
}

export function useSaveVisionMask() {
  const qc = useQueryClient()
  return useMutation<VisionMaskV1, Error, VisionMaskV1>({
    mutationFn: async (mask) => {
      const res = await fetch('/api/vision/mask', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mask),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export function useResetVisionMask() {
  const qc = useQueryClient()
  return useMutation<{ ok: boolean; mask: VisionMaskV1 }, Error>({
    mutationFn: async () => {
      const res = await fetch('/api/vision/mask', { method: 'DELETE' })
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}
