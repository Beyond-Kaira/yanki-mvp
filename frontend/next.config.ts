import type { NextConfig } from 'next'

// In dev there is no CORS: Next proxies /api/* and /healthz to the FastAPI
// backend so the browser only ever talks to the frontend origin. All frontend
// fetches use relative paths. Override the target with API_ORIGIN (compose sets
// it to http://api:8141).
const apiOrigin = process.env.API_ORIGIN ?? 'http://localhost:8141'

const nextConfig: NextConfig = {
  // Rank-check fans out live DataForSEO calls; default 30s proxy timeout → 500.
  experimental: {
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${apiOrigin}/api/:path*` },
      { source: '/healthz', destination: `${apiOrigin}/healthz` },
    ]
  },
}

export default nextConfig
