import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SeoProject } from '@/lib/contracts'
import { axeCheck } from './a11y'

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedListSeoProjects = vi.hoisted(() => vi.fn())
const mockedCreateSeoProject = vi.hoisted(() => vi.fn())
const mockedDeleteSeoProject = vi.hoisted(() => vi.fn())

vi.mock('@/components/AuthProvider', () => ({
  useAuth: mockedUseAuth,
}))

vi.mock('@/lib/api', () => ({
  createSeoProject: mockedCreateSeoProject,
  deleteSeoProject: mockedDeleteSeoProject,
  listSeoProjects: mockedListSeoProjects,
}))

import SiteAuditDashboard from '@/components/site-audit/dashboard/SiteAuditDashboard'

const PROJECT: SeoProject = {
  id: '4bb0f6e1-d873-47ce-b15a-d166c43f91f8',
  name: 'Dream Games',
  domain: 'https://www.dreamgames.com/',
  created_at: '2026-08-04T09:00:00Z',
  updated_at: '2026-08-04T10:30:00Z',
  latest_audit: null,
}

describe('SiteAuditDashboard accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue({ status: 'authenticated', user: null })
  })

  it('has no axe violations in the empty state', async () => {
    mockedListSeoProjects.mockResolvedValue([])
    const { container } = render(<SiteAuditDashboard />)

    await screen.findByRole('heading', {
      name: /find the technical issues holding your website back/i,
    })
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the crawl settings dialog', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([])
    const { container } = render(<SiteAuditDashboard />)

    await user.type(
      await screen.findByRole('textbox', { name: /domain/i }),
      'dreamgames.com',
    )
    await user.click(screen.getByRole('button', { name: /configure audit/i }))

    await screen.findByRole('dialog', { name: /configure your crawl/i })
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations with the project table', async () => {
    mockedListSeoProjects.mockResolvedValue([PROJECT])
    const { container } = render(<SiteAuditDashboard />)

    await screen.findByText('Dream Games')
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the delete confirmation', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([PROJECT])
    const { container } = render(<SiteAuditDashboard />)

    await user.click(await screen.findByRole('button', { name: 'Delete Dream Games' }))

    // The dialog names itself by the heading the user reads, and describes
    // itself by the consequence — neither duplicated into an aria- string.
    const dialog = await screen.findByRole('dialog', { name: 'Delete Dream Games?' })
    expect(dialog).toHaveAccessibleDescription(/cannot be undone/i)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('announces a loading failure with no axe violations', async () => {
    mockedListSeoProjects.mockRejectedValue(new Error('The network is offline.'))
    const { container } = render(<SiteAuditDashboard />)

    await screen.findByRole('alert')
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
