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
