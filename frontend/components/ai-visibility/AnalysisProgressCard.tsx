'use client'

import { useId, useState } from 'react'
import Link from 'next/link'
import type { AnalysisSummary } from '@/lib/contracts'
import { guidedReviewHref } from '@/lib/analysis-route'
import { ANALYSIS_STEPS, analysisStepState, STEP_DESCRIPTIONS, STEP_STATE_WORD } from '@/lib/steps'
import { IconChevron, IconSpark } from '@/components/shell/icons'
import { formatElapsed, useElapsedSeconds } from '@/components/useElapsedSeconds'

export default function AnalysisProgressCard({ analysis }: { analysis: AnalysisSummary }) {
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const live = analysis.status === 'running' || analysis.status === 'queued'
  const failed = analysis.status === 'failed'
  const review = analysis.status === 'awaiting_review'
  const elapsed = useElapsedSeconds(analysis.created_at, live)
  const progress = Math.max(0, Math.min(100, analysis.progress))
  const target = analysis.url.replace(/^https?:\/\//, '').replace(/\/$/, '')
  const activeStep = ANALYSIS_STEPS.find((_, index) =>
    analysisStepState(index, analysis.status, progress, analysis.current_step) === 'active',
  )
  const title = failed ? 'Analysis failed' : review ? 'Ready for your review'
    : analysis.status === 'queued' ? 'Analysis queued'
    : analysis.status === 'done' ? 'Analysis complete' : 'Analysis running in the background'
  const description = failed ? analysis.error ?? 'The analysis could not finish.'
    : review ? 'Review your company profile and prompts before measuring.'
    : activeStep?.key === 'execute' ? 'Asking AI models the questions your buyers ask.'
    : activeStep ? STEP_DESCRIPTIONS[activeStep.key]
    : analysis.status === 'queued' ? 'Starting soon. You can keep using this page.'
    : 'Your results are ready.'

  return (
    <article aria-label={`Analysis for ${target}`} className="overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-sm">
      <button
        type="button" aria-expanded={expanded} aria-controls={detailsId}
        aria-label={`${expanded ? 'Collapse' : 'Show'} analysis steps for ${target}`}
        onClick={() => {
          setExpanded(!expanded)
        }}
        className="flex w-full items-center gap-3 px-4 py-4 text-left hover:bg-surface-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary sm:px-5"
      >
        <span aria-hidden className={`hidden h-10 w-10 shrink-0 items-center justify-center rounded-xl sm:flex ${failed ? 'bg-danger-soft text-danger-strong' : 'bg-primary-soft text-primary-strong'}`}>
          <IconSpark className="h-5 w-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span aria-live="polite" className={`block break-words text-sm font-semibold ${failed ? 'text-danger-strong' : 'text-surface-foreground'}`}>
            {title}<span className="sr-only">{activeStep ? `: ${activeStep.label}` : ''}</span>
          </span>
          <span className="mt-0.5 block break-all text-xs text-surface-subtle">
            {target}{activeStep ? ` · ${activeStep.label}` : ''}
          </span>
        </span>
        <span className="shrink-0 text-xl font-semibold tabular-nums">{progress}%</span>
        <span aria-hidden className="flex h-11 w-11 shrink-0 items-center justify-center text-surface-subtle">
          <IconChevron className={`h-4 w-4 motion-safe:transition-transform motion-safe:duration-200 motion-safe:ease-out ${expanded ? '-rotate-90' : 'rotate-90'}`} />
        </span>
      </button>
      <div id={detailsId} aria-hidden={!expanded} inert={!expanded}
        className={`grid motion-safe:transition-[grid-template-rows,opacity,visibility] motion-safe:duration-200 motion-safe:ease-out ${expanded ? 'visible grid-rows-[1fr] opacity-100' : 'invisible grid-rows-[0fr] opacity-0'}`}>
        <div className="min-h-0 overflow-hidden">
          <div className="px-4 pb-4 sm:px-5">
            <ol aria-label="Analysis steps" className="grid grid-cols-3 gap-y-5 pb-4 pt-2 sm:grid-cols-6">
              {ANALYSIS_STEPS.map((step, index) => {
                const state = analysisStepState(index, analysis.status, progress, analysis.current_step)
                const completed = state === 'done'
                const active = state === 'active'
                const broken = state === 'failed'
                return (
                  <li key={step.key} aria-current={active ? 'step' : undefined} className="relative flex min-w-0 flex-col items-center gap-2">
                    {index > 0 ? <span aria-hidden className={`absolute right-1/2 top-3 h-0.5 w-full ${completed || active || broken ? 'bg-primary' : 'bg-surface-border'} ${index === 3 ? 'hidden sm:block' : ''}`} /> : null}
                    <span aria-hidden className={`relative z-10 flex h-6 w-6 items-center justify-center rounded-full text-xs ${completed ? 'bg-primary-soft text-primary-strong' : active ? 'bg-primary text-white ring-4 ring-primary-soft' : broken ? 'bg-danger text-white' : 'bg-surface-muted text-surface-subtle'}`}>
                      {completed ? '✓' : broken ? '✕' : index + 1}
                    </span>
                    <span className={`text-xs ${active ? 'font-semibold text-primary-strong' : broken ? 'font-semibold text-danger-strong' : 'text-surface-subtle'}`}>{step.label}</span>
                    <span className="sr-only">{STEP_STATE_WORD[state]}</span>
                  </li>
                )
              })}
            </ol>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-surface-subtle">
              <p className="min-w-0 break-words" role={failed ? 'alert' : undefined}>{description}</p>
              {live ? <p className="shrink-0 tabular-nums">{formatElapsed(elapsed)} elapsed</p> : null}
            </div>
          </div>
        </div>
      </div>
      {review || failed ? (
        <div className="px-4 pb-4 sm:px-5">
          <Link href={review ? guidedReviewHref(analysis.id) : `/analyses/${encodeURIComponent(analysis.id)}`} className="inline-flex min-h-9 items-center text-sm font-medium text-primary-strong underline underline-offset-2">
            {review ? 'Review profile and prompts' : 'View failure details'} →
          </Link>
        </div>
      ) : null}
      <div
        {...(live ? { role: 'progressbar', 'aria-label': `Analysis progress for ${target}`, 'aria-valuenow': progress, 'aria-valuemin': 0, 'aria-valuemax': 100 } : {})}
        className="h-1 bg-surface-muted"
      >
        <div className={`h-full motion-safe:transition-[width] motion-safe:duration-500 ${failed ? 'bg-danger' : 'bg-primary'}`} style={{ width: `${progress}%` }} />
      </div>
    </article>
  )
}
