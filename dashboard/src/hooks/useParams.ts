import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ParamDef, ParamUpdateResult } from '../types'

export function useParamsList() {
  return useQuery<ParamDef[]>({
    queryKey: ['params'],
    queryFn: async () => {
      const res = await fetch('/params')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchOnWindowFocus: true,
  })
}

export function useUpdateParams() {
  const queryClient = useQueryClient()

  return useMutation<Record<string, ParamUpdateResult>, Error, Record<string, number | boolean>>({
    mutationFn: async (items) => {
      const res = await fetch('/params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['params'] })
    },
  })
}
