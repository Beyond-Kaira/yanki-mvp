'use client'

import Link from 'next/link'
import type { UserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

export default function AnalysisQuotaChip({
  quota,
  historyHref,
}: {
  quota: UserAnalysisQuota
  historyHref?: string
}) {
  const full = quota.used >= quota.limit

  return (
    <p
      className={`text-sm ${full ? 'text-warning-strong' : 'text-surface-subtle'}`}
      aria-live="polite"
    >
      <span className="font-medium tabular-nums">
        {quota.used} / {quota.limit}
      </span>{' '}
      analyses active
      {full ? historyHref ? (
        <Link href={historyHref} aria-label="Open your analyses" className="underline underline-offset-2"> — delete one to run another</Link>
      ) : ' — delete one to run another' : null}
    </p>
  )
}
