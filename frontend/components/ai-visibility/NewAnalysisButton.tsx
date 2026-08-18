'use client'

import { useStartNewAnalysis } from '@/components/ai-visibility/useStartNewAnalysis'

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

  return (
    <button
      type="button"
      onClick={startNew}
      className={`inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-surface-border bg-surface px-4 text-sm font-medium text-surface-foreground shadow-sm transition-colors hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:w-auto ${className}`.trimEnd()}
    >
      <PlusIcon />
      New analysis
    </button>
  )
}
