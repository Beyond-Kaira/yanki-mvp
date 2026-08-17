'use client'

import { useMemo } from 'react'
import OverviewDashboard from '@/components/ai-visibility/OverviewDashboard'
import RecentAnalysesPanel from '@/components/ai-visibility/RecentAnalysesPanel'
import NewAnalysisButton from '@/components/ai-visibility/NewAnalysisButton'
import PageContainer from '@/components/shell/PageContainer'
import PageHeaderRow from '@/components/shell/PageHeaderRow'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import StepProgress from '@/components/StepProgress'
import { useAnalysisQuery } from '@/components/ai-visibility/useAnalysisQuery'
import { overviewFromAnalysis } from '@/lib/ai-overview'

export default function OverviewClient() {
  const { status, analysis, error } = useAnalysisQuery({ slices: 'ai' })
  const model = useMemo(
    () =>
      status === 'ready' && analysis ? overviewFromAnalysis(analysis) : null,
    [status, analysis],
  )

  return (
    <>
      {status === 'loading' ? (
        <PageContainer>
          <p className="text-sm text-surface-subtle" role="status">
            Loading analysis…
          </p>
        </PageContainer>
      ) : null}
      {status === 'running' && analysis ? (
        <PageContainer>
          <PageHeaderRow className="mb-6" action={<NewAnalysisButton />}>
            <h1 className="text-2xl font-semibold tracking-tight">
              Running analysis…
            </h1>
          </PageHeaderRow>
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
        <>
          <PageContainer>
            <PageHeaderRow className="mb-4" action={<NewAnalysisButton />}>
              <p className="text-sm text-warning-strong" role="alert">
                {error}
              </p>
            </PageHeaderRow>
          </PageContainer>
          <StartAnalysisPanel title="Run a new analysis" />
          <PageContainer className="pb-12 pt-0">
            <RecentAnalysesPanel />
          </PageContainer>
        </>
      ) : null}
      {status === 'empty' ? (
        <>
          <StartAnalysisPanel
            title="AI Visibility"
            description="Enter a domain to start a measured GEO analysis. Overview and every AI Visibility tab will use this same run."
          />
          <PageContainer className="pb-12 pt-0">
            <RecentAnalysesPanel />
          </PageContainer>
        </>
      ) : null}
      {status === 'ready' && model ? (
        <>
          <OverviewDashboard model={model} />
          <PageContainer className="pb-12 pt-0">
            <RecentAnalysesPanel />
          </PageContainer>
        </>
      ) : null}
    </>
  )
}
