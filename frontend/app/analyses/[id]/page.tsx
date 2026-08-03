'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams } from 'next/navigation'
import { getAnalysis, ApiError } from '@/lib/api'
import type { Analysis } from '@/lib/contracts'
import {
  deriveEnginePresence,
  groupByQuestion,
  runEngineIds,
} from '@/lib/results'
import FailedState from '@/components/FailedState'
import StepProgress from '@/components/StepProgress'
import ScoreSummary from '@/components/ScoreSummary'
import EnginePresenceMap from '@/components/EnginePresenceMap'
import QuestionBreakdown from '@/components/QuestionBreakdown'
import KycCard from '@/components/KycCard'
import SerpVisibility from '@/components/SerpVisibility'
import SeoAudit from '@/components/SeoAudit'
import WaitlistForm from '@/components/WaitlistForm'

const POLL_MS = 2000

export default function AnalysisPage() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false

    function stop() {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }

    async function poll() {
      try {
        const data = await getAnalysis(id)
        if (cancelled) return
        setAnalysis(data)
        setLoadError(null)
        if (data.status === 'done' || data.status === 'failed') stop()
      } catch (err) {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : 'Something went wrong.')
        // A 404/422 will never self-resolve (unknown or malformed id), so stop
        // polling; transient errors keep retrying.
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
  }, [id])

  let content: ReactNode
  if (!analysis && loadError) {
    // Nothing loaded, so there is no run to point at a step within.
    content = (
      <FailedState
        subject="analysis"
        reason={loadError}
        step={null}
        progress={0}
        retryHref="/"
        retryLabel="Try another URL"
      />
    )
  } else if (!analysis) {
    content = (
      <p role="status" className="text-sm text-surface-subtle">
        Loading…
      </p>
    )
  } else if (analysis.status === 'failed') {
    content = (
      <FailedState
        subject="analysis"
        reason={analysis.error ?? 'The analysis failed.'}
        step={analysis.current_step}
        progress={analysis.progress}
        retryHref="/"
        retryLabel="Try another URL"
      />
    )
  } else if (analysis.status === 'done') {
    content = <Results analysis={analysis} />
  } else {
    content = (
      <StepProgress
        status={analysis.status}
        progress={analysis.progress}
        currentStep={analysis.current_step}
        createdAt={analysis.created_at}
      />
    )
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-12 sm:px-8">
      <div className="space-y-8">
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Analysis
          </h1>
          {analysis ? (
            <p className="break-all text-sm text-surface-subtle">{analysis.url}</p>
          ) : null}
        </header>
        {/* Persistent live region for the success outcome: StepProgress (and its
            own live region) unmounts on completion, so announce "done" here. The
            failure outcome is announced by FailureCard's role="alert", which fires
            on every entry path (transition, direct load, and network error). */}
        <p aria-live="polite" className="sr-only">
          {analysis?.status === 'done'
            ? 'Analysis complete. Your GEO score is ready.'
            : ''}
        </p>
        {content}
      </div>
    </main>
  )
}

function Results({ analysis }: { analysis: Analysis }) {
  const { result } = analysis
  const total = result.total_responses ?? result.responses.length
  const footprints =
    result.footprint_count ??
    result.responses.filter((response) => response.footprint).length
  // Null when there is nothing to score; ScoreSummary withholds the verdict
  // rather than reading the backend's 0.0 as "engines left you out".
  const percent =
    result.geo_score === null ? null : Math.round(result.geo_score * 100)

  // One path whether or not the envelope carried an aggregate: reported numbers
  // win, the panel still sets the roster, so a silent engine is listed either way.
  const presence = useMemo(
    () => deriveEnginePresence(result.responses, result.engine_presence),
    [result.responses, result.engine_presence],
  )
  const engines = useMemo(
    () => runEngineIds(result.responses, result.engine_presence),
    [result.responses, result.engine_presence],
  )
  const questions = useMemo(
    () => groupByQuestion(result.prompts, result.responses),
    [result.prompts, result.responses],
  )

  return (
    <div className="space-y-8">
      <ScoreSummary
        score={percent}
        footprintCount={footprints}
        totalResponses={total}
        questionCount={result.prompts.length}
        engineCount={presence.length}
      />

      {result.kyc ? <KycCard kyc={result.kyc} /> : null}

      {result.serp ? <SerpVisibility serp={result.serp} /> : null}

      {result.seo ? <SeoAudit seo={result.seo} /> : null}

      {presence.length > 0 ? <EnginePresenceMap presence={presence} /> : null}

      {/* Gated on answers, not questions: a run can hold prompts and no
          responses, and rendering a column of 0/N cards would say less than
          the sentence does. */}
      {result.responses.length > 0 ? (
        <QuestionBreakdown groups={questions} engines={engines} />
      ) : (
        <p className="text-sm text-surface-subtle">
          No engine answers were recorded for this analysis.
        </p>
      )}

      {/* Growth loop: once a score is on screen, invite the visitor to keep
          tracking it. Reuses WaitlistForm as-is (its own <section> landmark and
          H2 come along); the copy below sets the context above it. */}
      <section aria-labelledby="track-heading" className="space-y-2">
        <h2
          id="track-heading"
          className="text-xl font-semibold text-surface-foreground"
        >
          Want to track this score over time?
        </h2>
        <p className="max-w-2xl text-sm text-surface-subtle">
          Join the waitlist for weekly tracking and updates as your AI visibility
          changes.
        </p>
        <WaitlistForm />
      </section>
    </div>
  )
}
