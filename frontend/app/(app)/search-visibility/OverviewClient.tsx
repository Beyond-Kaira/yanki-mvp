'use client'

import Link from 'next/link'
import AppShell from '@/components/shell/AppShell'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import StepProgress from '@/components/StepProgress'
import SerpVisibility from '@/components/SerpVisibility'
import SeoAudit from '@/components/SeoAudit'
import { useAnalysisQuery } from '@/components/ai-visibility/useAnalysisQuery'
import { analysisDomain } from '@/lib/ai-visibility-data'

export default function SearchVisibilityOverviewClient() {
  const { analysisId, status, analysis, error } = useAnalysisQuery()

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
            Search results visibility and the AI readiness audit appear here when
            this run finishes.
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
          title="Search Visibility"
          description="Enter a domain to measure ordinary search visibility and AI readiness. This overview uses the same analysis as AI Visibility."
        />
      ) : null}

      {status === 'ready' && analysis ? (
        <div className="mx-auto max-w-5xl px-6 py-8 sm:px-8">
          <header className="mb-8">
            <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
              Search Visibility
            </h1>
            <p className="mt-1 text-sm text-surface-subtle">
              Overview ·{' '}
              <span className="font-medium text-primary">
                {analysisDomain(analysis)}
              </span>
            </p>
            <p className="mt-3 text-sm text-surface-subtle">
              Also see{' '}
              <Link
                href={
                  analysisId
                    ? `/ai-visibility?analysis=${analysisId}`
                    : '/ai-visibility'
                }
                className="font-medium text-primary hover:text-primary-hover"
              >
                AI Visibility overview
              </Link>{' '}
              for GEO score, citations, and drivers.
            </p>
          </header>

          <div className="space-y-8">
            {analysis.result.serp ? (
              <SerpVisibility serp={analysis.result.serp} />
            ) : (
              <section className="rounded-xl border border-dashed border-surface-border bg-surface px-4 py-8 text-center">
                <h2 className="text-lg font-semibold text-surface-foreground">
                  Search results visibility
                </h2>
                <p className="mt-2 text-sm text-surface-subtle">
                  No SERP measurement for this run. Enable SERP in deploy settings
                  or re-run when search visibility is on.
                </p>
              </section>
            )}

            {analysis.result.seo ? (
              <SeoAudit seo={analysis.result.seo} />
            ) : (
              <section className="rounded-xl border border-dashed border-surface-border bg-surface px-4 py-8 text-center">
                <h2 className="text-lg font-semibold text-surface-foreground">
                  AI readiness audit
                </h2>
                <p className="mt-2 text-sm text-surface-subtle">
                  No AI readiness audit for this run.
                </p>
              </section>
            )}
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
