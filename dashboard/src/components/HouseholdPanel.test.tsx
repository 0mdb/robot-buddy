import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { Household } from '../hooks/useHousehold'
import { HouseholdPanel } from './HouseholdPanel'

// A fake /api/household with the server's rules that matter here. Synthetic names only.
let state: Household
let calls: string[]

function reply(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

beforeEach(() => {
  state = { enabled: false, members: [] }
  calls = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push(`${method} ${url}`)
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    if (method === 'GET') return reply(state)
    if (url === '/api/household/enabled') state = { ...state, enabled: body.enabled }
    else if (method === 'POST') {
      if (body.kind === 'kid' && body.age === undefined)
        return reply({ ok: false, reason: "a child's age is required" }, 422)
      state = { ...state, members: [...state.members, { id: `id${calls.length}`, ...body }] }
    } else if (method === 'DELETE' && url === '/api/household')
      state = { enabled: false, members: [] }
    else if (method === 'DELETE')
      state = { ...state, members: state.members.filter((m) => !url.endsWith(m.id)) }
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
      <HouseholdPanel />
    </QueryClientProvider>,
  )
}

test('off by default; enrol a child, switch on, remove', async () => {
  renderPanel()
  const toggle = await screen.findByRole('checkbox', { name: 'Use roster' })
  await waitFor(() => expect((toggle as HTMLInputElement).disabled).toBe(false))
  expect((toggle as HTMLInputElement).checked).toBe(false)

  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Test Kid' } })
  fireEvent.change(screen.getByLabelText('Age'), { target: { value: '6' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
  expect(await screen.findByText('Test Kid')).toBeTruthy()
  expect(screen.getByText('Child, 6')).toBeTruthy()
  expect(calls).toContain('POST /api/household/members')

  fireEvent.click(toggle)
  await waitFor(() => expect((toggle as HTMLInputElement).checked).toBe(true))

  fireEvent.click(screen.getByRole('button', { name: 'Remove Test Kid' }))
  await waitFor(() => expect(screen.queryByText('Test Kid')).toBeNull())
})

test('pets have no age field', async () => {
  renderPanel()
  await screen.findByRole('checkbox', { name: 'Use roster' })
  fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'animal' } })
  expect(screen.queryByLabelText('Age')).toBeNull()
})

test('forget everyone asks first, then clears', async () => {
  state = { enabled: true, members: [{ id: 'a1', name: 'Test Parent', kind: 'adult' }] }
  renderPanel()
  expect(await screen.findByText('Test Parent')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Forget everyone' }))
  expect(calls).not.toContain('DELETE /api/household')
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
  await waitFor(() => expect(screen.queryByText('Test Parent')).toBeNull())
  expect(calls).toContain('DELETE /api/household')
})

test('server refusals are shown', async () => {
  state = { enabled: false, members: [] }
  renderPanel()
  await screen.findByRole('checkbox', { name: 'Use roster' })
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Test Kid' } })
  // bypass the browser's required-field check to reach the server's rule
  fireEvent.submit(screen.getByRole('button', { name: 'Add' }).closest('form') as HTMLFormElement)
  expect((await screen.findByRole('alert')).textContent).toContain('age is required')
})
