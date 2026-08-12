'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import AppShell from '@/components/shell/AppShell'
import OverviewDashboard from '@/components/ai-visibility/OverviewDashboard'
import PageContainer from '@/components/shell/PageContainer'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import StepProgress from '@/components/StepProgress'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import { getAnalysis, ApiError } from '@/lib/api'
import {
  overviewFromAnalysis,
  type AiOverviewModel,
} from '@/lib/ai-overview'
import type { Analysis } from '@/lib/contracts'

const POLL_MS = 2000

export default function OverviewClient() {
  const params = useSearchParams()
  const fromQuery = params.get('analysis')
  const { analysisId: sessionId, setAnalysisId } = useAnalysisSession()
  const analysisId = fromQuery ?? sessionId
  const [model, setModel] = useState<AiOverviewModel | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [status, setStatus] = useState<
    'empty' | 'loading' | 'running' | 'ready' | 'error'
  >(analysisId ? 'loading' : 'empty')
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (fromQuery && fromQuery !== sessionId) {
      setAnalysisId(fromQuery)
    }
  }, [fromQuery, sessionId, setAnalysisId])

  useEffect(() => {
    function stop() {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }

    if (!analysisId) {
      stop()
      setModel(null)
      setAnalysis(null)
      setStatus('empty')
      setError(null)
      return
    }

    let cancelled = false
    setStatus('loading')

    async function poll() {
      try {
        const row = await getAnalysis(analysisId!)
        if (cancelled) return
        setAnalysisId(row.id)
        setAnalysis(row)
        setError(null)
        if (row.status === 'done') {
          setModel(overviewFromAnalysis(row))
          setStatus('ready')
          stop()
          return
        }
        if (row.status === 'failed') {
          setModel(null)
          setStatus('error')
          setError(row.error ?? 'The analysis failed.')
          stop()
          return
        }
        setModel(null)
        setStatus('running')
      } catch (err: unknown) {
        if (cancelled) return
        setModel(null)
        setAnalysis(null)
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Could not load analysis')
        if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
          stop()
        }
      }
    }

    poll()
    timerRef.current = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      stop()
    }
  }, [analysisId, setAnalysisId])

  return (
    <AppShell>
      {status === 'loading' ? (
        <PageContainer>
          <p className="text-sm text-surface-subtle" role="status">
            Loading analysis…
          </p>
        </PageContainer>
      ) : null}
      {status === 'running' && analysis ? (
        <PageContainer>
          <h1 className="mb-6 text-2xl font-semibold tracking-tight">
            Running analysis…
          </h1>
          <StepProgress
            status={analysis.status}
            progress={analysis.progress}
            currentStep={analysis.current_step}
            createdAt={analysis.created_at}
          />
          <p className="mt-4 text-sm text-surface-subtle">
            Prompts, Citations, and Drivers will fill with this same run when it
            finishes.
          </p>
        </PageContainer>
      ) : null}
      {status === 'error' ? (
        <PageContainer>
          <p className="mb-4 text-sm text-warning-strong" role="status">
            {error}
          </p>
          <StartAnalysisPanel title="Run a new analysis" />
        </PageContainer>
      ) : null}
      {status === 'empty' ? (
        <StartAnalysisPanel
          title="AI Visibility"
          description="Enter a domain to start a measured GEO analysis. Overview and every AI Visibility tab will use this same run."
        />
      ) : null}
      {status === 'ready' && model ? <OverviewDashboard model={model} /> : null}
    </AppShell>
  )
}
