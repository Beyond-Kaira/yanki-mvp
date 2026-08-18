'use client'

import { useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAnalysisBinding } from '@/components/ai-visibility/useAnalysisBinding'

/** Leave the current bound run and open the start-analysis empty state. */
export function useStartNewAnalysis(defaultPath = '/ai-visibility') {
  const router = useRouter()
  const { clearBinding } = useAnalysisBinding()

  return useCallback(() => {
    clearBinding()
    router.push(defaultPath)
  }, [clearBinding, defaultPath, router])
}
