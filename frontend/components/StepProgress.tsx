'use client'

import { useEffect, useState } from 'react'
import type { AnalysisStatus, PipelineStep } from '@/lib/contracts'

type StepState = 'done' | 'active' | 'failed' | 'pending'

interface StepDef {
  key: PipelineStep
  label: string
  // The `progress` value the backend sets once this step COMPLETES (SPEC).
  threshold: number
}

const STEPS: StepDef[] = [
  { key: 'discovery', label: 'Discovery', threshold: 15 },
  { key: 'kyc', label: 'KYC', threshold: 30 },
  { key: 'prompts', label: 'Prompts', threshold: 45 },
  { key: 'execute', label: 'Executing', threshold: 80 },
  { key: 'footprint', label: 'Footprint', threshold: 90 },
  { key: 'scoring', label: 'Scoring', threshold: 100 },
]

// Present-continuous phrase describing what each step is doing. Shown live for
// the active step, and reused by the failure card ("It stopped while …").
export const STEP_PHRASES: Record<PipelineStep, string> = {
  discovery: 'reading your website',
  kyc: 'building your company profile',
  prompts: 'writing the questions your buyers ask',
  execute: 'asking the AI engines about you',
  footprint: 'checking where you show up',
  scoring: 'scoring your visibility',
}

// One-line explanation of what the ACTIVE step is doing, shown under its
// label so the list reads as narration, not jargon.
const STEP_DESCRIPTIONS: Record<PipelineStep, string> = {
  discovery: "Fetching and reading your site's content.",
  kyc: 'Turning it into a company profile.',
  prompts: 'Generating the questions your buyers ask.',
  execute: 'Running your buyer questions against each engine.',
  footprint: 'Scanning every answer for your brand.',
  scoring: 'Calculating your GEO score.',
}

// Display names for the engine panel, mirroring the backend default panel
// (backend/app/providers/registry.py DEFAULT_PANEL) — update together. The
// backend does not report per-engine completion, so the panel only ever shows
// all engines as being asked; no fabricated checkmarks or counters.
const PANEL_ENGINES = ['Claude', 'ChatGPT', 'Gemini', 'Perplexity']

const STATE_WORD: Record<StepState, string> = {
  done: 'completed',
  active: 'in progress',
  failed: 'failed',
  pending: 'waiting',
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

// Wall-clock seconds since mount — the honest "still moving" signal while the
// backend only reports coarse step boundaries.
function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const startedAt = Date.now()
    const timer = setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  return seconds
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

interface StepProgressProps {
  status: AnalysisStatus
  progress: number
  currentStep: PipelineStep | null
}

export default function StepProgress({
  status,
  progress,
  currentStep,
}: StepProgressProps) {
  const elapsed = useElapsedSeconds()
  const firstPendingIndex = STEPS.findIndex((step) => progress < step.threshold)

  function stateFor(step: StepDef, index: number): StepState {
    if (progress >= step.threshold) return 'done'
    if (status === 'failed') return currentStep === step.key ? 'failed' : 'pending'
    if (status === 'running') {
      if (currentStep === step.key) return 'active'
      if (currentStep === null && index === firstPendingIndex) return 'active'
    }
    return 'pending'
  }

  const activeStep = STEPS.find(
    (step, index) => stateFor(step, index) === 'active',
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
      : 'This usually takes a couple of minutes.'

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
          const state = stateFor(step, index)
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

      <div
        role="progressbar"
        aria-label="Analysis progress"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
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
// fan-out to the engine panel, so name the engines being asked. All chips
// animate together — per-engine completion is not reported by the backend.
function EnginePanel() {
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4">
      <p className="text-xs text-surface-subtle">
        Asking {PANEL_ENGINES.length} AI engines the questions your buyers ask
      </p>
      <ul className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {PANEL_ENGINES.map((engine, index) => (
          <li
            key={engine}
            className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-muted px-3 py-2.5"
          >
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-full bg-primary motion-safe:animate-pulse"
              style={{ animationDelay: `${index * 0.3}s` }}
            />
            <span className="text-sm font-medium text-surface-foreground">
              {engine}
            </span>
            <span className="ml-auto text-xs text-surface-subtle">asking…</span>
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
