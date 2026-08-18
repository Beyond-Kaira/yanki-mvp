'use client'

import type { UserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

export default function AnalysisQuotaChip({
  quota,
}: {
  quota: UserAnalysisQuota
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
      {full ? ' — delete one to run another' : null}
    </p>
  )
}
