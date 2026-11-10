import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

// Quiet alerts for parents: a child asked Buddy to keep a secret, or disclosed a stranger,
// unwanted touching, being hurt, or being bullied. Robot-local; see
// supervisor/personality/parent_alerts.py.

export interface ParentAlert {
  id: string
  ts: number
  categories: string[]
  summary: string
  child_text: string
  buddy_reply: string
  reviewed: boolean
}

export interface ParentAlerts {
  enabled: boolean
  push: boolean
  unreviewed: number
  alerts: ParentAlert[]
}

const KEY = ['parent-alerts']

async function call(url: string, init?: RequestInit): Promise<ParentAlerts> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.reason ?? `${res.status}`)
  return body as ParentAlerts
}

export function useParentAlerts() {
  return useQuery<ParentAlerts>({
    queryKey: KEY,
    queryFn: () => call('/api/parent-alerts'),
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
  })
}

function useAlertMutation<T>(fn: (arg: T) => Promise<ParentAlerts>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: (data) => qc.setQueryData(KEY, data) })
}

export const useMarkReviewed = () =>
  useAlertMutation(({ id, reviewed }: { id: string; reviewed: boolean }) =>
    call(`/api/parent-alerts/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ reviewed }),
    }),
  )

export const useDeleteAlert = () =>
  useAlertMutation((id: string) =>
    call(`/api/parent-alerts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  )

export const useClearAlerts = () =>
  useAlertMutation((_: undefined) => call('/api/parent-alerts', { method: 'DELETE' }))

export const useSetAlertsEnabled = () =>
  useAlertMutation((enabled: boolean) =>
    call('/api/parent-alerts/enabled', { method: 'PUT', body: JSON.stringify({ enabled }) }),
  )
