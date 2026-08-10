import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InvitationsClient from '@/app/(app)/admin/invitations/InvitationsClient'
import { ApiError } from '@/lib/api'

const fetchInvitations = vi.fn()
const createInvitation = vi.fn()
const resendInvitation = vi.fn()
const revokeInvitation = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchInvitations: (...args: unknown[]) => fetchInvitations(...args),
    createInvitation: (...args: unknown[]) => createInvitation(...args),
    resendInvitation: (...args: unknown[]) => resendInvitation(...args),
    revokeInvitation: (...args: unknown[]) => revokeInvitation(...args),
  }
})

function invitation(overrides: Record<string, unknown> = {}) {
  return {
    id: 'inv-1',
    email: 'newbie@acme.test',
    role: 'analyst',
    status: 'pending',
    expired: false,
    created_at: '2026-08-01T00:00:00Z',
    expires_at: '2026-08-15T00:00:00Z',
    accepted_at: null,
    revoked_at: null,
    last_sent_at: '2026-08-01T00:00:00Z',
    sent_count: 1,
    invited_by_email: 'owner@acme.test',
    ...overrides,
  }
}

function listOf(invitations: ReturnType<typeof invitation>[], total?: number) {
  return {
    total: total ?? invitations.length,
    limit: 25,
    offset: 0,
    assignable_roles: ['admin', 'analyst', 'editor', 'guest', 'manager', 'owner', 'viewer'],
    invitations,
  }
}

// Several labels appear twice on this screen — once as a filter <option> and
// once as a row badge — so row assertions are scoped to the table rather than
// to the document.
const inTable = () => within(screen.getByRole('table'))

describe('InvitationsClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchInvitations.mockResolvedValue(listOf([invitation()]))
    createInvitation.mockResolvedValue({
      invitation: invitation({ id: 'inv-2', email: 'fresh@acme.test' }),
      accept_url: 'https://yanki.test/invite/tok-abc',
      email_sent: false,
    })
    resendInvitation.mockResolvedValue({
      invitation: invitation({ sent_count: 2 }),
      accept_url: 'https://yanki.test/invite/tok-new',
      email_sent: true,
    })
    revokeInvitation.mockResolvedValue(invitation({ status: 'revoked' }))
  })

  it('lists invitations with who invited them', async () => {
    render(<InvitationsClient />)

    expect(await screen.findByText('newbie@acme.test')).toBeVisible()
    expect(screen.getByText(/invited by owner@acme.test/i)).toBeVisible()
    expect(inTable().getByText('Pending')).toBeVisible()
  })

  it('populates the role picker from the server, never a local constant', async () => {
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    const picker = screen.getByLabelText('Role')
    const options = within(picker).getAllByRole('option').map((o) => o.textContent)
    // The platform roles are absent because the API excludes them — a hardcoded
    // list here could drift into offering one.
    expect(options).not.toContain('Super admin')
    expect(options).toContain('Analyst')
  })

  it('sends an invitation and reports that email did not go out', async () => {
    const user = userEvent.setup()
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    await user.type(screen.getByLabelText('Email address'), 'fresh@acme.test')
    await user.click(screen.getByRole('button', { name: /send invitation/i }))

    await waitFor(() => expect(createInvitation).toHaveBeenCalledWith('fresh@acme.test', 'analyst'))
    // The honest half: email is off by default, so the panel says so and shows
    // the link rather than claiming a send that never happened.
    expect(await screen.findByText(/email is not configured/i)).toBeVisible()
    expect(screen.getByText('https://yanki.test/invite/tok-abc')).toBeVisible()
  })

  it('does not show a link when the email actually went out', async () => {
    const user = userEvent.setup()
    createInvitation.mockResolvedValue({
      invitation: invitation({ id: 'inv-2', email: 'fresh@acme.test' }),
      accept_url: 'https://yanki.test/invite/tok-abc',
      email_sent: true,
    })
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    await user.type(screen.getByLabelText('Email address'), 'fresh@acme.test')
    await user.click(screen.getByRole('button', { name: /send invitation/i }))

    expect(await screen.findByText(/invitation emailed to/i)).toBeVisible()
    expect(screen.queryByText('https://yanki.test/invite/tok-abc')).not.toBeInTheDocument()
  })

  it('says plainly that resending retires the previous link', async () => {
    const user = userEvent.setup()
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    await user.click(screen.getByRole('button', { name: 'Resend' }))

    await waitFor(() => expect(resendInvitation).toHaveBeenCalledWith('inv-1'))
    expect(await screen.findByText(/previous link no longer works/i)).toBeVisible()
  })

  it('withdraws an invitation and reflects the new state', async () => {
    const user = userEvent.setup()
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    await user.click(screen.getByRole('button', { name: 'Withdraw' }))

    await waitFor(() => expect(revokeInvitation).toHaveBeenCalledWith('inv-1'))
    await waitFor(() => expect(inTable().getByText('Revoked')).toBeVisible())
  })

  it('shows an expired invitation as expired even while its status says pending', async () => {
    // Expiry is derived from the clock, not stored — so a row can be `pending`
    // in the database and dead in reality. Showing "Pending" there would be a
    // lie the admin acts on.
    fetchInvitations.mockResolvedValue(listOf([invitation({ expired: true })]))
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    expect(inTable().getByText('Expired')).toBeVisible()
  })

  it('cannot resend or withdraw an invitation that was accepted', async () => {
    fetchInvitations.mockResolvedValue(
      listOf([invitation({ status: 'accepted', accepted_at: '2026-08-02T00:00:00Z' })]),
    )
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    expect(inTable().getByText('Accepted')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Resend' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeDisabled()
  })

  it("surfaces the server's refusal rather than inventing one", async () => {
    const user = userEvent.setup()
    createInvitation.mockRejectedValue(
      new ApiError('that person is already a member of this organization', 409),
    )
    render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    await user.type(screen.getByLabelText('Email address'), 'already@acme.test')
    await user.click(screen.getByRole('button', { name: /send invitation/i }))

    expect(
      await screen.findByText('that person is already a member of this organization'),
    ).toBeVisible()
  })

  it('explains a permission refusal instead of showing an empty table', async () => {
    fetchInvitations.mockRejectedValue(new ApiError('forbidden', 403))
    render(<InvitationsClient />)

    expect(await screen.findByText(/do not have permission/i)).toBeVisible()
  })
})
