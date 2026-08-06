import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  getSearchConsolePerformance,
  linkSearchConsoleProperty,
  listSearchConsoleConnections,
  listSearchConsoleProperties,
  startSearchConsoleConnect,
  unlinkSearchConsoleProperty,
} from '@/lib/api'
import { setAccessToken } from '@/lib/session'

const PROJECT_ID = '4bb0f6e1-d873-47ce-b15a-d166c43f91f8'
const CONNECTION_ID = '9f1b0f26-1c2b-4f3a-9c1d-2b3c4d5e6f70'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('Search Console API client', () => {
  beforeEach(() => {
    setAccessToken('gsc-token')
  })

  afterEach(() => {
    setAccessToken(null)
    vi.unstubAllGlobals()
  })

  it('starts a connection and returns only the authorization url', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ authorization_url: 'https://accounts.google.test/x' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(startSearchConsoleConnect(PROJECT_ID)).resolves.toEqual({
      authorization_url: 'https://accounts.google.test/x',
    })

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe(`/api/v1/seo-projects/${PROJECT_ID}/search-console/connect`)
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer gsc-token')
  })

  it('lists connections without caching', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ project_status: 'no_connection', connections: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await listSearchConsoleConnections(PROJECT_ID)

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe(`/api/v1/seo-projects/${PROJECT_ID}/search-console/connections`)
    expect(init.cache).toBe('no-store')
  })

  it('encodes both ids into the properties path', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ google_connection_id: CONNECTION_ID, google_account_email: 'a@b.test', properties: [] }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await listSearchConsoleProperties(PROJECT_ID, CONNECTION_ID)

    const [path] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe(
      `/api/v1/seo-projects/${PROJECT_ID}/search-console/connections/${CONNECTION_ID}/properties`,
    )
  })

  it('sends the property link as JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ site_url: 'sc-domain:a.test' }))
    vi.stubGlobal('fetch', fetchMock)

    await linkSearchConsoleProperty(PROJECT_ID, {
      google_connection_id: CONNECTION_ID,
      site_url: 'sc-domain:a.test',
    })

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe(`/api/v1/seo-projects/${PROJECT_ID}/search-console/property`)
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({
      google_connection_id: CONNECTION_ID,
      site_url: 'sc-domain:a.test',
    })
  })

  it('treats a 204 unlink as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

    await expect(unlinkSearchConsoleProperty(PROJECT_ID)).resolves.toBeUndefined()
  })

  it('reads performance without caching', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data_state: 'no_data' }))
    vi.stubGlobal('fetch', fetchMock)

    await getSearchConsolePerformance(PROJECT_ID)

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe(`/api/v1/seo-projects/${PROJECT_ID}/search-console/performance`)
    expect(init.cache).toBe('no-store')
  })

  // --- The 409 vocabulary --------------------------------------------------

  it.each([
    ['reauth_required', /reconnect the account/i],
    ['no_property_selected', /choose a search console property/i],
    ['property_access_lost', /no longer has access/i],
    ['property_not_accessible', /not available to this google account/i],
  ])('turns the %s conflict into an actionable sentence', async (detail, expected) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail }, 409)))

    await expect(getSearchConsolePerformance(PROJECT_ID)).rejects.toThrow(expected)
  })

  it('passes an unfamiliar conflict through rather than inventing one', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'something_new' }, 409)),
    )

    await expect(getSearchConsolePerformance(PROJECT_ID)).rejects.toThrow('something_new')
  })

  it('reads a 404 as "the feature is off", not "we could not find it"', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Not Found' }, 404)))

    await expect(listSearchConsoleConnections(PROJECT_ID)).rejects.toThrow(
      /not available for this project/i,
    )
  })

  it.each([
    [429, /rate limiting/i],
    [502, /could not be reached/i],
    [503, /could not be reached/i],
  ])('explains a %s from the provider', async (status, expected) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'x' }, status)))

    await expect(listSearchConsoleProperties(PROJECT_ID, CONNECTION_ID)).rejects.toThrow(
      expected,
    )
  })

  it('turns a network rejection into a user-facing ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const request = startSearchConsoleConnect(PROJECT_ID)
    await expect(request).rejects.toThrow(/couldn't reach the server/i)
    await expect(request).rejects.toMatchObject({ status: 0 } satisfies Partial<ApiError>)
  })

  it('propagates an abort so a stale load can be discarded', async () => {
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))

    await expect(getSearchConsolePerformance(PROJECT_ID)).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
})
