import Link from 'next/link'
import { guidedReviewHref } from '@/lib/analysis-route'

/** Points a bound run at the guided review wizard on AI Visibility Overview. */
export default function GuidedReviewLinkPanel({
  analysisId,
  className = 'mt-6 space-y-3',
}: {
  analysisId: string
  className?: string
}) {
  return (
    <div className={className}>
      <p className="text-sm text-surface-subtle" role="status">
        This guided run is waiting for your review before measurement starts.
      </p>
      <Link
        href={guidedReviewHref(analysisId)}
        className="text-sm font-medium text-primary-strong underline underline-offset-2"
      >
        Review profile and prompts
      </Link>
    </div>
  )
}
