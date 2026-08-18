import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedGetSeoProject = vi.hoisted(() => vi.fn())
const mockedGetSiteAudit = vi.hoisted(() => vi.fn())
const mockedStartSiteAudit = vi.hoisted(() => vi.fn())
// Mirrors the real class closely enough for `instanceof` plus `.status`, which
// is all the component asks of it.
const MockApiError = vi.hoisted(
  () =>
    class ApiError extends Error {
      status: number
      constructor(message: string, status: number) {
        super(message)
        this.status = status
      }
    },
)

vi.mock('next/navigation', () => ({
  useParams: () => ({ projectId: 'project-1' }),
}))
vi.mock('@/components/AuthProvider', () => ({ useAuth: mockedUseAuth }))
vi.mock('@/lib/api', () => ({
  ApiError: MockApiError,
  getSeoProject: mockedGetSeoProject,
  getSiteAudit: mockedGetSiteAudit,
  startSiteAudit: mockedStartSiteAudit,
}))

import SiteAuditProjectDetail from '@/components/site-audit/detail/SiteAuditProjectDetail'

const AUDIT: SiteAuditDetail = {
  id: 'audit-1', project_id: 'project-1', status: 'done', progress: 100,
  current_step: null, page_limit: 10, profile_id: 'site_audit_mobile',
  js_rendering: true, pages_discovered: 1, pages_crawled: 1,
  total_errors: 1, total_warnings: 1, total_notices: 0, health_score: 78,
  error: null, created_at: '2026-08-04T09:00:00Z',
  updated_at: '2026-08-04T09:05:00Z', started_at: '2026-08-04T09:00:01Z',
  completed_at: '2026-08-04T09:05:00Z',
  pages: [{
    id: 'page-1', requested_url: 'https://example.com/',
    final_url: 'https://example.com/', status_code: 200, title: 'Example',
    meta_description: 'Example page', h1_count: 1, html_lang: 'en',
    issues: [
      { code: 'missing_canonical', severity: 'error', message: 'Canonical link is missing.', details: {} },
      { code: 'short_title', severity: 'warning', message: 'Title is too short.', details: {} },
    ],
    schemas: [{ type: 'Organization', syntax_valid: true, structure_status: 'checked fields valid', details: {} }],
  }],
}

const PROJECT: SeoProjectDetail = {
  id: 'project-1', name: 'Example', domain: 'https://example.com/',
  created_at: '2026-08-04T09:00:00Z', updated_at: '2026-08-04T09:05:00Z',
  latest_audit: AUDIT, audits: [AUDIT],
}

describe('SiteAuditProjectDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue({ status: 'authenticated', user: null })
    mockedGetSeoProject.mockResolvedValue(PROJECT)
    mockedGetSiteAudit.mockResolvedValue(AUDIT)
    mockedStartSiteAudit.mockResolvedValue({ ...AUDIT, id: 'audit-2', status: 'queued' })
  })

  it('re-runs the crawl with the settings the last run used', async () => {
    const user = userEvent.setup()
    render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 })

    await user.click(screen.getByRole('button', { name: 'Run audit again' }))

    // Prefilled from the completed run, not reset to the create-flow defaults.
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(/limit per audit/i)).toHaveValue(10)
    expect(within(dialog).getByRole('radio', { name: /mobile crawler/i })).toBeChecked()

    await user.click(within(dialog).getByRole('button', { name: /start audit/i }))

    expect(mockedStartSiteAudit).toHaveBeenCalledWith('project-1', {
      page_limit: 10,
      profile_id: 'site_audit_mobile',
      js_rendering: true,
    })
    // The queued run has to come from a refetch, or the poller never follows it.
    await waitFor(() => expect(mockedGetSeoProject).toHaveBeenCalledTimes(2))
  })

  it('will not queue a second run while one is already in flight', async () => {
    const running: SiteAuditDetail = { ...AUDIT, status: 'running', progress: 40 }
    mockedGetSeoProject.mockResolvedValue({ ...PROJECT, latest_audit: running })
    mockedGetSiteAudit.mockResolvedValue(running)
    render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 })

    expect(screen.getByRole('button', { name: 'Audit in progress' })).toBeDisabled()
    expect(mockedStartSiteAudit).not.toHaveBeenCalled()
  })

  it('withdraws the button when the deployment has crawling switched off', async () => {
    const user = userEvent.setup()
    mockedStartSiteAudit.mockRejectedValueOnce(new MockApiError('Not Found', 404))
    render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 })

    await user.click(screen.getByRole('button', { name: 'Run audit again' }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: /start audit/i,
      }),
    )

    expect(await screen.findByRole('status')).toHaveTextContent(/turned off/i)
    expect(screen.queryByRole('button', { name: /run audit/i })).not.toBeInTheDocument()
  })

  it('keeps the dialog open and explains a refused duplicate run', async () => {
    const user = userEvent.setup()
    mockedStartSiteAudit.mockRejectedValueOnce(
      new MockApiError('This project already has an audit queued or running.', 409),
    )
    render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 })

    await user.click(screen.getByRole('button', { name: 'Run audit again' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /start audit/i }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      /already has an audit queued or running/i,
    )
  })

  it('loads the project and renders only backend audit values', async () => {
    render(<SiteAuditProjectDetail />)

    expect(
      await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Site health 78%' })).toBeInTheDocument()
    expect(screen.getByText('Pages crawled: 1/10')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Crawled pages' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Findings by severity' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Top issues' })).toBeInTheDocument()
    expect(screen.getByText('Canonical link is missing.')).toBeInTheDocument()
    expect(mockedGetSeoProject).toHaveBeenCalledWith('project-1', expect.any(AbortSignal))
    expect(mockedGetSiteAudit).toHaveBeenCalledWith('project-1', 'audit-1', expect.any(AbortSignal))
  })

  it('switches between issue, page, and schema tabs', async () => {
    const user = userEvent.setup()
    render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 })

    await user.click(screen.getByRole('tab', { name: 'Issues' }))
    expect(screen.getByRole('heading', { name: 'All issues' })).toBeInTheDocument()
    expect(screen.getByText(/2 issue types and 2 findings across 1 crawled pages/i)).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Crawled pages' }))
    expect(screen.getByRole('table', { name: /pages crawled in this audit/i })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Schema markup' }))
    expect(screen.getByText('Organization')).toBeInTheDocument()
    expect(screen.getAllByText('Checks passed')).toHaveLength(2)
  })

  it('shows a retryable project load error', async () => {
    const user = userEvent.setup()
    mockedGetSeoProject.mockRejectedValueOnce(new Error('The server is offline.'))
    render(<SiteAuditProjectDetail />)

    expect(await screen.findByRole('alert')).toHaveTextContent('The server is offline.')
    await user.click(screen.getByRole('button', { name: /try again/i }))
    expect(
      await screen.findByRole('heading', { name: 'Site Audit: Example', level: 1 }),
    ).toBeInTheDocument()
  })
})
