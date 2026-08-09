'use client'

import AppShell from '@/components/shell/AppShell'
import RequireAuth from '@/components/RequireAuth'
import AnalysisHistoryClient from './AnalysisHistoryClient'

/**
 * `/analyses` — the organization's analysis history.
 *
 * Behind `RequireAuth` deliberately, unlike its own child route
 * `/analyses/[id]`, which stays reachable to anyone holding an id. A single
 * result is a capability URL; a list has no capability to present.
 */
export default function AnalysisHistoryPage() {
  return (
    <RequireAuth>
      <AppShell>
        <AnalysisHistoryClient />
      </AppShell>
    </RequireAuth>
  )
}
