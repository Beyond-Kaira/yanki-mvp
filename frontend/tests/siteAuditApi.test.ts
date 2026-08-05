import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  createSeoProject,
  getSeoProject,
  getSiteAudit,
  listSeoProjects,
} from '@/lib/api'
import type { SeoProject, SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'
import { setAccessToken } from '@/lib/session'

const PROJECT: SeoProject = {
  id: '4bb0f6e1-d873-47ce-b15a-d166c43f91f8',
  name: 'Dream Games',
  domain: 'https://www.dreamgames.com/',
  created_at: '2026-08-04T09:00:00Z',
  updated_at: '2026-08-04T10:30:00Z',
  latest_audit: null,
}

const PROJECT_DETAIL: SeoProjectDetail = { ...PROJECT, audits: [] }

const AUDIT_DETAIL: SiteAuditDetail = {
  id: 'audit-1',
  project_id: PROJECT.id,
  status: 'done',
  progress: 100,
  current_step: null,
  page_limit: 10,
  profile_id: 'site_audit_mobile',
  js_rendering: true,
  pages_discovered: 1,
  pages_crawled: 1,
  total_errors: 0,
  total_warnings: 0,
  total_notices: 0,
  health_score: 100,
  error: null,
  created_at: PROJECT.created_at,
  updated_at: PROJECT.updated_at,
  started_at: PROJECT.created_at,
  completed_at: PROJECT.updated_at,
  pages: [],
}

describe('Site Audit API', () => {
  beforeEach(() => {
    setAccessToken('site-audit-token')
  })

  afterEach(() => {
    setAccessToken(null)
    vi.unstubAllGlobals()
  })

  it('lists SEO projects through the authenticated API client', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([PROJECT]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(listSeoProjects()).resolves.toEqual([PROJECT])

    expect(fetchMock).toHaveBeenCalledOnce()
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/api/v1/seo-projects')
    expect(init.cache).toBe('no-store')
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).get('Authorization')).toBe(
      'Bearer site-audit-token',
    )
  })

  it('turns a network rejection into a user-facing ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const request = listSeoProjects()
    await expect(request).rejects.toThrow(/couldn't reach the server/i)
    await expect(request).rejects.toMatchObject({ status: 0 } satisfies Partial<ApiError>)
  })

  it('creates an SEO project through the authenticated API client', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(PROJECT), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const input = {
      domain: 'dreamgames.com',
      name: null,
      page_limit: 10,
      profile_id: 'site_audit_mobile' as const,
      js_rendering: true,
    }

    await expect(createSeoProject(input)).resolves.toEqual(PROJECT)

    expect(fetchMock).toHaveBeenCalledOnce()
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/api/v1/seo-projects')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).get('Authorization')).toBe(
      'Bearer site-audit-token',
    )
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual(input)
  })

  it('loads an account-owned project and audit detail', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(PROJECT_DETAIL), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(AUDIT_DETAIL), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getSeoProject(PROJECT.id)).resolves.toEqual(PROJECT_DETAIL)
    await expect(getSiteAudit(PROJECT.id, AUDIT_DETAIL.id)).resolves.toEqual(
      AUDIT_DETAIL,
    )

    expect(fetchMock.mock.calls[0][0]).toBe(`/api/v1/seo-projects/${PROJECT.id}`)
    expect(fetchMock.mock.calls[1][0]).toBe(
      `/api/v1/seo-projects/${PROJECT.id}/audits/${AUDIT_DETAIL.id}`,
    )
    for (const [, init] of fetchMock.mock.calls as [string, RequestInit][]) {
      expect(new Headers(init.headers).get('Authorization')).toBe(
        'Bearer site-audit-token',
      )
    }
  })
})
