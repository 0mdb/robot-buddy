import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

// Household roster (SIM-INTERACTION I3, stage 3). Robot-local and opt-in; see
// supervisor/personality/roster.py. Nothing here leaves the robot.

export type MemberKind = 'kid' | 'adult' | 'animal'

export interface HouseholdMember {
  id: string
  name: string
  kind: MemberKind
  age?: number
}

export interface Household {
  enabled: boolean
  members: HouseholdMember[]
}

const KEY = ['household']

async function call(url: string, init?: RequestInit): Promise<Household> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.reason ?? `${res.status}`)
  return body as Household
}

export function useHousehold() {
  return useQuery<Household>({
    queryKey: KEY,
    queryFn: () => call('/api/household'),
    refetchOnWindowFocus: true,
  })
}

function useRosterMutation<T>(fn: (arg: T) => Promise<Household>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => qc.setQueryData(KEY, data),
  })
}

export function useSetHouseholdEnabled() {
  return useRosterMutation((enabled: boolean) =>
    call('/api/household/enabled', { method: 'PUT', body: JSON.stringify({ enabled }) }),
  )
}

export function useAddMember() {
  return useRosterMutation((m: Omit<HouseholdMember, 'id'>) =>
    call('/api/household/members', { method: 'POST', body: JSON.stringify(m) }),
  )
}

export function useRemoveMember() {
  return useRosterMutation((id: string) =>
    call(`/api/household/members/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  )
}

export function useForgetEveryone() {
  return useRosterMutation((_: undefined) => call('/api/household', { method: 'DELETE' }))
}
