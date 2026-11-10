import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { ParentAlerts } from '../hooks/useParentAlerts'
import { ParentAlertsPanel } from './ParentAlertsPanel'

let state: ParentAlerts
let calls: string[]

function reply(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
}

function recount() {
  state.unreviewed = state.alerts.filter((a) => !a.reviewed).length
}

beforeEach(() => {
  state = {
    enabled: true,
    push: false,
    unreviewed: 1,
    alerts: [
      {
        id: 'a1',
        ts: 1_700_000_000,
        categories: ['secret'],
        summary: 'asked Buddy to keep a secret',
        child_text: 'promise you won’t tell',
        buddy_reply: 'Grown-ups need to know.',
        reviewed: false,
      },
    ],
  }
  calls = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push(`${method} ${url}`)
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    if (method === 'PATCH')
      state.alerts = state.alerts.map((a) => ({ ...a, reviewed: body.reviewed }))
    if (method === 'DELETE') state.alerts = []
    recount()
    return reply(state)
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
      <ParentAlertsPanel />
    </QueryClientProvider>,
  )
}

test('shows the alert with the child’s words and Buddy’s reply', async () => {
  renderPanel()
  expect(await screen.findByText(/a child asked Buddy to keep a secret/)).toBeTruthy()
  expect(screen.getByText('Child: “promise you won’t tell”')).toBeTruthy()
  expect(screen.getByText('Buddy: “Grown-ups need to know.”')).toBeTruthy()
  expect(screen.getByText('1 new')).toBeTruthy()
  expect(screen.getByText('phone push off')).toBeTruthy()
})

test('mark reviewed clears the new count', async () => {
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: 'Mark reviewed' }))
  await waitFor(() => expect(screen.queryByText('1 new')).toBeNull())
  expect(calls).toContain('PATCH /api/parent-alerts/a1')
})

test('clear all asks first', async () => {
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: 'Clear all' }))
  expect(calls).not.toContain('DELETE /api/parent-alerts')
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
  expect(await screen.findByText('Nothing to follow up.')).toBeTruthy()
})
