// The organization a multi-org (contractor) user is currently acting in.
//
// Read by `lib/api.ts`, which turns it into the `X-Org-Id` request header the
// backend already honours (`org_dependencies.get_org_context`): a *request* for
// a scope, membership-checked server-side every time, never a grant. A single-org
// user never sets this and every request behaves exactly as before.
//
// Persisted in localStorage, unlike the access token, and deliberately so: the
// access token is a credential kept in memory only (see `lib/session.ts`), but an
// org id is not a secret, and a switch has to survive a reload or it is not a
// switch. A stale value — a membership the user has since lost — is self-healed
// in `AuthProvider` against the authoritative list `/auth/me` returns.

const STORAGE_KEY = 'yanki:active-org'

const isBrowser = typeof window !== 'undefined'

export function getActiveOrgId(): string | null {
  if (!isBrowser) return null
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can throw in private-mode Safari and sandboxed frames. A missing
    // preference is the safe default — the backend falls back to the first org.
    return null
  }
}

export function setActiveOrgId(orgId: string | null): void {
  if (!isBrowser) return
  try {
    if (orgId) {
      window.localStorage.setItem(STORAGE_KEY, orgId)
    } else {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // See above: if it cannot persist, the switch lasts for this page's life
    // rather than failing the click.
  }
}
