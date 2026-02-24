import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export interface MemoryEntry {
  tag: string
  category: string
  valence_bias: number
  arousal_bias: number
  initial_strength: number
  created_ts: number
  last_reinforced_ts: number
  reinforcement_count: number
  decay_lambda: number
  source: string
  current_strength: number
}

export interface MemoryData {
  version: number
  entries: MemoryEntry[]
  entry_count: number
  consent: boolean
  session_count?: number
  total_conversation_s?: number
  created_ts?: number
}

export function useMemory() {
  return useQuery<MemoryData>({
    queryKey: ['personality-memory'],
    queryFn: async () => {
      const res = await fetch('/api/personality/memory')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 10000,
    refetchOnWindowFocus: true,
  })
}

export function useResetMemory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/personality/memory', { method: 'DELETE' })
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['personality-memory'] })
    },
  })
}
