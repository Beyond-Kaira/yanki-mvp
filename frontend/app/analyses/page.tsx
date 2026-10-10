import { Suspense } from 'react'
import AnalysisHistoryClient from './AnalysisHistoryClient'

/**
 * `/analyses` — the organization's analysis history.
 *
 * Gated; individual runs open in AI Visibility. The retired `/analyses/[id]`
 * route returns 404.
 *
 * The shell comes from the root layout — rendering another one here would
 * stack a second nav rail under the first.
 */
export default function AnalysisHistoryPage() {
  return (
    <Suspense
      fallback={
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading your analyses…
        </p>
      }
    >
      <AnalysisHistoryClient />
    </Suspense>
  )
}
