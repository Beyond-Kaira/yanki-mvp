import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'
import { axeCheck } from './a11y'

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedGetSeoProject = vi.hoisted(() => vi.fn())
const mockedGetSiteAudit = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({ useParams: () => ({ projectId: 'project-1' }) }))
vi.mock('@/components/AuthProvider', () => ({ useAuth: mockedUseAuth }))
vi.mock('@/lib/api', () => ({ getSeoProject: mockedGetSeoProject, getSiteAudit: mockedGetSiteAudit }))

import SiteAuditProjectDetail from '@/components/site-audit/detail/SiteAuditProjectDetail'

const AUDIT: SiteAuditDetail = {
  id: 'audit-1', project_id: 'project-1', status: 'done', progress: 100,
  current_step: null, page_limit: 10, profile_id: 'site_audit_mobile', js_rendering: true,
  pages_discovered: 0, pages_crawled: 0, total_errors: 0, total_warnings: 0,
  total_notices: 0, health_score: null, error: null,
  created_at: '2026-08-04T09:00:00Z', updated_at: '2026-08-04T09:05:00Z',
  started_at: '2026-08-04T09:00:01Z', completed_at: '2026-08-04T09:05:00Z', pages: [],
}
const PROJECT: SeoProjectDetail = {
  id: 'project-1', name: 'Example', domain: 'https://example.com/',
  created_at: AUDIT.created_at, updated_at: AUDIT.updated_at,
  latest_audit: AUDIT, audits: [AUDIT],
}

describe('SiteAuditProjectDetail accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue({ status: 'authenticated', user: null })
    mockedGetSeoProject.mockResolvedValue(PROJECT)
    mockedGetSiteAudit.mockResolvedValue(AUDIT)
  })

  it('has no axe violations in the project overview', async () => {
    const { container } = render(<SiteAuditProjectDetail />)
    await screen.findByRole('heading', { name: 'Example', level: 1 })
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
