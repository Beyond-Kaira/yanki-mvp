'use client'

import type { AnalysisStatus, PipelineStep } from '@/lib/contracts'
import { GEO_LLM_MODELS, modelSlugLabel } from '@/lib/engines'
import {
  ANALYSIS_STEPS as STEPS, analysisStepState, STEP_STATE_WORD as STATE_WORD,
  STEP_DESCRIPTIONS, STEP_PHRASES, type StepState,
} from '@/lib/steps'
import { formatElapsed, useElapsedSeconds } from '@/components/useElapsedSeconds'

// The backend does not report per-model completion, so the panel only ever
// shows all configured models as being asked; no fabricated checkmarks.
const EXECUTE_MODELS = GEO_LLM_MODELS.map(modelSlugLabel)

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

interface StepProgressProps {
  status: AnalysisStatus
  progress: number
  currentStep: PipelineStep | null
  // `created_at` off the envelope; the elapsed counter reads from it.
  createdAt?: string | null
}

export default function StepProgress({
  status,
  progress,
  currentStep,
  createdAt = null,
}: StepProgressProps) {
  const isFailed = status === 'failed'
  const elapsed = useElapsedSeconds(createdAt, !isFailed)

  const activeStep = STEPS.find(
    (_, index) => analysisStepState(index, status, progress, currentStep) === 'active',
  )
  const headline =
    status === 'queued'
      ? 'Starting soon…'
      : activeStep
        ? `${capitalize(STEP_PHRASES[activeStep.key])}…`
        : 'Analyzing…'
  const subline =
    status === 'queued'
      ? 'Your analysis is queued.'
      : 'This takes a few minutes.'

  return (
    <div className="space-y-6">
      {status !== 'failed' ? (
        <div className="flex items-baseline justify-between gap-4">
          <div className="space-y-1">
            <p
              aria-live="polite"
              className="text-lg font-semibold text-surface-foreground"
            >
              {headline}
            </p>
            <p className="text-sm text-surface-subtle">{subline}</p>
          </div>
          <p className="shrink-0 text-xs tabular-nums text-surface-subtle">
            {formatElapsed(elapsed)} elapsed
          </p>
        </div>
      ) : null}

      <ol className="space-y-3">
        {STEPS.map((step, index) => {
          const state = analysisStepState(index, status, progress, currentStep)
          return (
            <li key={step.key} className="flex items-start gap-3">
              <span className={dotClass(state)} aria-hidden="true">
                {state === 'done' ? '✓' : state === 'failed' ? '✕' : index + 1}
              </span>
              <span className="pt-1.5">
                <span className={labelClass(state)}>{step.label}</span>
                {state === 'active' ? (
                  <span className="mt-0.5 block text-xs text-surface-subtle">
                    {STEP_DESCRIPTIONS[step.key]}
                  </span>
                ) : null}
                <span className="sr-only">{STATE_WORD[state]}</span>
              </span>
            </li>
          )
        })}
      </ol>

      {activeStep?.key === 'execute' ? <EnginePanel /> : null}

      {/* Progress semantics only while the run is live: polling has already
          stopped on the failed screen, so announcing an in-progress operation
          there contradicts the FailureCard alert. The bar stays as a visual
          record of how far the run got. */}
      <div
        {...(isFailed
          ? {}
          : {
              role: 'progressbar',
              'aria-label': 'Analysis progress',
              'aria-valuenow': progress,
              'aria-valuemin': 0,
              'aria-valuemax': 100,
            })}
        className="h-2 w-full overflow-hidden rounded-full bg-surface-border"
      >
        <div
          className={`h-full rounded-full motion-safe:transition-[width] motion-safe:duration-500 ${
            status === 'failed' ? 'bg-danger' : 'bg-primary'
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}

// Shown only while the execute step is active: the wait is dominated by the
// multi-LLM fan-out via OpenRouter, so name the models being asked. All chips
// animate together — per-model completion is not reported by the backend.
function EnginePanel() {
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4">
      <p className="text-xs text-surface-subtle">
        Asking {EXECUTE_MODELS.length} models via OpenRouter the questions your
        buyers ask
      </p>
      <ul className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {EXECUTE_MODELS.map((label, index) => (
          <li
            key={label}
            className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-muted px-3 py-2.5"
          >
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-full bg-primary motion-safe:animate-pulse"
              style={{ animationDelay: `${index * 0.3}s` }}
            />
            <span className="text-sm font-medium text-surface-foreground">
              {label}
            </span>
            <span aria-hidden="true" className="ml-auto text-xs text-surface-subtle">
              asking…
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function dotClass(state: StepState): string {
  const base =
    'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium'
  if (state === 'done') return `${base} bg-success-soft text-success-strong`
  if (state === 'active') return `${base} bg-primary text-white motion-safe:animate-pulse-ring`
  if (state === 'failed') return `${base} bg-danger-soft text-danger-strong`
  return `${base} border border-surface-border bg-surface-muted text-surface-subtle`
}

function labelClass(state: StepState): string {
  if (state === 'done') return 'text-sm font-medium text-surface-foreground'
  if (state === 'active') return 'text-sm font-semibold text-primary'
  if (state === 'failed') return 'text-sm font-semibold text-danger-strong'
  return 'text-sm text-surface-subtle'
}
