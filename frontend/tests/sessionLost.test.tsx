import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AuthProvider, { useAuth } from '@/components/AuthProvider'
import { authorizedFetch } from '@/lib/api'
import { getAccessToken, notifySessionLost, onSessionLost, setAccessToken } from '@/lib/session'

vi.mock('@/lib/auth', async () => {
  const actual = await vi.importActual<typeof import('@/lib/auth')>('@/lib/auth')
  return {
    ...actual,
    fetchCurrentUser: vi.fn().mockResolvedValue({
      id: 'u1',
      email: 'someone@example.com',
      status: 'active',
      organization: null,
      role: null,
      permissions: [],
    }),
  }
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  setAccessToken(null)
})

describe('onSessionLost', () => {
  it('hands the notification to every listener and stops after unsubscribe', () => {
    const first = vi.fn()
    const second = vi.fn()
    const unsubscribe = onSessionLost(first)
    onSessionLost(second)

    notifySessionLost()
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)

    unsubscribe()
    notifySessionLost()
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(2)
  })
})

describe('authorizedFetch when the session is over', () => {
  beforeEach(() => {
    setAccessToken('stale-token')
  })

  it('announces the loss when a 401 survives the refresh', async () => {
    const heard = vi.fn()
    const unsubscribe = onSessionLost(heard)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        // The refresh is what decides: a cookie the server will not honour any
        // more answers 401, so there is no new token to replay the call with.
        if (String(input).includes('/auth/refresh')) return new Response(null, { status: 401 })
        return new Response(null, { status: 401 })
      }),
    )

    const res = await authorizedFetch('/api/v1/seo/projects')

    expect(res.status).toBe(401)
    expect(heard).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it('stays quiet when the refresh rescues the request', async () => {
    // The common case, and the one that must NOT sign anybody out: access
    // tokens are short-lived by design, so an expired one is routine.
    const heard = vi.fn()
    const unsubscribe = onSessionLost(heard)
    let seenBearer = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).includes('/auth/refresh')) {
          return new Response(JSON.stringify({ access_token: 'fresh' }), { status: 200 })
        }
        const auth = new Headers(init?.headers).get('Authorization')
        if (auth === 'Bearer fresh') {
          seenBearer += 1
          return new Response(null, { status: 200 })
        }
        return new Response(null, { status: 401 })
      }),
    )

    const res = await authorizedFetch('/api/v1/seo/projects')

    expect(res.status).toBe(200)
    expect(seenBearer).toBe(1)
    expect(heard).not.toHaveBeenCalled()
    unsubscribe()
  })
})

function AuthProbe() {
  const { status } = useAuth()
  return <p>status: {status}</p>
}

describe('AuthProvider reacting to a lost session', () => {
  it('drops to anonymous and clears the token', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ access_token: 'tok' }), { status: 200 }),
      ),
    )

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )

    await waitFor(() =>
      expect(screen.getByText(/status: authenticated/)).toBeInTheDocument(),
    )

    notifySessionLost()

    await waitFor(() =>
      expect(screen.getByText(/status: anonymous/)).toBeInTheDocument(),
    )
    expect(getAccessToken()).toBeNull()
  })
})
