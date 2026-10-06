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
import { useAuth } from '@/components/AuthProvider'
import type { AnalysisSummary } from '@/lib/contracts'
import {
  LAST_ANALYSIS_STORAGE_KEY,
  readRememberedAnalysisId,
  rememberAnalysisId as persistAnalysisId,
} from '@/lib/ai-visibility-data'

interface AnalysisSessionValue {
  analysisId: string | null
  setAnalysisId: (id: string | null) => void
  sessionScope: string | null
  trackedAnalyses: readonly TrackedAnalysis[]
  trackAnalysis: (analysis: AnalysisSummary) => void
  settleAnalyses: (ids: string[]) => void
}

export interface TrackedAnalysis {
  id: string
  initial?: AnalysisSummary
}

const EMPTY_TRACKED: readonly TrackedAnalysis[] = []

const AnalysisSessionContext = createContext<AnalysisSessionValue | null>(null)

export default function AnalysisSessionProvider({
  children,
}: {
  children: ReactNode
}) {
  const [analysisId, setAnalysisIdState] = useState<string | null>(null)
  const { user } = useAuth()
  const sessionScope = user ? `${user.id}:${user.organization?.id ?? 'personal'}` : null
  const storageKey = sessionScope ? `yanki:pendingAnalyses:${sessionScope}` : null
  const [tracked, setTracked] = useState<{ scope: string | null; rows: readonly TrackedAnalysis[] }>({ scope: null, rows: EMPTY_TRACKED })
  const trackedAnalyses = tracked.scope === sessionScope ? tracked.rows : EMPTY_TRACKED

  useEffect(() => {
    let rows: TrackedAnalysis[] = []
    try {
      const ids: unknown = storageKey ? JSON.parse(sessionStorage.getItem(storageKey) ?? '[]') : []
      if (Array.isArray(ids)) rows = [...new Set(ids.filter((id): id is string => typeof id === 'string'))].map(id => ({ id }))
    } catch { /* Storage is optional; in-memory tracking still works. */ }
    setTracked({ scope: sessionScope, rows })
  }, [sessionScope, storageKey])

  useEffect(() => {
    if (!storageKey || tracked.scope !== sessionScope) return
    try { sessionStorage.setItem(storageKey, JSON.stringify(tracked.rows.map(row => row.id))) } catch { /* ignore */ }
  }, [sessionScope, storageKey, tracked])

  const trackAnalysis = useCallback((analysis: AnalysisSummary) => {
    setTracked(current => ({
      scope: sessionScope,
      rows: [{ id: analysis.id, initial: analysis }, ...(current.scope === sessionScope ? current.rows.filter(row => row.id !== analysis.id) : [])],
    }))
  }, [sessionScope])

  const settleAnalyses = useCallback((ids: string[]) => {
    setTracked(current => {
      if (current.scope !== sessionScope || !current.rows.some(row => ids.includes(row.id))) return current
      return { ...current, rows: current.rows.filter(row => !ids.includes(row.id)) }
    })
  }, [sessionScope])

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
    () => ({ analysisId, setAnalysisId, sessionScope, trackedAnalyses, trackAnalysis, settleAnalyses }),
    [analysisId, setAnalysisId, sessionScope, trackedAnalyses, trackAnalysis, settleAnalyses],
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
      sessionScope: null,
      trackedAnalyses: EMPTY_TRACKED,
      trackAnalysis: () => {},
      settleAnalyses: () => {},
      setAnalysisId: (id: string | null) => {
        if (id) persistAnalysisId(id)
      },
    }
  }
  return value
}
