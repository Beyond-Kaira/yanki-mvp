import { describe, it, expect, vi, afterEach } from 'vitest'
import { getAccessToken, refreshAccessToken, setAccessToken } from '@/lib/session'

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe('refreshAccessToken', () => {
  it('rotates the cookie for a bearer token and keeps it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ access_token: 'tok' }), { status: 200 }),
      ),
    )

    await expect(refreshAccessToken()).resolves.toBe('tok')
    expect(getAccessToken()).toBe('tok')
  })

  it('shares one attempt between concurrent callers', async () => {
    // Rotation is single-use and the backend revokes the whole session family
    // when a consumed token is replayed, so a second parallel refresh would
    // sign the person out. One request, one rotation.
    const gate = deferred<Response>()
    const fetchMock = vi.fn().mockReturnValue(gate.promise)
    vi.stubGlobal('fetch', fetchMock)

    const first = refreshAccessToken()
    const second = refreshAccessToken()
    gate.resolve(
      new Response(JSON.stringify({ access_token: 'tok' }), { status: 200 }),
    )

    expect(await first).toBe('tok')
    expect(await second).toBe('tok')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('starts a new attempt once the previous one has settled', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ access_token: 'tok' }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await refreshAccessToken()
    await refreshAccessToken()

    // Sharing must not turn into caching: a later refresh has to actually run.
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('reports no session and clears the token when the cookie is spent', async () => {
    setAccessToken('stale')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))

    await expect(refreshAccessToken()).resolves.toBeNull()
    expect(getAccessToken()).toBeNull()
  })

  it('treats an unreachable API as no session rather than throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(refreshAccessToken()).resolves.toBeNull()
  })
})
