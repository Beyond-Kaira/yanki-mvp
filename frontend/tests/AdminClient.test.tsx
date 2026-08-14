import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminClient from '@/app/admin/AdminClient'
import { ApiError } from '@/lib/api'

const fetchMembers = vi.fn()
const fetchOrganization = vi.fn()
const removeMember = vi.fn()
const push = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchMembers: (...args: unknown[]) => fetchMembers(...args),
    fetchOrganization: (...args: unknown[]) => fetchOrganization(...args),
    removeMember: (...args: unknown[]) => removeMember(...args),
  }
})

vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { id: 'me', email: 'owner@acme.test' },
  }),
}))

const ORG = {
  id: 'org-1',
  name: 'Acme Industries',
  slug: 'acme-industries',
  kind: 'company',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  member_count: 3,
}

function member(overrides: Record<string, unknown> = {}) {
  return {
    id: 'u-1',
    email: 'editor@acme.test',
    status: 'active',
    created_at: '2026-02-01T00:00:00Z',
    last_active_at: null,
    role: 'editor',
    membership_status: 'active',
    membership_id: 'm-1',
    ...overrides,
  }
}

function listOf(members: ReturnType<typeof member>[], total?: number) {
  return {
    total: total ?? members.length,
    limit: 25,
    offset: 0,
    // Deliberately excludes the platform roles, mirroring the API.
    assignable_roles: [
      'admin',
      'analyst',
      'billing_admin',
      'editor',
      'guest',
      'manager',
      'owner',
      'viewer',
    ],
    members,
  }
}

describe('AdminClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchOrganization.mockResolvedValue(ORG)
    fetchMembers.mockResolvedValue(listOf([member(), member({ id: 'me', email: 'owner@acme.test', role: 'owner' })]))
    removeMember.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows the organization and its members', async () => {
    render(<AdminClient />)

    expect(await screen.findByText(/Acme Industries/)).toBeVisible()
    expect(screen.getByText(/Organization account/)).toBeVisible()
    expect(await screen.findByText('editor@acme.test')).toBeVisible()
  })

  it('offers only the roles the server said are assignable', async () => {
    render(<AdminClient />)

    await screen.findByText('editor@acme.test')
    const select = screen.getByLabelText(/^role$/i)
    const options = within(select).getAllByRole('option').map((o) => o.textContent)

    expect(options).toContain('Editor')
    expect(options).toContain('Owner')
    // A customer must never be offered a platform role.
    expect(options.join(' ')).not.toMatch(/super admin|support/i)
  })

  it('searches by email', async () => {
    const user = userEvent.setup()
    render(<AdminClient />)
    await screen.findByText('editor@acme.test')

    await user.type(screen.getByLabelText(/search/i), 'edit')

    await waitFor(() =>
      expect(fetchMembers).toHaveBeenCalledWith(expect.objectContaining({ q: 'edit' })),
    )
  })

  it('filters by role and status', async () => {
    const user = userEvent.setup()
    render(<AdminClient />)
    await screen.findByText('editor@acme.test')

    await user.selectOptions(screen.getByLabelText(/^role$/i), 'viewer')
    await waitFor(() =>
      expect(fetchMembers).toHaveBeenCalledWith(expect.objectContaining({ role: 'viewer' })),
    )

    await user.selectOptions(screen.getByLabelText(/^status$/i), 'disabled')
    await waitFor(() =>
      expect(fetchMembers).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'disabled' }),
      ),
    )
  })

  it('opens that member\u2019s history from the row', async () => {
    const user = userEvent.setup()
    render(<AdminClient />)
    const row = (await screen.findByText('editor@acme.test')).closest('tr')!

    // The email is the row's keyboard-reachable link; the row itself carries
    // the same destination for a click anywhere on it.
    expect(within(row).getByRole('link', { name: 'editor@acme.test' })).toHaveAttribute(
      'href',
      '/admin/audit?entity_type=user&entity_id=u-1',
    )

    await user.click(within(row).getByText(/Editor/))
    expect(push).toHaveBeenCalledWith('/admin/audit?entity_type=user&entity_id=u-1')
  })

  it('removes a member after asking', async () => {
    const user = userEvent.setup()
    render(<AdminClient />)
    const row = (await screen.findByText('editor@acme.test')).closest('tr')!

    await user.click(within(row).getByRole('button', { name: /remove editor@acme.test/i }))

    await waitFor(() => expect(removeMember).toHaveBeenCalledWith('u-1'))
    // Removing must not also navigate: the row's click handler sits underneath.
    expect(push).not.toHaveBeenCalled()
    expect(await screen.findByRole('status')).toHaveTextContent(/no longer has a seat/i)
  })

  it('cannot edit your own row', async () => {
    render(<AdminClient />)
    const row = (await screen.findByText('owner@acme.test')).closest('tr')!

    expect(within(row).getByText(/that's you/i)).toBeVisible()
    // The only control left that could change your own seat.
    expect(
      within(row).getByRole('button', { name: /remove owner@acme.test/i }),
    ).toBeDisabled()
  })

  it("surfaces the server's refusal rather than inventing one", async () => {
    const user = userEvent.setup()
    removeMember.mockRejectedValue(
      new ApiError('an organization must keep at least one active owner', 409),
    )
    render(<AdminClient />)
    const row = (await screen.findByText('editor@acme.test')).closest('tr')!

    await user.click(within(row).getByRole('button', { name: /remove editor@acme.test/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /at least one active owner/i,
    )
    // The row must NOT show the change as applied.
    expect(within(row).getByText('editor@acme.test')).toBeVisible()
  })

  it('explains a permission refusal instead of showing an empty table', async () => {
    fetchMembers.mockRejectedValue(new ApiError('forbidden', 403))
    render(<AdminClient />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /do not have permission/i,
    )
  })

  it('says so when nothing matches the filters', async () => {
    const user = userEvent.setup()
    render(<AdminClient />)
    await screen.findByText('editor@acme.test')

    fetchMembers.mockResolvedValue(listOf([]))
    await user.type(screen.getByLabelText(/search/i), 'nobody')

    expect(await screen.findByText(/no members match/i)).toBeVisible()
  })

  it('pages only when there is more than one page', async () => {
    fetchMembers.mockResolvedValue(listOf([member()], 60))
    render(<AdminClient />)

    expect(await screen.findByText(/Showing 1–25 of 60/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('keeps the wide table inside its own scroll container', async () => {
    const { container } = render(<AdminClient />)
    await screen.findByText('editor@acme.test')

    // The classic mobile overflow is a wide table pushing the PAGE sideways.
    expect(container.querySelector('.overflow-x-auto')).not.toBeNull()
  })
})
