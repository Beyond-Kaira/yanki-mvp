// Auth API surface for the sign-in and sign-up screens.
//
// THESE ENDPOINTS DO NOT EXIST YET. The backend work is in progress on
// `feat/auth-endpoints`, whose session note reads: "Working on email/password
// signup and login endpoints. The JWT flow will be handled in a separate task."
//
// Nothing here fakes a success or mints a token. Each call posts what the form
// collected and lets the backend decide; until the routes land, a submit fails
// with the API's own error, which is the honest behaviour. Wiring this up later
// should be a matter of confirming the items below, not rewriting the screens.
//
// TODO(auth): confirm against the backend before this ships —
//   1. Paths. Assumed `/api/v1/auth/login` and `/api/v1/auth/signup` to match
//      the `/api/v1` prefix every existing route uses.
//   2. Sign-up field name for the person's name: `name` or `full_name`.
//   3. How the session comes back: a JSON token this layer must return and
//      store, or a `Set-Cookie` the browser keeps on its own. Both calls
//      currently return void, which assumes the cookie shape; a token shape
//      means changing the return type here and handling it at the call sites.
//   4. Whether `remember` is sent at all, or only changes token lifetime
//      server-side. It is included in the login body for now.
//   5. Error codes worth a specific message: 401 for bad credentials, 409 for
//      an email already registered.

import { ApiError, readErrorMessage } from './api'

export interface LoginRequest {
  email: string
  password: string
  remember: boolean
}

export interface SignupRequest {
  name: string
  email: string
  password: string
}

// Paths are relative like every other call: Next rewrites proxy them to the
// backend (see next.config.ts), so there is no base URL and no CORS.
const LOGIN_PATH = '/api/v1/auth/login'
const SIGNUP_PATH = '/api/v1/auth/signup'

// `credentials: 'same-origin'` is the browser default for same-origin requests
// and is spelled out so a cookie-based session works without a later edit.
//
// A request that never reaches the API rejects with a bare TypeError ("Failed
// to fetch"), which is not a sentence to put in front of someone trying to sign
// in. Status 0 marks "no response at all", distinct from any HTTP status.
async function postJson(path: string, body: unknown): Promise<Response> {
  try {
    return await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }
}

// A 5xx is our fault and its status number tells the reader nothing they can
// act on; anything else falls through to the API's own message, which for a
// 4xx is usually the specific reason.
async function failureMessage(res: Response): Promise<string> {
  if (res.status >= 500) {
    return 'Something went wrong on our side. Try again in a moment.'
  }
  return readErrorMessage(res)
}

export async function login(payload: LoginRequest): Promise<void> {
  const res = await postJson(LOGIN_PATH, payload)
  if (!res.ok) {
    const message =
      res.status === 401
        ? 'That email and password do not match an account.'
        : await failureMessage(res)
    throw new ApiError(message, res.status)
  }
}

export async function signup(payload: SignupRequest): Promise<void> {
  const res = await postJson(SIGNUP_PATH, payload)
  if (!res.ok) {
    const message =
      res.status === 409
        ? 'An account with that email already exists.'
        : await failureMessage(res)
    throw new ApiError(message, res.status)
  }
}
