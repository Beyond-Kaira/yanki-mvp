import { Suspense } from 'react'
import KeywordsOverviewClient from './KeywordsOverviewClient'

export default function Page() {
  return (
    <Suspense
      fallback={
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading…
        </p>
      }
    >
      <KeywordsOverviewClient />
    </Suspense>
  )
}
