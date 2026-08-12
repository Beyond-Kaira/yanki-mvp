const DEFAULT_NEXT = '/dashboard'

/**
 * Where to send someone after they authenticate.
 *
 * Only same-origin paths are honoured. A `next` of `https://evil.example` in
 * the query string would otherwise turn the login form into an open redirect —
 * the classic phishing primitive, made worse here because the victim has just
 * been asked to type a password.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_NEXT
  if (!raw.startsWith('/') || raw.startsWith('//')) return DEFAULT_NEXT
  return raw
}

export function loginHref(next: string | null | undefined): string {
  return `/login?next=${encodeURIComponent(safeNext(next))}`
}

export function currentPathWithQuery(): string {
  if (typeof window === 'undefined') return DEFAULT_NEXT
  return safeNext(`${window.location.pathname}${window.location.search}`)
}
