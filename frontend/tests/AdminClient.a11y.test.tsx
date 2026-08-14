import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminClient from '@/app/admin/AdminClient'
import { axeCheck } from './a11y'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchOrganization: async () => ({
      id: 'o', name: 'Acme', slug: 'acme', kind: 'company',
      status: 'active', created_at: '2026-01-01T00:00:00Z', member_count: 1,
    }),
    fetchMembers: async () => ({
      total: 1, limit: 25, offset: 0,
      assignable_roles: ['owner', 'admin', 'editor', 'viewer'],
      members: [{
        id: 'u1', email: 'someone@acme.test', status: 'active',
        created_at: '2026-02-01T00:00:00Z', last_active_at: null,
        role: 'editor', membership_status: 'active', membership_id: 'm1',
      }],
    }),
    removeMember: async () => undefined,
    updateMember: async () => ({}),
  }
})

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({ status: 'authenticated', user: { id: 'me', email: 'me@acme.test' } }),
}))

describe('Admin panel accessibility', () => {
  beforeEach(() => vi.clearAllMocks())

  it('has no axe violations once loaded', async () => {
    const { container } = render(<AdminClient />)
    await screen.findByText('someone@acme.test')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('labels every per-row control, so a screen reader knows which member it edits', async () => {
    render(<AdminClient />)
    await screen.findByText('someone@acme.test')

    // Without these the row's two icons are announced only as their glyphs.
    expect(screen.getByRole('button', { name: /disable someone@acme.test/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /remove someone@acme.test/i })).toBeVisible()
  })

  it('gives the table a caption', async () => {
    const { container } = render(<AdminClient />)
    await screen.findByText('someone@acme.test')

    expect(container.querySelector('caption')?.textContent).toMatch(/members of this organization/i)
  })
})
