'use client'

import { useMemo } from 'react'
import OverviewDashboard from '@/components/ai-visibility/OverviewDashboard'
import RecentAnalysesPanel from '@/components/ai-visibility/RecentAnalysesPanel'
import NewAnalysisButton from '@/components/ai-visibility/NewAnalysisButton'
import CustomGeoGuidedWizard from '@/components/guided/CustomGeoGuidedWizard'
import PageContainer from '@/components/shell/PageContainer'
import PageHeaderRow from '@/components/shell/PageHeaderRow'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import { useAnalysisQuery } from '@/components/ai-visibility/useAnalysisQuery'
import { overviewFromAnalysis } from '@/lib/ai-overview'

export default function OverviewClient() {
  const { status, analysis, error, resumePolling, setAnalysis } =
    useAnalysisQuery({ slices: 'ai' })
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
      {status === 'review' && analysis ? (
        <PageContainer className="pb-12">
          <PageHeaderRow className="mb-6" action={<NewAnalysisButton />}>
            <span className="sr-only">Guided review</span>
          </PageHeaderRow>
          <CustomGeoGuidedWizard
            analysis={analysis}
            onAnalysisUpdated={setAnalysis}
            onMeasureStarted={resumePolling}
          />
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
      {status === 'empty' || status === 'running' ? (
        <>
          <StartAnalysisPanel
            title="AI Visibility"
            description="Enter a domain to start a measured GEO analysis. Overview and every AI Visibility tab will use this same run."
          />
          <PageContainer className="pb-12 pt-0">
            <RecentAnalysesPanel activeAnalysis={status === 'running' ? analysis : null} />
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
