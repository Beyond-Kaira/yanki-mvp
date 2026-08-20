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

/** Post-submit landing: guided runs always open the review wizard on AI Visibility. */
export function analysisSubmitLandingHref(
  analysisId: string,
  options: { mode: 'quick' | 'guided'; pathname: string },
): string {
  if (options.mode === 'guided') {
    return guidedReviewHref(analysisId)
  }
  if (options.pathname.startsWith('/search-visibility')) {
    return `/search-visibility?analysis=${encodeURIComponent(analysisId)}`
  }
  if (options.pathname.startsWith('/ai-visibility')) {
    return `/ai-visibility?analysis=${encodeURIComponent(analysisId)}`
  }
  return `/analyses/${encodeURIComponent(analysisId)}`
}
