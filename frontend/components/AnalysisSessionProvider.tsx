'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  LAST_ANALYSIS_STORAGE_KEY,
  readRememberedAnalysisId,
  rememberAnalysisId as persistAnalysisId,
} from '@/lib/ai-visibility-data'

interface AnalysisSessionValue {
  analysisId: string | null
  setAnalysisId: (id: string | null) => void
}

const AnalysisSessionContext = createContext<AnalysisSessionValue | null>(null)

export default function AnalysisSessionProvider({
  children,
}: {
  children: ReactNode
}) {
  const [analysisId, setAnalysisIdState] = useState<string | null>(null)

  useEffect(() => {
    setAnalysisIdState(readRememberedAnalysisId())
  }, [])

  const setAnalysisId = useCallback((id: string | null) => {
    setAnalysisIdState(id)
    if (id) {
      persistAnalysisId(id)
      return
    }
    try {
      sessionStorage.removeItem(LAST_ANALYSIS_STORAGE_KEY)
    } catch {
      // ignore
    }
  }, [])

  const value = useMemo(
    () => ({ analysisId, setAnalysisId }),
    [analysisId, setAnalysisId],
  )

  return (
    <AnalysisSessionContext.Provider value={value}>
      {children}
    </AnalysisSessionContext.Provider>
  )
}

export function useAnalysisSession(): AnalysisSessionValue {
  const value = useContext(AnalysisSessionContext)
  // Tests and rare trees outside the root layout still need a no-op-safe API.
  if (!value) {
    return {
      analysisId: null,
      setAnalysisId: (id: string | null) => {
        if (id) persistAnalysisId(id)
      },
    }
  }
  return value
}
