// Auth API surface, written against `backend/app/api/auth_routes.py` and the
// schemas beside it (landed in #9). Request and response types come from the
// generated contract via `lib/contracts.ts`, so a schema change reaches these
// call sites as a type error rather than a runtime surprise.
//
// Shape of the flow there, since it drives everything here:
//   signup   201, returns the user and NOTHING else. It does not sign anyone in,
//            so the caller has to log in afterwards to get a session.
//   login    200, returns { user, access_token } AND sets an httpOnly refresh
//            cookie scoped to /api/v1/auth.
//   refresh  200, rotates that cookie for a new access token (see lib/session.ts,
//            which owns it to keep this module out of an import cycle).
//   me       200, needs `Authorization: Bearer`, returns the user.
//   logout   204, clears the cookie server-side.
//
// TODO(auth): still missing on the backend, so the page for it cannot work yet:
//   a password-reset request endpoint. `requestPasswordReset` below posts to the
//   path this app assumes; until it exists the call fails and the form says so.

import { ApiError, authorizedFetch, readErrorMessage } from './api'
import type { AuthUser, Credentials, LoginResponse } from './contracts'
import { setAccessToken } from './session'

export type { AuthUser, Credentials }

export interface Session {
  user: AuthUser
  accessToken: string
}

const LOGIN_PATH = '/api/v1/auth/login'
const SIGNUP_PATH = '/api/v1/auth/signup'
const LOGOUT_PATH = '/api/v1/auth/logout'
const ME_PATH = '/api/v1/auth/me'
// Assumed. No endpoint answers this yet.
const PASSWORD_RESET_PATH = '/api/v1/auth/password-reset'

// A request that never reaches the API rejects with a bare TypeError ("Failed
// to fetch"), which is not a sentence to put in front of someone signing in.
// Status 0 marks "no response at all", distinct from any HTTP status.
async function postJson(path: string, body?: unknown): Promise<Response> {
  try {
    return await fetch(path, {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }
}

// A 5xx is our fault and its status number tells the reader nothing they can act
// on; anything else falls through to the API's own message, which for a 4xx is
// usually the specific reason.
async function failureMessage(res: Response): Promise<string> {
  if (res.status === 429) {
    // Rate limiting is a wait, not a mistake to correct, so say so instead of
    // passing on a limiter's technical wording.
    return 'Too many attempts. Wait a few minutes and try again.'
  }
  if (res.status >= 500) {
    return 'Something went wrong on our side. Try again in a moment.'
  }
  return readErrorMessage(res)
}

export async function login(credentials: Credentials): Promise<Session> {
  const res = await postJson(LOGIN_PATH, credentials)
  if (!res.ok) {
    const message =
      res.status === 401
        ? 'That email and password do not match an account.'
        : res.status === 503
          ? 'Sign-in is unavailable right now. Try again shortly.'
          : await failureMessage(res)
    throw new ApiError(message, res.status)
  }

  const body = (await res.json()) as LoginResponse
  setAccessToken(body.access_token)
  return { user: body.user, accessToken: body.access_token }
}

// Creates the account only. The endpoint returns no token and sets no cookie, so
// the caller is still anonymous when this resolves.
export async function signup(credentials: Credentials): Promise<AuthUser> {
  const res = await postJson(SIGNUP_PATH, credentials)
  if (!res.ok) {
    const message =
      res.status === 409
        ? 'An account with that email already exists.'
        : await failureMessage(res)
    throw new ApiError(message, res.status)
  }
  return (await res.json()) as AuthUser
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const res = await authorizedFetch(ME_PATH)
  // 401 after `authorizedFetch` already tried a refresh means no session.
  if (res.status === 401) return null
  if (!res.ok) throw new ApiError(await failureMessage(res), res.status)
  return (await res.json()) as AuthUser
}

// Clears the cookie server-side and the token here. Signing out is a local act
// as much as a remote one: a request that fails still leaves the person signed
// out on this device, so the failure is swallowed rather than handed back to a
// caller who has nothing useful to do with it.
export async function logout(): Promise<void> {
  try {
    await postJson(LOGOUT_PATH)
  } catch {
    // Offline, or the API is down. The token is dropped below either way.
  } finally {
    setAccessToken(null)
  }
}

// Sign-up is two requests: create the account, then spend the same credentials
// on a session. When the first succeeds and the second does not, the account
// EXISTS, and telling the person it could not be created sends them back to a
// form that will now answer 409. This distinguishes the two.
export class SignedUpButNotSignedInError extends Error {
  constructor(cause: string) {
    super(cause)
    this.name = 'SignedUpButNotSignedInError'
  }
}

// No 404 branch on purpose: whether an address has an account is not something
// this endpoint should reveal, so an unknown email has to look exactly like a
// known one from here. That only holds if the backend answers the same way for
// both, which is worth confirming when the endpoint is written.
export async function requestPasswordReset(email: string): Promise<void> {
  const res = await postJson(PASSWORD_RESET_PATH, { email })
  if (!res.ok) {
    throw new ApiError(await failureMessage(res), res.status)
  }
}
