import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AuditLogClient from '@/app/(app)/admin/audit/AuditLogClient'
import InvitationsClient from '@/app/(app)/admin/invitations/InvitationsClient'
import InviteClient from '@/app/invite/[token]/InviteClient'
import { axeCheck } from './a11y'

const INVITATION = {
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
}

const EVENT = {
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
}

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchInvitations: async () => ({
      total: 1,
      limit: 25,
      offset: 0,
      assignable_roles: ['admin', 'analyst', 'editor', 'viewer'],
      invitations: [INVITATION],
    }),
    createInvitation: async () => ({}),
    resendInvitation: async () => ({}),
    revokeInvitation: async () => ({}),
    fetchAuditEvents: async () => ({
      total: 1,
      limit: 25,
      offset: 0,
      sort: 'occurred_at',
      order: 'desc',
      actions: ['member:update'],
      events: [EVENT],
    }),
    fetchRecordHistory: async () => ({
      total: 0,
      limit: 100,
      offset: 0,
      sort: 'occurred_at',
      order: 'asc',
      actions: [],
      events: [],
    }),
    fetchAuditIntegrity: async () => ({
      checked: 1,
      intact: 1,
      altered: 0,
      unverifiable: 0,
      altered_ids: [],
      ok: true,
    }),
    previewInvitation: async () => ({
      email: 'newbie@acme.test',
      role: 'analyst',
      organization_name: 'Acme Industries',
      expires_at: '2026-08-19T00:00:00Z',
    }),
  }
})

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({
    status: 'anonymous',
    user: null,
    acceptInvite: vi.fn(),
  }),
}))

describe('Admin Panel accessibility', () => {
  beforeEach(() => vi.clearAllMocks())

  it('has no axe violations on the invitations screen', async () => {
    const { container } = render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('gives the invitations table a caption', async () => {
    const { container } = render(<InvitationsClient />)
    await screen.findByText('newbie@acme.test')

    expect(container.querySelector('caption')?.textContent).toMatch(/invitations to this/i)
  })

  it('has no axe violations on the audit log', async () => {
    const { container } = render(<AuditLogClient />)
    await screen.findByText('owner@acme.test')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('names the expand control per row, so it is not announced as a bare button', async () => {
    render(<AuditLogClient />)
    await screen.findByText('owner@acme.test')

    // aria-expanded is what tells a screen-reader user the detail panel exists
    // at all; without it "Show" is a button that appears to do nothing.
    expect(screen.getByRole('button', { name: 'Show' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('has no axe violations on the invitation accept screen', async () => {
    const { container } = render(<InviteClient token="tok-abc" />)
    await screen.findByText('newbie@acme.test')

    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
