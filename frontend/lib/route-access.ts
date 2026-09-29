/**
 * Which routes a signed-out visitor may see.
 *
 * Deny by default: anything absent from these lists is gated. A new product
 * page is therefore protected the moment it exists, and the failure mode of
 * forgetting to classify one is a page that asks for a login it did not need —
 * visible, and harmless — rather than one that quietly serves private data.
 */
const PUBLIC_PATHS = new Set([
  '/',
  '/login',
  '/signup',
  '/checker',
  '/methodology',
])

/**
 * Capability URLs, retired analysis URLs, and the invitation flow. The retired
 * `/analyses/:id` path stays public solely so an anonymous visitor sees its 404
 * instead of being sent to login. The analysis list remains gated.
 */
const PUBLIC_PATTERNS = [
  /^\/analyses\/[^/]+$/,
  /^\/checker\/[^/]+$/,
  /^\/invite\/[^/]+$/,
]

export function isPublicPath(pathname: string): boolean {
  const path =
    pathname.length > 1 && pathname.endsWith('/')
      ? pathname.slice(0, -1)
      : pathname
  if (PUBLIC_PATHS.has(path)) return true
  return PUBLIC_PATTERNS.some((pattern) => pattern.test(path))
}
