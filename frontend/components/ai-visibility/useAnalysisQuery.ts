'use client'

import { useEffect, useRef, useState } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import {
  fetchAnalysisSlices,
  getAnalysis,
  ApiError,
} from '@/lib/api'
import {
  analysisFromEnvelope,
  mergeAnalysis,
  type AnalysisSliceMode,
} from '@/lib/analysis-bundle'
import { resolveBoundAnalysisId } from '@/lib/analysis-route'
import type { Analysis } from '@/lib/contracts'
import { useAnalysisBinding } from '@/components/ai-visibility/useAnalysisBinding'

export type AnalysisQueryStatus =
  | 'empty'
  | 'loading'
  | 'running'
  | 'ready'
  | 'error'

const POLL_MS = 2000

export function useAnalysisQuery(options?: {
  slices?: AnalysisSliceMode
}): {
  analysisId: string | null
  status: AnalysisQueryStatus
  analysis: Analysis | null
  error: string | null
} {
  const sliceMode = options?.slices ?? 'full'
  const params = useSearchParams()
  const pathname = usePathname()
  const fromQuery = params.get('analysis')
  const { analysisId: sessionId, setAnalysisId } = useAnalysisSession()
  // Overview without `?analysis=` stays empty so "New analysis" can start fresh.
  // Subpages and nav links fall back to the remembered run for tab binding.
  const analysisId = resolveBoundAnalysisId(fromQuery, pathname, sessionId)
  const { clearBinding } = useAnalysisBinding()
  const [status, setStatus] = useState<AnalysisQueryStatus>(
    analysisId ? 'loading' : 'empty',
  )
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (fromQuery) {
      setAnalysisId(fromQuery)
    }
  }, [fromQuery, setAnalysisId])

  useEffect(() => {
    function stop() {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }

    if (!analysisId) {
      stop()
      setAnalysis(null)
      setStatus('empty')
      setError(null)
      return
    }

    let cancelled = false
    setStatus('loading')

    async function poll() {
      try {
        const envelope = await getAnalysis(analysisId!)
        if (cancelled) return
        setAnalysisId(envelope.id)
        setError(null)

        if (envelope.status === 'done') {
          const slices = await fetchAnalysisSlices(envelope.id, sliceMode)
          if (cancelled) return
          setAnalysis(mergeAnalysis(envelope, slices))
          setStatus('ready')
          stop()
          return
        }

        if (envelope.status === 'failed') {
          const slices = await fetchAnalysisSlices(envelope.id, sliceMode)
          if (cancelled) return
          setAnalysis(mergeAnalysis(envelope, slices))
          setStatus('error')
          setError(envelope.error ?? 'The analysis failed.')
          stop()
          return
        }

        setAnalysis(analysisFromEnvelope(envelope))
        setStatus('running')
      } catch (err: unknown) {
        if (cancelled) return
        setAnalysis(null)
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Could not load analysis')
        if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
          stop()
          clearBinding(analysisId!)
        }
      }
    }

    poll()
    timerRef.current = setInterval(poll, POLL_MS)

    return () => {
      cancelled = true
      stop()
    }
  }, [analysisId, clearBinding, setAnalysisId, sliceMode])

  return { analysisId, status, analysis, error }
}
