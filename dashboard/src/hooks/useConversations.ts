import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

// Opt-in conversation history (supervisor/core/conversation_history.py): kept on the
// robot only, for a parent to review and tune Buddy. Off by default.

export interface HistoryEntry {
  t: number // unix seconds
  role: 'child' | 'buddy' | 'typed' | 'timing' | 'voice'
  text?: string
  source?: string // buddy lines: conversation, greeter, planner, speech_policy, ...
  session?: string
  who?: string[] // who the camera recognised when the child spoke
  emotion?: string
  stt_ms?: number
  reply_ms?: number // end of the child's speech to Buddy's first sound
  late_resumes?: number
  // role 'voice': the server's voice ID guess for the turn just heard (names, robot-side)
  voice?: string // the name, or 'unsure'
  best?: string
  score?: number
  runner?: string
  runner_score?: number
  conversation?: string // the match over the whole conversation so far
  speech_s?: number
  learned?: boolean // this turn was added to the person's voiceprints
}

export interface ConversationHistory {
  enabled: boolean
  days: number
  entries: HistoryEntry[]
}

const KEY = ['conversations']

export function useConversations() {
  return useQuery<ConversationHistory>({
    queryKey: KEY,
    queryFn: async () => {
      const res = await fetch('/api/conversations')
      if (!res.ok) throw new Error(`${res.status}`)
      return res.json()
    },
    refetchInterval: 10_000,
  })
}

/** Turn the history on/off or change how many days it keeps (robot params, saved). */
export function useHistorySettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (items: Record<string, number | boolean>) => {
      const res = await fetch('/params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useClearConversations() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/conversations', { method: 'DELETE' })
      if (!res.ok) throw new Error(`${res.status}`)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

/** Entries grouped into visits: a new group on a new session or after 2 quiet minutes.
 * Newest visit first; entries within a visit in order. */
export function groupVisits(entries: HistoryEntry[]): HistoryEntry[][] {
  const visits: HistoryEntry[][] = []
  let cur: HistoryEntry[] = []
  let lastT = Number.NEGATIVE_INFINITY
  let lastSession: string | undefined
  for (const e of entries) {
    const newSession = e.session && lastSession && e.session !== lastSession
    if (cur.length && (e.t - lastT > 120 || newSession)) {
      visits.push(cur)
      cur = []
    }
    cur.push(e)
    lastT = e.t
    if (e.session) lastSession = e.session
  }
  if (cur.length) visits.push(cur)
  return visits.reverse()
}
