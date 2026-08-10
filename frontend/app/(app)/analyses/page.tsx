'use client'

import AppShell from '@/components/shell/AppShell'
import AnalysisHistoryClient from './AnalysisHistoryClient'

/**
 * `/analyses` — the organization's analysis history.
 *
 * Gated by the `(app)` group, unlike its own child route `/analyses/[id]`,
 * which stays public under `(public)` and reachable to anyone holding an id.
 * A single result is a capability URL; a list has no capability to present.
 */
export default function AnalysisHistoryPage() {
  return (
    <AppShell>
      <AnalysisHistoryClient />
    </AppShell>
  )
}
