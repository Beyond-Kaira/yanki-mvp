'use client'

import { useMemo } from 'react'
import AppShell from '@/components/shell/AppShell'
import OverviewDashboard from '@/components/ai-visibility/OverviewDashboard'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import StepProgress from '@/components/StepProgress'
import { useAnalysisQuery } from '@/components/ai-visibility/useAnalysisQuery'
import { overviewFromAnalysis } from '@/lib/ai-overview'

export default function OverviewClient() {
  const { status, analysis, error } = useAnalysisQuery({ slices: 'ai' })
  const model = useMemo(
    () => (status === 'ready' && analysis ? overviewFromAnalysis(analysis) : null),
    [status, analysis],
  )

  return (
    <AppShell>
      {status === 'loading' ? (
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading analysis…
        </p>
      ) : null}
      {status === 'running' && analysis ? (
        <div className="mx-auto max-w-3xl px-6 py-10 sm:px-8">
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
        </div>
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
          description="Enter a domain to start a measured GEO analysis. Overview and every AI Visibility tab will use this same run."
        />
      ) : null}
      {status === 'ready' && model ? <OverviewDashboard model={model} /> : null}
    </AppShell>
  )
}
