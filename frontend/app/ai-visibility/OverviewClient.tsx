'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import AppShell from '@/components/shell/AppShell'
import OverviewDashboard from '@/components/ai-visibility/OverviewDashboard'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import { getAnalysis } from '@/lib/api'
import {
  overviewFromAnalysis,
  type AiOverviewModel,
} from '@/lib/ai-overview'

export default function OverviewClient() {
  const params = useSearchParams()
  const analysisId = params.get('analysis')
  const [model, setModel] = useState<AiOverviewModel | null>(null)
  const [status, setStatus] = useState<'empty' | 'loading' | 'ready' | 'error'>(
    analysisId ? 'loading' : 'empty',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!analysisId) {
      setModel(null)
      setStatus('empty')
      setError(null)
      return
    }
    let cancelled = false
    setStatus('loading')
    getAnalysis(analysisId)
      .then((analysis) => {
        if (cancelled) return
        setModel(overviewFromAnalysis(analysis))
        setStatus('ready')
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setModel(null)
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Could not load analysis')
      })
    return () => {
      cancelled = true
    }
  }, [analysisId])

  return (
    <AppShell>
      {status === 'loading' ? (
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading analysis…
        </p>
      ) : null}
      {status === 'error' ? (
        <div className="px-8 pt-6">
          <p className="mb-4 text-sm text-warning-strong" role="status">
            {error}
          </p>
          <StartAnalysisPanel title="Run a new analysis" />
        </div>
      ) : null}
      {status === 'empty' ? (
        <StartAnalysisPanel
          title="AI Visibility"
          description="Enter a domain to start a measured GEO analysis. Overview metrics appear here when the run finishes."
        />
      ) : null}
      {status === 'ready' && model ? <OverviewDashboard model={model} /> : null}
    </AppShell>
  )
}
