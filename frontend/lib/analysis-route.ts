/** AI Visibility subpages share one run; overview pages start fresh without `?analysis=`. */
export function analysisRouteUsesSession(pathname: string): boolean {
  if (pathname === '/ai-visibility' || pathname === '/search-visibility') {
    return false
  }
  return (
    pathname.startsWith('/ai-visibility') ||
    pathname.startsWith('/search-visibility')
  )
}

export function resolveBoundAnalysisId(
  fromQuery: string | null,
  pathname: string,
  sessionId: string | null,
): string | null {
  if (fromQuery) return fromQuery
  if (analysisRouteUsesSession(pathname)) return sessionId
  return null
}

/** Where the guided review wizard lives (ADR-50). */
export function guidedReviewHref(analysisId: string): string {
  return `/ai-visibility?analysis=${encodeURIComponent(analysisId)}`
}

/** Keep the start form and live history visible after either run mode starts. */
export function analysisSubmitLandingHref(pathname: string): string {
  if (pathname.startsWith('/search-visibility')) {
    return '/search-visibility'
  }
  if (pathname.startsWith('/ai-visibility')) {
    return '/ai-visibility'
  }
  return '/dashboard'
}
