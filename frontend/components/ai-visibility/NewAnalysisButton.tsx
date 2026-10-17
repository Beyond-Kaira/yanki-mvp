'use client'

import Link from 'next/link'
import { useStartNewAnalysis } from '@/components/ai-visibility/useStartNewAnalysis'
import { useUserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

function PlusIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
      className="h-4 w-4 shrink-0"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

export default function NewAnalysisButton({
  path = '/ai-visibility',
  className = '',
}: {
  path?: string
  className?: string
}) {
  const startNew = useStartNewAnalysis(path)
  const { quota, atLimit, loading: quotaLoading } = useUserAnalysisQuota()

  const limitMessage =
    quota != null
      ? `You have reached the limit of ${quota.limit} active analyses. Delete a finished run from your history to free a slot.`
      : 'Analysis limit reached. Delete a finished run from your history to free a slot.'

  const blocked = !quotaLoading && atLimit

  return (
    <div className="flex flex-col items-stretch gap-2 sm:items-end">
      <button
        type="button"
        onClick={() => {
          if (blocked) return
          startNew()
        }}
        disabled={blocked}
        title={blocked ? limitMessage : undefined}
        aria-describedby={blocked ? 'new-analysis-limit-hint' : undefined}
        className={`inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-surface-border bg-surface px-4 text-sm font-medium text-surface-foreground shadow-sm transition-colors hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto ${className}`.trimEnd()}
      >
        <PlusIcon />
        New analysis
      </button>
      {blocked ? (
        <p
          id="new-analysis-limit-hint"
          className="max-w-xs text-right text-xs text-warning-strong"
          role="status"
        >
          {limitMessage}{' '}
          <Link
            href="/analyses"
            className="font-medium text-primary-strong underline underline-offset-2"
          >
            Open your analyses
          </Link>
        </p>
      ) : null}
    </div>
  )
}
