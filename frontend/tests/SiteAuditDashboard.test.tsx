import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SeoProject } from '@/lib/contracts'

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedListSeoProjects = vi.hoisted(() => vi.fn())
const mockedCreateSeoProject = vi.hoisted(() => vi.fn())

vi.mock('@/components/AuthProvider', () => ({
  useAuth: mockedUseAuth,
}))

vi.mock('@/lib/api', () => ({
  // A faithful stand-in for the real ApiError so the component's
  // `error instanceof ApiError` branch resolves against the same class the test
  // throws with.
  ApiError: class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
  createSeoProject: mockedCreateSeoProject,
  listSeoProjects: mockedListSeoProjects,
}))

import SiteAuditDashboard from '@/components/site-audit/dashboard/SiteAuditDashboard'
import { ApiError } from '@/lib/api'

const PROJECT: SeoProject = {
  id: '4bb0f6e1-d873-47ce-b15a-d166c43f91f8',
  name: 'Dream Games',
  domain: 'https://www.dreamgames.com/',
  created_at: '2026-08-04T09:00:00Z',
  updated_at: '2026-08-04T10:30:00Z',
  latest_audit: {
    id: 'fa51dd7c-6c71-45ab-b40d-b28395d8c0f6',
    project_id: '4bb0f6e1-d873-47ce-b15a-d166c43f91f8',
    status: 'done',
    progress: 100,
    current_step: null,
    page_limit: 100,
    profile_id: 'site_audit_mobile',
    js_rendering: true,
    pages_discovered: 50,
    pages_crawled: 3,
    total_errors: 2,
    total_warnings: 7,
    total_notices: 1,
    health_score: 82,
    error: null,
    created_at: '2026-08-04T09:00:00Z',
    updated_at: '2026-08-04T10:30:00Z',
    started_at: '2026-08-04T09:00:05Z',
    completed_at: '2026-08-04T10:30:00Z',
  },
}

function authenticated() {
  mockedUseAuth.mockReturnValue({ status: 'authenticated', user: null })
}

describe('SiteAuditDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authenticated()
  })

  it('shows an honest loading state while projects are requested', () => {
    mockedListSeoProjects.mockReturnValue(new Promise(() => undefined))

    render(<SiteAuditDashboard />)

    expect(screen.getByRole('status')).toHaveTextContent(/loading seo projects/i)
  })

  it('shows the empty workspace state when the account has no projects', async () => {
    mockedListSeoProjects.mockResolvedValue([])

    render(<SiteAuditDashboard />)

    expect(
      await screen.findByRole('heading', {
        name: /find the technical issues holding your website back/i,
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /domain/i })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /configure audit/i }),
    ).toBeInTheDocument()
  })

  it('creates a project and queues its first audit with the chosen settings', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([])
    mockedCreateSeoProject.mockResolvedValue(PROJECT)

    render(<SiteAuditDashboard />)

    await user.type(
      await screen.findByRole('textbox', { name: /domain/i }),
      'dreamgames.com',
    )
    await user.click(screen.getByRole('button', { name: /configure audit/i }))

    expect(
      screen.getByRole('dialog', { name: /configure your crawl/i }),
    ).toBeInTheDocument()
    const pageLimit = screen.getByRole('spinbutton', { name: /limit per audit/i })
    await user.clear(pageLimit)
    await user.type(pageLimit, '3')
    await user.click(screen.getByRole('radio', { name: /desktop crawler/i }))
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^start audit$/i }))

    expect(mockedCreateSeoProject).toHaveBeenCalledWith({
      domain: 'dreamgames.com',
      name: null,
      page_limit: 3,
      profile_id: 'site_audit_desktop',
      js_rendering: false,
    })
    expect(await screen.findByText('Dream Games')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Dream Games' })).toHaveAttribute(
      'href',
      `/site-audit/${PROJECT.id}`,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('offers the start call-to-action when Site Audit is switched on', async () => {
    mockedListSeoProjects.mockResolvedValue([])

    render(<SiteAuditDashboard />)

    expect(
      await screen.findByRole('button', { name: /configure audit/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: /isn.t available yet/i }),
    ).not.toBeInTheDocument()
  })

  it('withdraws the start call-to-action and explains when Site Audit is off', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([])
    // Project creation stays open while the crawl is off: the project comes back
    // created but with no queued audit (`latest_audit: null`).
    mockedCreateSeoProject.mockResolvedValue({
      ...PROJECT,
      latest_audit: null,
    })

    render(<SiteAuditDashboard />)

    await user.type(
      await screen.findByRole('textbox', { name: /domain/i }),
      'dreamgames.com',
    )
    await user.click(screen.getByRole('button', { name: /configure audit/i }))
    await user.click(screen.getByRole('button', { name: /^start audit$/i }))

    // The honest notice replaces the CTA, which is now gone...
    expect(
      await screen.findByRole('heading', { name: /isn.t available yet/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /configure audit/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // ...the created project is listed and honestly reads "Not audited", never
    // stuck at "queued".
    expect(screen.getByRole('link', { name: 'Dream Games' })).toBeInTheDocument()
    expect(screen.getByText(/not audited/i)).toBeInTheDocument()
    expect(screen.queryByText(/queued|auditing/i)).not.toBeInTheDocument()
  })

  it('keeps existing projects viewable but drops the create button when off', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([PROJECT])
    // A second project is created (open), but with no crawl queued.
    mockedCreateSeoProject.mockResolvedValue({
      ...PROJECT,
      id: 'a2f3d5c6-0000-4000-8000-000000000abc',
      name: 'Second Site',
      latest_audit: null,
    })

    render(<SiteAuditDashboard />)

    // Open the compact create form and submit.
    await user.click(await screen.findByRole('button', { name: /new seo project/i }))
    await user.type(
      screen.getByRole('textbox', { name: /domain/i }),
      'secondsite.com',
    )
    await user.click(screen.getByRole('button', { name: /configure audit/i }))
    await user.click(screen.getByRole('button', { name: /^start audit$/i }))

    // Notice shown, both projects still listed, no create affordances left.
    expect(
      await screen.findByRole('heading', { name: /isn.t available yet/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Dream Games' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Second Site' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /new seo project/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /configure audit/i }),
    ).not.toBeInTheDocument()
  })

  it('still treats a 404 from create as "feature off" (older deployments)', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([])
    // A deployment that still gates project creation itself answers 404. The
    // client must fall back to the same honest notice, not surface a raw error.
    mockedCreateSeoProject.mockRejectedValue(
      new ApiError('Site Audit is not available in this deployment yet.', 404),
    )

    render(<SiteAuditDashboard />)

    await user.type(
      await screen.findByRole('textbox', { name: /domain/i }),
      'dreamgames.com',
    )
    await user.click(screen.getByRole('button', { name: /configure audit/i }))
    await user.click(screen.getByRole('button', { name: /^start audit$/i }))

    expect(
      await screen.findByRole('heading', { name: /isn.t available yet/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /configure audit/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('validates the domain before opening crawl settings', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects.mockResolvedValue([])

    render(<SiteAuditDashboard />)

    await user.type(
      await screen.findByRole('textbox', { name: /domain/i }),
      'https://',
    )
    await user.click(screen.getByRole('button', { name: /configure audit/i }))

    expect(screen.getByRole('alert')).toHaveTextContent(/valid domain/i)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockedCreateSeoProject).not.toHaveBeenCalled()
  })

  it('shows a retryable error and reloads the project list', async () => {
    const user = userEvent.setup()
    mockedListSeoProjects
      .mockRejectedValueOnce(new Error('The network is offline.'))
      .mockResolvedValueOnce([PROJECT])

    render(<SiteAuditDashboard />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The network is offline.',
    )
    await user.click(screen.getByRole('button', { name: /try again/i }))

    expect(await screen.findByText('Dream Games')).toBeInTheDocument()
    expect(mockedListSeoProjects).toHaveBeenCalledTimes(2)
  })

  it('renders only backend-supported project and audit fields', async () => {
    mockedListSeoProjects.mockResolvedValue([PROJECT])

    render(<SiteAuditDashboard />)

    expect(await screen.findByText('Dream Games')).toBeInTheDocument()
    expect(screen.getByText('https://www.dreamgames.com/')).toBeInTheDocument()
    expect(screen.getByText('3 / 100')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('2 errors')).toBeInTheDocument()
    expect(screen.getByText('7 warnings')).toBeInTheDocument()
    expect(screen.getByText('Complete')).toBeInTheDocument()
  })

  it('does not request account projects for an anonymous visitor', async () => {
    mockedUseAuth.mockReturnValue({ status: 'anonymous', user: null })

    render(<SiteAuditDashboard />)

    expect(
      screen.getByRole('heading', { name: /sign in to view site audit/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^sign in$/i })).toHaveAttribute(
      'href',
      '/login',
    )
    await waitFor(() => expect(mockedListSeoProjects).not.toHaveBeenCalled())
  })
})
