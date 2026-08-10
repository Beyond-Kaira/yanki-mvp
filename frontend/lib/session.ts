// The access token, held in memory on the client only.
//
// Deliberately not localStorage or a readable cookie: the backend pairs a
// short-lived bearer token with an httpOnly refresh cookie (`set_refresh_cookie`
// in backend/app/api/auth_cookies.py) precisely so the bearer never has to be
// persisted somewhere a script could read it. A reload therefore starts with no
// token and earns one back from the cookie through `refreshAccessToken`.
//
// Module state rather than React state because `lib/api.ts` needs the token too,
// and it is a plain fetch layer with no access to context.

const REFRESH_PATH = '/api/v1/auth/refresh'

// Module state on the server is shared by every request that renders, so one
// visitor's token would become everyone's. This module is client-side by
// construction; the guard makes that structural instead of a convention, so a
// later import from a server component fails loudly rather than leaking.
const isBrowser = typeof window !== 'undefined'

let accessToken: string | null = null

export function getAccessToken(): string | null {
  if (!isBrowser) return null
  return accessToken
}

export function setAccessToken(token: string | null): void {
  if (!isBrowser) {
    throw new Error(
      'lib/session holds a per-user token and must not run on the server',
    )
  }
  accessToken = token
}

type SessionLostListener = () => void

const sessionLostListeners = new Set<SessionLostListener>()

export function onSessionLost(listener: SessionLostListener): () => void {
  sessionLostListeners.add(listener)
  return () => {
    sessionLostListeners.delete(listener)
  }
}

export function notifySessionLost(): void {
  for (const listener of sessionLostListeners) listener()
}

interface RefreshBody {
  access_token?: unknown
}

// Rotation is single-use and the backend revokes the whole session family when a
// consumed token is replayed (`RefreshTokenReuseDetectedError` in
// services/auth_sessions.py). Two requests refreshing at once would do exactly
// that and sign the person out, so concurrent callers share one attempt.
let inFlight: Promise<string | null> | null = null

// …but that promise only covers this tab, and the cookie belongs to all of
// them. Two tabs cold-loading together — a restored window, a restart, a
// duplicated tab — each rotate the same cookie value, and the second is a reuse
// of a token the first has already spent: the family is revoked and BOTH tabs
// are signed out. A Web Lock is held across every tab on the origin, so the
// second rotation waits and then rotates the successor rather than the corpse.
const REFRESH_LOCK = 'yanki:auth-refresh'

async function rotate(): Promise<string | null> {
  try {
    const res = await fetch(REFRESH_PATH, {
      method: 'POST',
      credentials: 'same-origin',
    })
    if (!res.ok) {
      accessToken = null
      return null
    }
    const body = (await res.json()) as RefreshBody
    if (typeof body.access_token !== 'string') {
      accessToken = null
      return null
    }
    accessToken = body.access_token
    return accessToken
  } catch {
    // Offline or the API unreachable: treat as no session rather than throwing
    // into whatever call happened to trigger the refresh.
    accessToken = null
    return null
  }
}

// Serialised across tabs where the browser has Web Locks (everywhere current;
// Chrome 69, Firefox 96, Safari 15.4). Where it does not, this falls back to the
// single-tab behaviour rather than failing: one tab is the common case, and a
// rotation that never runs is worse than one that can still race.
async function rotateExclusively(): Promise<string | null> {
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks
  if (!locks) return rotate()
  // `await` rather than a plain return: the DOM lib types the result as the
  // callback's own return value, so the promise `rotate` hands back would
  // otherwise arrive nested.
  return await locks.request(REFRESH_LOCK, rotate)
}

// Returns null when there is no usable session: no cookie, an expired one, or a
// reuse the server rejected. A null answer is the normal anonymous case, not an
// error to report.
export async function refreshAccessToken(): Promise<string | null> {
  if (!isBrowser) return null
  if (!inFlight) {
    // The lock is the cross-tab guard; this promise still shares one attempt
    // inside this tab, so a page's own callers never queue behind each other.
    inFlight = rotateExclusively().finally(() => {
      inFlight = null
    })
  }
  return inFlight
}
