import Link from 'next/link'
import type { PipelineStep } from '@/lib/contracts'
import { STEP_PHRASES } from '@/lib/steps'
import StepProgress from './StepProgress'

interface FailedStateProps {
  // What failed, in the sentence "We couldn't finish this ___." The two routes
  // call the same run an analysis and a check.
  subject: string
  reason: string
  step: PipelineStep | null
  progress: number
  retryHref: string
  retryLabel: string
}

// The failure screen for both result routes. It lived in each page as a
// near-identical copy, which meant the rule below — and the copy around it —
// had to be kept in step by hand.
export default function FailedState({
  subject,
  reason,
  step,
  progress,
  retryHref,
  retryLabel,
}: FailedStateProps) {
  return (
    <div className="space-y-6">
      <div
        role="alert"
        className="space-y-3 rounded-xl border border-danger bg-danger-soft p-6"
      >
        <h2 className="text-xl font-semibold text-danger-strong">
          {`We couldn't finish this ${subject}.`}
        </h2>
        {step ? (
          <p className="text-sm font-medium text-surface-foreground">
            It stopped while {STEP_PHRASES[step]}.
          </p>
        ) : null}
        <p className="text-sm text-surface-foreground">{reason}</p>
        <Link
          href={retryHref}
          className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {retryLabel}
        </Link>
      </div>

      {/* The trail exists to point at the step that broke. A run that failed
          before claiming one reports current_step=null, leaving nothing to
          point at — the alert above already carries the outcome, so render no
          trail rather than a row of neutral "waiting" steps. */}
      {step ? (
        <StepProgress status="failed" progress={progress} currentStep={step} />
      ) : null}
    </div>
  )
}
