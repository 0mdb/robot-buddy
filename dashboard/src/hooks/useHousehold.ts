import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

// Household roster (SIM-INTERACTION I3, stage 3). Stored on the robot, opt-in; see
// supervisor/personality/roster.py. Names go to Buddy's own LAN server, never outside.

export type MemberKind = 'kid' | 'adult' | 'animal'

export interface HouseholdMember {
  id: string
  name: string
  kind: MemberKind
  age?: number
  species?: string // pets only: "cat", "dog", ...
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
    onSuccess: (data) => {
      qc.setQueryData(KEY, data)
      // Removing a member (or everyone) also removes their face prints.
      qc.invalidateQueries({ queryKey: ['household', 'faces'] })
    },
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

// -- Face prints (supervisor/inputs/face_id.py) --------------------------------------
// Stored on the robot by member id; removed with the member or "Forget everyone".

const FACES_KEY = ['household', 'faces']

export interface FaceSamples {
  samples: Record<string, number> // member id -> stored samples
}

export interface EnrollResult {
  ok: boolean
  samples?: number
  error?: string
  reason?: string
}

export function useHouseholdFaces() {
  return useQuery<FaceSamples>({
    queryKey: FACES_KEY,
    queryFn: async () => {
      const res = await fetch('/api/household/faces')
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.reason ?? `${res.status}`)
      return { samples: body?.samples ?? {} }
    },
  })
}

/** Capture a member's face: the robot collects samples while they stand alone in front of
 * the camera. Resolves with the result (the server waits up to ~25 s). */
export function useEnrollFace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string): Promise<EnrollResult> => {
      const res = await fetch(`/api/household/members/${encodeURIComponent(id)}/face`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ samples: 8 }),
      })
      const body = (await res.json().catch(() => ({}))) as EnrollResult
      if (!res.ok || !body.ok) throw new Error(body.error || body.reason || `${res.status}`)
      return body
    },
    onSettled: () => qc.invalidateQueries({ queryKey: FACES_KEY }),
  })
}

export function useForgetFace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await fetch(`/api/household/members/${encodeURIComponent(id)}/face`, { method: 'DELETE' })
    },
    // The vision worker applies the forget on its next pass; refetch shortly after.
    onSettled: () => setTimeout(() => qc.invalidateQueries({ queryKey: FACES_KEY }), 500),
  })
}
