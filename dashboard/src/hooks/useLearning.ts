import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

// Learning-game progress per child (docs/learning-games.md §2, §2.1). Robot-local; see
// supervisor/personality/learning.py. Answers are checked by code on Buddy's server.

export type Grade = 'K' | 'G1' | 'G2' | 'G3'

export interface LearningGame {
  day: string
  step: Grade
  right: number
  of: number
}

export interface LearningSkill {
  skill: string
  step: Grade
  mastered: Grade[]
  confident: boolean
  games: LearningGame[]
  trend: number | null
  code_share: number | null
  missed_most: string[]
}

export interface LearningChild {
  member_id: string
  name: string
  age?: number
  base: Grade
  ceiling: Grade
  ceiling_is_default: boolean
  skills: LearningSkill[]
}

export interface Learning {
  enabled: boolean
  grades: { id: Grade; name: string }[]
  children: LearningChild[]
}

const KEY = ['learning']

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.error ?? `${res.status}`)
  return body as T
}

export function useLearning() {
  return useQuery<Learning>({
    queryKey: KEY,
    queryFn: () => call<Learning>('/api/learning'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
}

function useChildMutation<T>(fn: (arg: T) => Promise<LearningChild>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetCeiling() {
  return useChildMutation(({ id, ceiling }: { id: string; ceiling: Grade | null }) =>
    call<LearningChild>(`/api/learning/${encodeURIComponent(id)}/ceiling`, {
      method: 'PUT',
      body: JSON.stringify({ ceiling }),
    }),
  )
}

export function useResetLearning() {
  return useChildMutation((id: string) =>
    call<LearningChild>(`/api/learning/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  )
}
