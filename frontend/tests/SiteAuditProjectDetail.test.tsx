import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedGetSeoProject = vi.hoisted(() => vi.fn())
const mockedGetSiteAudit = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useParams: () => ({ projectId: 'project-1' }),
}))
vi.mock('@/components/AuthProvider', () => ({ useAuth: mockedUseAuth }))
vi.mock('@/lib/api', () => ({
  getSeoProject: mockedGetSeoProject,
  getSiteAudit: mockedGetSiteAudit,
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
  })

  it('loads the project and renders only backend audit values', async () => {
    render(<SiteAuditProjectDetail />)

    expect(await screen.findByRole('heading', { name: 'Example', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Site health 78%' })).toBeInTheDocument()
    expect(screen.getByText('1 unique page result · limit 10')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Crawled page results' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Findings by severity' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Top issues' })).toBeInTheDocument()
    expect(screen.getByText('Canonical link is missing.')).toBeInTheDocument()
    expect(mockedGetSeoProject).toHaveBeenCalledWith('project-1', expect.any(AbortSignal))
    expect(mockedGetSiteAudit).toHaveBeenCalledWith('project-1', 'audit-1', expect.any(AbortSignal))
  })

  it('switches between issue, page, and schema tabs', async () => {
    const user = userEvent.setup()
    render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Example', level: 1 })

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
    expect(await screen.findByRole('heading', { name: 'Example', level: 1 })).toBeInTheDocument()
  })

  it('does not request private results for an anonymous visitor', () => {
    mockedUseAuth.mockReturnValue({ status: 'anonymous', user: null })
    render(<SiteAuditProjectDetail />)
    expect(screen.getByRole('heading', { name: /sign in to view this site audit/i })).toBeInTheDocument()
    expect(mockedGetSeoProject).not.toHaveBeenCalled()
  })
})
