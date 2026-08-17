import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  AccountLinkRequiredError,
  fetchCurrentUser,
  login,
  logout,
  requestPasswordReset,
  signInWithProvider,
  signup,
} from '@/lib/auth'
import { ApiError } from '@/lib/api'
import { getAccessToken, setAccessToken } from '@/lib/session'

const USER = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'ada@example.com',
  created_at: '2026-07-29T00:00:00Z',
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

describe('login', () => {
  it('posts only the fields the endpoint accepts', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { user: USER, access_token: 'tok' }))
    vi.stubGlobal('fetch', fetchMock)

    await login({ email: 'ada@example.com', password: 'hunter2!' })

    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/auth/login')
    // LoginRequest is {email, password}. Anything else would be swallowed
    // server-side, which is worse than being rejected.
    expect(JSON.parse(init.body)).toEqual({
      email: 'ada@example.com',
      password: 'hunter2!',
    })
  })

  it('keeps the returned bearer token instead of discarding the body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { user: USER, access_token: 'tok' })),
    )

    const session = await login({ email: 'ada@example.com', password: 'hunter2!' })

    expect(session.user).toEqual(USER)
    expect(session.accessToken).toBe('tok')
    // Without this the sign-in succeeds and authorises nothing.
    expect(getAccessToken()).toBe('tok')
  })

  it('names the reason on a rejected credential rather than the status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})))

    await expect(
      login({ email: 'ada@example.com', password: 'wrong' }),
    ).rejects.toThrow(/do not match an account/i)
  })

  it('explains a 503 from the token service without the number', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(503, {})))

    await expect(
      login({ email: 'ada@example.com', password: 'hunter2!' }),
    ).rejects.toThrow(/unavailable right now/i)
  })

  it('turns a request that never lands into a sentence', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const failure = await login({
      email: 'ada@example.com',
      password: 'hunter2!',
    }).catch((err: unknown) => err)

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).message).toMatch(/couldn't reach the server/i)
    expect((failure as ApiError).status).toBe(0)
  })
})

describe('signup', () => {
  it('posts the credentials and returns the created user', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, USER))
    vi.stubGlobal('fetch', fetchMock)

    const user = await signup({ email: 'ada@example.com', password: 'hunter2!pass' })

    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/auth/signup')
    expect(JSON.parse(init.body)).toEqual({
      email: 'ada@example.com',
      password: 'hunter2!pass',
    })
    expect(user).toEqual(USER)
  })

  it('leaves the caller anonymous, because the endpoint issues no session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(201, USER)))

    await signup({ email: 'ada@example.com', password: 'hunter2!pass' })

    expect(getAccessToken()).toBeNull()
  })

  it('says the email is taken instead of reporting a conflict code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, {})))

    await expect(
      signup({ email: 'ada@example.com', password: 'hunter2!pass' }),
    ).rejects.toThrow(/already exists/i)
  })
})

describe('provider account linking', () => {
  it('turns the password precondition into a distinct UI signal', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(428, {
          detail: 'current password required to connect this sign-in method',
        }),
      ),
    )

    await expect(
      signInWithProvider({ provider: 'google', id_token: 'google-token' }),
    ).rejects.toBeInstanceOf(AccountLinkRequiredError)
  })

  it('explains a rejected linking password specifically', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})))

    await expect(
      signInWithProvider({
        provider: 'google',
        id_token: 'google-token',
        password: 'wrong-password',
      }),
    ).rejects.toThrow(/password is incorrect/i)
  })
})

describe('fetchCurrentUser', () => {
  it('sends the bearer token it holds', async () => {
    setAccessToken('tok')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, USER))
    vi.stubGlobal('fetch', fetchMock)

    await fetchCurrentUser()

    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/auth/me')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok')
  })

  it('reports no session rather than throwing when the token is spent', async () => {
    setAccessToken('stale')
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        // /me rejects the stale token, the refresh has no cookie to rotate, so
        // the replay is never reached and this is simply anonymous.
        .mockResolvedValueOnce(jsonResponse(401, {}))
        .mockResolvedValueOnce(jsonResponse(401, {})),
    )

    await expect(fetchCurrentUser()).resolves.toBeNull()
  })

  it('replays the request with the token the refresh just earned', async () => {
    setAccessToken('stale')
    const fetchMock = vi
      .fn()
      // The bearer has expired, which is the expected end of a short-lived
      // token rather than an error to surface…
      .mockResolvedValueOnce(jsonResponse(401, {}))
      // …so the cookie is rotated for a new one…
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'fresh' }))
      // …and the original request runs again, this time carrying it.
      .mockResolvedValueOnce(jsonResponse(200, USER))
    vi.stubGlobal('fetch', fetchMock)

    // Dropping the replay leaves this null: the session is alive and the user
    // is signed out anyway, which is the whole failure this covers.
    await expect(fetchCurrentUser()).resolves.toEqual(USER)

    expect(fetchMock).toHaveBeenCalledTimes(3)
    const [refreshPath] = fetchMock.mock.calls[1]
    expect(refreshPath).toBe('/api/v1/auth/refresh')
    const [replayPath, replayInit] = fetchMock.mock.calls[2]
    expect(replayPath).toBe('/api/v1/auth/me')
    expect(new Headers(replayInit.headers).get('Authorization')).toBe(
      'Bearer fresh',
    )
  })
})

describe('logout', () => {
  it('drops the local token and does not fail when the request cannot be sent', async () => {
    setAccessToken('tok')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    // Signing out is local as much as remote: an unreachable API is no reason to
    // hand the caller an error, or to keep the token.
    await expect(logout()).resolves.toBeUndefined()
    expect(getAccessToken()).toBeNull()
  })

  it('drops the local token when the server rejects the call', async () => {
    setAccessToken('tok')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(500, {})))

    await expect(logout()).resolves.toBeUndefined()
    expect(getAccessToken()).toBeNull()
  })
})

// No screen reaches this yet — the backend has no password-reset endpoint, so
// the route and the link to it are not shipped. The client stays because it is
// the contract the endpoint is expected to meet, and these hold it to that.
describe('requestPasswordReset', () => {
  it('posts the email alone to the path the app assumes', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(requestPasswordReset('ada@example.com')).resolves.toBeUndefined()

    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/auth/password-reset')
    expect(JSON.parse(init.body)).toEqual({ email: 'ada@example.com' })
  })

  it('rejects rather than reporting success while the endpoint is missing', async () => {
    // What the backend answers today: the route is not registered, so FastAPI
    // returns 404. Resolving on that would tell someone a mail was sent.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(404, { detail: 'Not Found' })),
    )

    await expect(requestPasswordReset('ada@example.com')).rejects.toBeInstanceOf(
      ApiError,
    )
  })
})
