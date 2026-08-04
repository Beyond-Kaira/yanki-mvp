'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { getAnalysis, ApiError } from '@/lib/api'
import type { Analysis, AnalysisResponse, Prompt } from '@/lib/contracts'
import { deriveEnginePresence } from '@/lib/results'
import FailedState from '@/components/FailedState'
import StepProgress from '@/components/StepProgress'
import ScoreSummary from '@/components/ScoreSummary'
import ResultsTable from '@/components/ResultsTable'
import EnginePresenceMap from '@/components/EnginePresenceMap'
import CompetitorsList from '@/components/CompetitorsList'
import SerpVisibility from '@/components/SerpVisibility'
import EmailGate from '@/components/EmailGate'
import WaitlistForm from '@/components/WaitlistForm'

const POLL_MS = 2000

function CheckerResults() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const searchParams = useSearchParams()
  // Carried from the submit response; P5.5's email gate posts against it.
  const submissionId = searchParams.get('submission_id')
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

  // Nothing loaded and an error came back: there is no run to point at a step
  // within, so the load failure itself is the only thing to report.
  const content: ReactNode =
    !analysis && loadError ? (
      <FailedState
        subject="check"
        reason={loadError}
        step={null}
        progress={0}
        retryHref="/checker"
        retryLabel="Check another brand"
      />
    ) : !analysis ? (
      <p role="status" className="text-sm text-surface-subtle">
        Loading…
      </p>
    ) : analysis.status === 'failed' ? (
      <FailedState
        subject="check"
        reason={analysis.error ?? 'The check failed.'}
        step={analysis.current_step}
        progress={analysis.progress}
        retryHref="/checker"
        retryLabel="Check another brand"
      />
    ) : analysis.status === 'done' ? (
      <Results analysis={analysis} submissionId={submissionId} />
    ) : (
      <StepProgress
        status={analysis.status}
        progress={analysis.progress}
        currentStep={analysis.current_step}
        createdAt={analysis.created_at}
      />
    )

  return (
    <main
      data-submission-id={submissionId ?? undefined}
      className="mx-auto max-w-4xl px-4 py-12 sm:px-8"
    >
      <div className="space-y-8">
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Your AI visibility check
          </h1>
        </header>
        {/* Persistent live region for the success outcome: StepProgress (and its
            own live region) unmounts on completion, so announce "done" here. */}
        <p aria-live="polite" className="sr-only">
          {analysis?.status === 'done'
            ? 'Check complete. Your visibility score is ready.'
            : ''}
        </p>
        {content}
        <footer className="border-t border-surface-border pt-6">
          <Link
            href="/methodology"
            className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            How we score this
          </Link>
        </footer>
      </div>
    </main>
  )
}

export default function CheckerResultsPage() {
  // useSearchParams needs a Suspense boundary to keep `next build` from
  // bailing the route out of static rendering with an error.
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-4xl px-4 py-12 sm:px-8">
          <p role="status" className="text-sm text-surface-subtle">
            Loading…
          </p>
        </main>
      }
    >
      <CheckerResults />
    </Suspense>
  )
}

function Results({
  analysis,
  submissionId,
}: {
  analysis: Analysis
  submissionId: string | null
}) {
  const { result } = analysis
  const total = result.total_responses ?? result.responses.length
  const footprints =
    result.footprint_count ??
    result.responses.filter((response) => response.footprint).length
  // Backend composite GEO is already 0–100; ScoreSummary expects that scale.
  const percent =
    result.geo_score === null ? null : Math.round(result.geo_score)
  // Checker rows carry `engine_presence` from the backend, whose aggregate walks
  // the responses it has and so omits an engine that answered nothing. Passing
  // it through the same helper keeps the reported numbers while seeding the
  // roster from the panel, so this surface makes the same promise as /analyses.
  const presence = deriveEnginePresence(
    result.responses,
    result.engine_presence,
  )

  // The email gate is the PRIMARY conversion here, so the waitlist section stays
  // hidden until the gate is out of the way — either unlocked by the visitor, or
  // never shown at all (0 or 1 answer leaves nothing to gate). It then appears
  // below, secondary to the gate, never pre-empting it.
  const [unlocked, setUnlocked] = useState(false)
  const gateInPlay = result.responses.length > 1
  const showWaitlist = !gateInPlay || unlocked

  return (
    <div className="space-y-8">
      <ScoreSummary
        score={percent}
        footprintCount={footprints}
        totalResponses={total}
        questionCount={result.prompts.length}
        engineCount={presence.length}
      />

      {presence.length > 0 ? <EnginePresenceMap presence={presence} /> : null}

      {result.competitors_appeared ? (
        <CompetitorsList competitors={result.competitors_appeared} />
      ) : null}

      {result.serp ? <SerpVisibility serp={result.serp} /> : null}

      <GatedAnswers
        responses={result.responses}
        prompts={result.prompts}
        submissionId={submissionId}
        unlocked={unlocked}
        onUnlock={() => setUnlocked(true)}
      />

      {showWaitlist ? (
        <section aria-labelledby="track-heading" className="space-y-2">
          <h2
            id="track-heading"
            className="text-xl font-semibold text-surface-foreground"
          >
            Want to track this score over time?
          </h2>
          <p className="max-w-2xl text-sm text-surface-subtle">
            Join the waitlist for weekly tracking and updates as your AI
            visibility changes.
          </p>
          <WaitlistForm />
        </section>
      ) : null}
    </div>
  )
}

// The one free answer defaults to the first answer that mentions the brand
// (footprint === true), falling back to the very first answer.
function pickFreeIndex(responses: AnalysisResponse[]): number {
  const idx = responses.findIndex((response) => response.footprint === true)
  return idx >= 0 ? idx : 0
}

function GatedAnswers({
  responses,
  prompts,
  submissionId,
  unlocked,
  onUnlock,
}: {
  responses: AnalysisResponse[]
  prompts: Prompt[]
  submissionId: string | null
  unlocked: boolean
  onUnlock: () => void
}) {
  if (responses.length === 0) {
    return (
      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-surface-foreground">
          Every answer
        </h2>
        <p className="text-sm text-surface-subtle">
          No engine answers were recorded for this check.
        </p>
      </section>
    )
  }

  // Nothing to gate once every answer would show anyway (unlocked, or a lone
  // answer): render the full table so the reveal happens in place.
  if (unlocked || responses.length === 1) {
    return (
      <section className="space-y-3">
        <h2 className="text-xl font-semibold text-surface-foreground">
          Every answer
        </h2>
        <ResultsTable responses={responses} prompts={prompts} />
      </section>
    )
  }

  const freeIndex = pickFreeIndex(responses)
  const freeResponse = responses[freeIndex]
  const hiddenCount = responses.length - 1

  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-surface-foreground">
        A sample answer
      </h2>
      <ResultsTable responses={[freeResponse]} prompts={prompts} />
      <EmailGate
        submissionId={submissionId}
        hiddenCount={hiddenCount}
        onUnlock={onUnlock}
      />
    </section>
  )
}
