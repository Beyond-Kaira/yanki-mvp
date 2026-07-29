import { describe, it, expect, vi, afterEach } from 'vitest'
import { login, signup } from '@/lib/auth'
import { ApiError } from '@/lib/api'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('login', () => {
  it('posts the credentials to the auth endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await login({ email: 'ada@example.com', password: 'hunter2!', remember: true })

    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({
      email: 'ada@example.com',
      password: 'hunter2!',
      remember: true,
    })
  })

  it('names the reason on a rejected credential rather than the status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})))

    await expect(
      login({ email: 'ada@example.com', password: 'wrong', remember: false }),
    ).rejects.toThrow(/do not match an account/i)
  })

  it('does not put a 5xx status number in front of the reader', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(500, {})))

    await expect(
      login({ email: 'ada@example.com', password: 'hunter2!', remember: false }),
    ).rejects.toThrow(/something went wrong on our side/i)
  })

  it('turns a request that never lands into a sentence', async () => {
    // What the browser throws when the request cannot be made at all.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const failure = await login({
      email: 'ada@example.com',
      password: 'hunter2!',
      remember: false,
    }).catch((err: unknown) => err)

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).message).toMatch(/couldn't reach the server/i)
    // Status 0 marks "no response", which is not any HTTP status.
    expect((failure as ApiError).status).toBe(0)
  })
})

describe('signup', () => {
  it('posts the account details to the auth endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)

    await signup({
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      password: 'hunter2!pass',
    })

    const [path, init] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/auth/signup')
    expect(JSON.parse(init.body)).toEqual({
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      password: 'hunter2!pass',
    })
  })

  it('says the email is taken instead of reporting a conflict code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, {})))

    await expect(
      signup({ name: 'Ada', email: 'ada@example.com', password: 'hunter2!pass' }),
    ).rejects.toThrow(/already exists/i)
  })

  it('passes a validation message from the API straight through', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'Password is too common.' })),
    )

    await expect(
      signup({ name: 'Ada', email: 'ada@example.com', password: 'password' }),
    ).rejects.toThrow('Password is too common.')
  })
})
