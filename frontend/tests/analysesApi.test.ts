import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createAnalysis, getAnalysis } from '@/lib/api'
import { setAccessToken } from '@/lib/session'

function jsonResponse(body: unknown, status: number, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

describe('Analyses API', () => {
  afterEach(() => {
    setAccessToken(null)
    vi.unstubAllGlobals()
  })

  describe('createAnalysis', () => {
    beforeEach(() => {
      setAccessToken('analysis-token')
    })

    it('sends the bearer, because a submitted run now belongs to an organization', async () => {
      // It used to be a bare `fetch`. The form sat behind sign-in while the
      // request it sent carried no credential, so every run a customer started
      // was attributed to nobody.
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse({ id: 'analysis-1' }, 202))
      vi.stubGlobal('fetch', fetchMock)

      await expect(createAnalysis('https://example.com')).resolves.toEqual({
        id: 'analysis-1',
      })

      const [path, init] = fetchMock.mock.calls[0]
      expect(path).toBe('/api/v1/analyses')
      expect(new Headers(init.headers).get('Authorization')).toBe('Bearer analysis-token')
    })

    it('passes a plan refusal through verbatim instead of calling it a rate limit', async () => {
      // Both limits answer 429 and they ask for opposite things. "Wait a
      // moment" is wrong advice for an allowance that resets next month.
      const detail = 'your plan allows 5 analyses and 5 have been used'
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse({ detail, metric: 'analyses', used: 5, limit: 5 }, 429),
        ),
      )

      await expect(createAnalysis('https://example.com')).rejects.toMatchObject({
        message: detail,
        status: 429,
      })
    })

    it('rewrites the burst limiter’s terse 429 into something a person can act on', async () => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValue(jsonResponse({ detail: 'rate limit exceeded' }, 429)),
      )

      await expect(createAnalysis('https://example.com')).rejects.toMatchObject({
        message: expect.stringContaining('short time'),
        status: 429,
      })
    })

    it('explains an expired session rather than surfacing a raw 401', async () => {
      // Two 401s: the first triggers a refresh attempt, the second ends it.
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(jsonResponse({ detail: 'invalid token' }, 401)),
      )

      await expect(createAnalysis('https://example.com')).rejects.toMatchObject({
        message: expect.stringContaining('Sign in again'),
        status: 401,
      })
    })

    it('names the role problem on a 403, since retrying will not fix it', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(jsonResponse({ detail: 'no permission' }, 403)),
      )

      await expect(createAnalysis('https://example.com')).rejects.toMatchObject({
        message: expect.stringContaining('role'),
        status: 403,
      })
    })

    it('keeps the friendly copy for a malformed URL', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(jsonResponse({ detail: [{ msg: 'bad url' }] }, 422)),
      )

      await expect(createAnalysis('nonsense')).rejects.toBeInstanceOf(ApiError)
    })
  })

  describe('getAnalysis', () => {
    it('carries the bearer so the submitter can read their own run', async () => {
      // An org-owned analysis is served only to that org. Polling without the
      // token would 404 the person who just started it.
      setAccessToken('reader-token')
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse({ id: 'analysis-1' }, 200))
      vi.stubGlobal('fetch', fetchMock)

      await getAnalysis('analysis-1')

      const [, init] = fetchMock.mock.calls[0]
      expect(new Headers(init.headers).get('Authorization')).toBe('Bearer reader-token')
    })

    it('still reads an organization-less analysis with no credential at all', async () => {
      // Checker results and every pre-P7.6 row are capability URLs.
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse({ id: 'public-1' }, 200))
      vi.stubGlobal('fetch', fetchMock)

      await getAnalysis('public-1')

      const [, init] = fetchMock.mock.calls[0]
      expect(new Headers(init.headers).get('Authorization')).toBeNull()
    })
  })
})
