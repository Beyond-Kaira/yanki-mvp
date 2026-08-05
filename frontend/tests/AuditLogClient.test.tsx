import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AuditLogClient from '@/app/admin/audit/AuditLogClient'
import { ApiError } from '@/lib/api'

const fetchAuditEvents = vi.fn()
const fetchRecordHistory = vi.fn()
const fetchAuditIntegrity = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchAuditEvents: (...args: unknown[]) => fetchAuditEvents(...args),
    fetchRecordHistory: (...args: unknown[]) => fetchRecordHistory(...args),
    fetchAuditIntegrity: (...args: unknown[]) => fetchAuditIntegrity(...args),
  }
})

let searchParams = new URLSearchParams()
vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}))

function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 'ev-1',
    occurred_at: '2026-08-05T10:00:00Z',
    action: 'member:update',
    outcome: 'success',
    actor_type: 'user',
    actor_id: 'u-1',
    actor_label: 'owner@acme.test',
    entity_type: 'user',
    entity_id: 'u-2',
    before: { role: 'viewer' },
    after: { role: 'editor' },
    changed: { role: { from: 'viewer', to: 'editor' } },
    ip_hash: 'a'.repeat(64),
    user_agent: 'Mozilla/5.0',
    request_id: 'req-123',
    integrity: 'ok',
    ...overrides,
  }
}

function listOf(events: ReturnType<typeof event>[], overrides: Record<string, unknown> = {}) {
  return {
    total: events.length,
    limit: 25,
    offset: 0,
    sort: 'occurred_at',
    order: 'desc',
    actions: ['auth:login', 'member:update'],
    events,
    ...overrides,
  }
}

// `member:update` is both a row value and an entry in the action filter, which
// is populated from the data — so row assertions are scoped to the table.
const inTable = () => within(screen.getByRole('table'))
const rowsLoaded = () => screen.findByText('owner@acme.test')

describe('AuditLogClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    searchParams = new URLSearchParams()
    fetchAuditEvents.mockResolvedValue(listOf([event()]))
    fetchRecordHistory.mockResolvedValue(
      listOf([event()], { order: 'asc', sort: 'occurred_at' }),
    )
    fetchAuditIntegrity.mockResolvedValue({
      checked: 12,
      intact: 12,
      altered: 0,
      unverifiable: 0,
      altered_ids: [],
      ok: true,
    })
  })

  it('lists events with actor, action and outcome', async () => {
    render(<AuditLogClient />)
    await rowsLoaded()

    expect(inTable().getByText('member:update')).toBeVisible()
    expect(inTable().getByText('owner@acme.test')).toBeVisible()
    expect(inTable().getByText('success')).toBeVisible()
  })

  it('shows the before/after diff, the request id and the hashed ip on demand', async () => {
    const user = userEvent.setup()
    render(<AuditLogClient />)
    await rowsLoaded()

    await user.click(screen.getByRole('button', { name: 'Show' }))

    expect(await screen.findByText('role: "viewer" → "editor"')).toBeVisible()
    expect(screen.getByText('req-123')).toBeVisible()
    // Truncated for readability, and never the raw address — there isn't one.
    expect(screen.getByText(/^a{16}…$/)).toBeVisible()
  })

  it('narrows by action, outcome and date in one query', async () => {
    const user = userEvent.setup()
    render(<AuditLogClient />)
    await rowsLoaded()

    await user.selectOptions(screen.getByLabelText('Action'), 'auth:login')
    await waitFor(() =>
      expect(fetchAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ action: 'auth:login' }),
      ),
    )

    await user.selectOptions(screen.getByLabelText('Outcome'), 'denied')
    await waitFor(() =>
      expect(fetchAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ outcome: 'denied' }),
      ),
    )
  })

  it('sends the end of the day for a "to" date, not its midnight', async () => {
    const user = userEvent.setup()
    render(<AuditLogClient />)
    await rowsLoaded()

    await user.type(screen.getByLabelText('To'), '2026-08-05')

    // Midnight would exclude everything that happened on the chosen day, which
    // reads as "the log is empty" rather than as an off-by-one.
    await waitFor(() =>
      expect(fetchAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ occurred_to: '2026-08-05T23:59:59' }),
      ),
    )
  })

  it('toggles the sort direction', async () => {
    const user = userEvent.setup()
    render(<AuditLogClient />)
    await rowsLoaded()

    await user.click(screen.getByRole('button', { name: /sort ascending/i }))

    await waitFor(() =>
      expect(fetchAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ order: 'asc' }),
      ),
    )
  })

  it('reports a clean integrity sweep', async () => {
    render(<AuditLogClient />)

    expect(await screen.findByText(/12 of 12 recent entries verified/i)).toBeVisible()
  })

  it('raises an alarm when the log has been edited out of band', async () => {
    fetchAuditIntegrity.mockResolvedValue({
      checked: 12,
      intact: 11,
      altered: 1,
      unverifiable: 0,
      altered_ids: ['ev-1'],
      ok: false,
    })
    fetchAuditEvents.mockResolvedValue(listOf([event({ integrity: 'altered' })]))
    render(<AuditLogClient />)

    const alarm = await screen.findByRole('alert')
    expect(alarm).toHaveTextContent(/no longer match their stored hash/i)
    await rowsLoaded()
    expect(inTable().getByText('Altered')).toBeVisible()
  })

  it('marks a row written before hashing as unverifiable rather than fine', async () => {
    fetchAuditEvents.mockResolvedValue(listOf([event({ integrity: 'unverifiable' })]))
    render(<AuditLogClient />)
    await rowsLoaded()

    expect(inTable().getByText('Unverifiable')).toBeVisible()
  })

  it('renders one record history when the URL scopes it', async () => {
    searchParams = new URLSearchParams({ entity_type: 'user', entity_id: 'u-2' })
    render(<AuditLogClient />)

    expect(await screen.findByRole('heading', { name: 'Change history' })).toBeVisible()
    await waitFor(() => expect(fetchRecordHistory).toHaveBeenCalledWith('user', 'u-2'))
    expect(fetchAuditEvents).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: /view the whole audit log/i })).toBeVisible()
  })

  it('explains a permission refusal instead of showing an empty table', async () => {
    fetchAuditEvents.mockRejectedValue(new ApiError('forbidden', 403))
    render(<AuditLogClient />)

    expect(await screen.findByText(/do not have permission to read the audit log/i)).toBeVisible()
  })

  it('still shows the log when the integrity sweep itself fails', async () => {
    fetchAuditIntegrity.mockRejectedValue(new ApiError('boom', 500))
    render(<AuditLogClient />)
    await rowsLoaded()

    expect(inTable().getByText('member:update')).toBeVisible()
  })
})

describe('AuditLogClient entity filter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    searchParams = new URLSearchParams()
    fetchAuditEvents.mockResolvedValue(
      listOf([event()], { actions: ['auth:login', 'member:update', 'invitation:create'] }),
    )
    fetchAuditIntegrity.mockResolvedValue({
      checked: 1, intact: 1, altered: 0, unverifiable: 0, altered_ids: [], ok: true,
    })
  })

  it('offers entity types derived from the action taxonomy', async () => {
    render(<AuditLogClient />)
    await rowsLoaded()

    const picker = screen.getByLabelText('Entity')
    const options = within(picker).getAllByRole('option').map((o) => o.textContent)
    // `resource:action` means the prefix IS the entity type — no second request.
    expect(options).toEqual(['All entities', 'auth', 'invitation', 'member'])
  })

  it('narrows the query by entity type', async () => {
    const user = userEvent.setup()
    render(<AuditLogClient />)
    await rowsLoaded()

    await user.selectOptions(screen.getByLabelText('Entity'), 'invitation')

    await waitFor(() =>
      expect(fetchAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ entity_type: 'invitation' }),
      ),
    )
  })
})
