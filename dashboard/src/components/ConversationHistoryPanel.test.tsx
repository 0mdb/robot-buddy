import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { ConversationHistory } from '../hooks/useConversations'
import { groupVisits } from '../hooks/useConversations'
import { ConversationHistoryPanel } from './ConversationHistoryPanel'

// Synthetic names and words only.
let state: ConversationHistory
let posts: unknown[]
let deletes: number

beforeEach(() => {
  posts = []
  deletes = 0
  state = { enabled: false, days: 3, entries: [] }
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (url === '/params' && method === 'POST') {
      const { items } = JSON.parse(String(init?.body))
      posts.push(items)
      if ('conversation.history_enabled' in items)
        state = { ...state, enabled: items['conversation.history_enabled'] }
      return Promise.resolve(new Response('{}'))
    }
    if (url === '/api/conversations' && method === 'DELETE') {
      deletes++
      state = { ...state, entries: [] }
    }
    return Promise.resolve(new Response(JSON.stringify(state)))
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ConversationHistoryPanel />
    </QueryClientProvider>,
  )
}

test('off by default; turning it on saves the setting', async () => {
  renderPanel()
  expect(await screen.findByText('History is off.')).toBeTruthy()
  fireEvent.click(screen.getByLabelText('Keep history'))
  await waitFor(() => expect(posts).toContainEqual({ 'conversation.history_enabled': true }))
  expect(await screen.findByText('Nothing yet.')).toBeTruthy()
})

test('a visit shows who spoke, the reply, its expression and timing', async () => {
  const t = 1_800_000_000
  state = {
    enabled: true,
    days: 3,
    entries: [
      { t, role: 'buddy', source: 'greeter', text: 'Hi, Test Kid!' },
      { t: t + 5, role: 'child', text: 'can we play', session: 's1', who: ['Test Kid'] },
      { t: t + 6, role: 'timing', reply_ms: 1400, late_resumes: 1 },
      {
        t: t + 7,
        role: 'buddy',
        source: 'conversation',
        text: 'Yes!',
        emotion: 'excited',
        session: 's1',
      },
    ],
  }
  renderPanel()
  expect(await screen.findByText('can we play')).toBeTruthy()
  expect(screen.getByText('Test Kid')).toBeTruthy()
  expect(screen.getByText('excited')).toBeTruthy()
  expect(screen.getByText(/replied after 1.4 s, kept listening 1×/)).toBeTruthy()
  expect(screen.getByText('greeting')).toBeTruthy()

  fireEvent.click(screen.getByLabelText(/Show Buddy's own lines/))
  expect(screen.queryByText('Hi, Test Kid!')).toBeNull()
  expect(screen.getByText('Yes!')).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: 'Clear all' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
  await waitFor(() => expect(deletes).toBe(1))
  expect(await screen.findByText('Nothing yet.')).toBeTruthy()
})

test('visits split on a new session or a 2-minute gap, newest first', () => {
  const v = groupVisits([
    { t: 0, role: 'child', session: 'a' },
    { t: 10, role: 'buddy', session: 'a' },
    { t: 20, role: 'child', session: 'b' },
    { t: 500, role: 'buddy' },
  ])
  expect(v.map((x) => x.map((e) => e.t))).toEqual([[500], [20], [0, 10]])
})
