'use client'

import AnalysisHistoryClient from './AnalysisHistoryClient'

/**
 * `/analyses` — the organization's analysis history.
 *
 * Gated, unlike its own child route `/analyses/[id]`, which stays reachable
 * to anyone holding an id. A single result is a capability URL; a list has no
 * capability to present.
 *
 * The shell comes from `layout.tsx`, which wraps this page and `[id]` alike —
 * rendering another one here stacked a second nav rail under the first.
 */
export default function AnalysisHistoryPage() {
  return <AnalysisHistoryClient />
}
