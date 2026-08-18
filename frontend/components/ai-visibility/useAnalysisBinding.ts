'use client'

import { useCallback } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import { notifyAnalysisQuotaChanged } from '@/lib/analysis-quota-events'

/** Drop the bound analysis from session and from the current URL when it matches. */
export function useAnalysisBinding() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { analysisId: sessionId, setAnalysisId } = useAnalysisSession()

  const clearBinding = useCallback(
    (id?: string) => {
      const fromQuery = searchParams.get('analysis')
      const bound = fromQuery ?? sessionId
      if (id != null && bound !== id) return

      setAnalysisId(null)
      if (fromQuery) {
        const next = new URLSearchParams(searchParams.toString())
        next.delete('analysis')
        const qs = next.toString()
        router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
      }
    },
    [pathname, router, searchParams, sessionId, setAnalysisId],
  )

  return { clearBinding, notifyQuotaChanged: notifyAnalysisQuotaChanged }
}
