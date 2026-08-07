import { Suspense } from 'react'
import KeywordsMagicClient from './KeywordsMagicClient'

export default function Page() {
  return (
    <Suspense
      fallback={
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading…
        </p>
      }
    >
      <KeywordsMagicClient />
    </Suspense>
  )
}
