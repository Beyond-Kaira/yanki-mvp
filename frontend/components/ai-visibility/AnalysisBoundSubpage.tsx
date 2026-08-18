'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import PageContainer from '@/components/shell/PageContainer'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import StepProgress from '@/components/StepProgress'
import NewAnalysisButton from '@/components/ai-visibility/NewAnalysisButton'
import PageHeaderRow from '@/components/shell/PageHeaderRow'
import { useAnalysisQuery } from '@/components/ai-visibility/useAnalysisQuery'
import { analysisDomain } from '@/lib/ai-visibility-data'
import type { Analysis } from '@/lib/contracts'

function analysisHref(path: string, analysisId: string | null): string {
  if (!analysisId) return path
  return `${path}?analysis=${analysisId}`
}

export default function AnalysisBoundSubpage({
  title,
  children,
}: {
  title: string
  children: (analysis: Analysis) => ReactNode
}) {
  const { analysisId, status, analysis, error } = useAnalysisQuery()

  return (
    <PageContainer>
      <p className="text-sm text-surface-subtle">
        <Link
          href={analysisHref('/ai-visibility', analysisId)}
          className="text-primary hover:text-primary-hover"
        >
          AI Visibility
        </Link>
        <span className="mx-1.5">/</span>
        {title}
      </p>
      <PageHeaderRow className="mt-2 mb-0" action={analysisId ? <NewAnalysisButton /> : null}>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        {analysis ? (
          <p className="mt-1 text-sm text-surface-subtle">
            {title} ·{' '}
            <span className="font-medium text-primary">
              {analysisDomain(analysis)}
            </span>
          </p>
        ) : analysisId ? (
          <p className="mt-1 text-sm text-surface-subtle" role="status">
            Loading domain…
          </p>
        ) : null}
      </PageHeaderRow>

      {status === 'loading' ? (
        <p className="mt-6 text-sm text-surface-subtle" role="status">
          Loading analysis…
        </p>
      ) : null}

      {status === 'running' && analysis ? (
        <div className="mt-6 space-y-4">
          <StepProgress
            status={analysis.status}
            progress={analysis.progress}
            currentStep={analysis.current_step}
            createdAt={analysis.created_at}
          />
          <p className="text-sm text-surface-subtle">
            This tab uses the same run as Overview. Results appear here when the
            analysis finishes.
          </p>
        </div>
      ) : null}

      {status === 'error' ? (
        <div className="mt-6 space-y-4">
          <p className="text-sm text-warning-strong" role="status">
            {error}
          </p>
          <StartAnalysisPanel title="Run a new analysis" />
        </div>
      ) : null}

      {status === 'empty' ? (
        <div className="mt-6">
          <StartAnalysisPanel
            title={title}
            description="Start a domain analysis here or on Overview. Every AI Visibility tab shares that same run."
          />
        </div>
      ) : null}

      {status === 'ready' && analysis ? (
        <div className="mt-6 space-y-6">{children(analysis)}</div>
      ) : null}
    </PageContainer>
  )
}
