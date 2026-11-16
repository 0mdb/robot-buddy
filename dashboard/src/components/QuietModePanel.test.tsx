import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { QUIET_MODE_PARAM, QuietModePanel } from './QuietModePanel'

let quiet: boolean
let posts: unknown[]

beforeEach(() => {
  quiet = false
  posts = []
  vi.stubGlobal('fetch', (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      posts.push(body)
      quiet = body.items[QUIET_MODE_PARAM]
      return Promise.resolve(
        new Response(JSON.stringify({ [QUIET_MODE_PARAM]: { ok: true } }), { status: 200 }),
      )
    }
    return Promise.resolve(
      new Response(
        JSON.stringify([{ name: QUIET_MODE_PARAM, type: 'bool', value: quiet, doc: 'Quiet mode' }]),
        { status: 200 },
      ),
    )
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <QuietModePanel />
    </QueryClientProvider>,
  )
}

test('toggles conversation.quiet_mode', async () => {
  renderPanel()
  const box = await screen.findByRole('checkbox')
  expect((box as HTMLInputElement).checked).toBe(false)
  fireEvent.click(box)
  await waitFor(() => expect(posts).toEqual([{ items: { [QUIET_MODE_PARAM]: true } }]))
  await waitFor(() => expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true))
  expect(screen.getByText(/still warns about battery/)).toBeTruthy()
})
