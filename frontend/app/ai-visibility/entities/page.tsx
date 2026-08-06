import { Suspense } from 'react'
import EntitiesClient from './EntitiesClient'

export default function EntitiesPage() {
  return (
    <Suspense>
      <EntitiesClient />
    </Suspense>
  )
}
