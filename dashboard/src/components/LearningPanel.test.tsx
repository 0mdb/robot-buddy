import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { Learning } from '../hooks/useLearning'
import { LearningPanel } from './LearningPanel'

// A fake /api/learning. Synthetic names only.
let state: Learning
let calls: string[]

function reply(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

const GRADES = [
  { id: 'K', name: 'Kindergarten' },
  { id: 'G1', name: 'Grade 1' },
  { id: 'G2', name: 'Grade 2' },
  { id: 'G3', name: 'Grade 3' },
] as Learning['grades']

beforeEach(() => {
  calls = []
  state = {
    enabled: true,
    grades: GRADES,
    children: [
      {
        member_id: 'kid_a',
        name: 'Sam',
        age: 7,
        base: 'G2',
        ceiling: 'G3',
        ceiling_is_default: true,
        skills: [
          {
            skill: 'add_sub_facts',
            step: 'G2',
            mastered: [],
            confident: true,
            games: [{ day: '2026-11-18', step: 'G2', right: 4, of: 5 }],
            trend: 0.8,
            code_share: 1,
            missed_most: ['What is 7 plus 8?'],
          },
        ],
      },
      {
        member_id: 'kid_b',
        name: 'Pip',
        age: 5,
        base: 'K',
        ceiling: 'G1',
        ceiling_is_default: true,
        skills: [],
      },
    ],
  }
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push(`${method} ${url}`)
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    const ceil = url.match(/^\/api\/learning\/([^/]+)\/ceiling$/)
    if (ceil) {
      const c = state.children.find((x) => x.member_id === ceil[1])
      if (!c) return reply({ error: 'no such child' }, 404)
      c.ceiling = body.ceiling ?? 'G3'
      c.ceiling_is_default = body.ceiling === null
      return reply(c)
    }
    const del = url.match(/^\/api\/learning\/([^/]+)$/)
    if (del && method === 'DELETE') {
      const c = state.children.find((x) => x.member_id === del[1])
      if (c) c.skills = []
      return reply(c)
    }
    return reply(state)
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <LearningPanel />
    </QueryClientProvider>,
  )
}

test('shows each child, their skills, and the confident badge', async () => {
  renderPanel()
  expect(await screen.findByText('Sam')).toBeTruthy()
  expect(screen.getByText('Pip')).toBeTruthy()
  expect(screen.getByText(/Rocket Math/)).toBeTruthy()
  expect(screen.getAllByText('confident').length).toBe(2) // the badge, and the note above
  expect(screen.getByText('4/5')).toBeTruthy()
  expect(screen.getByText('No games played yet.')).toBeTruthy()
})

test('setting a ceiling sends it, and Default sends null', async () => {
  renderPanel()
  const select = (await screen.findByLabelText('Grade ceiling for Sam')) as HTMLSelectElement
  fireEvent.change(select, { target: { value: 'G2' } })
  await waitFor(() => expect(calls).toContain('PUT /api/learning/kid_a/ceiling'))
  fireEvent.change(select, { target: { value: '' } })
  await waitFor(() =>
    expect(calls.filter((c) => c === 'PUT /api/learning/kid_a/ceiling').length).toBe(2),
  )
})

test('reset asks for confirmation first', async () => {
  renderPanel()
  fireEvent.click(await screen.findByLabelText('Reset progress for Sam'))
  expect(calls).not.toContain('DELETE /api/learning/kid_a')
  fireEvent.click(screen.getByText('Confirm reset'))
  await waitFor(() => expect(calls).toContain('DELETE /api/learning/kid_a'))
})
