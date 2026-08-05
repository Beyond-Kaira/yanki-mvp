import { Suspense } from 'react'
import CitationsClient from './CitationsClient'

export default function Page() {
  return (
    <Suspense
      fallback={
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading…
        </p>
      }
    >
      <CitationsClient />
    </Suspense>
  )
}
