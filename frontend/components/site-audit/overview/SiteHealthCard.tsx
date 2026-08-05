const RADIUS = 80
const CIRCUMFERENCE = Math.PI * RADIUS
const ARC_PATH = `M20 100 A${RADIUS} ${RADIUS} 0 0 1 180 100`

export default function SiteHealthCard({
  score,
  delta,
}: {
  score: number | null
  delta?: string | null
}) {
  const normalizedScore = score == null ? 0 : Math.min(100, Math.max(0, score))
  const dashOffset = CIRCUMFERENCE * (1 - normalizedScore / 100)

  return (
    <article className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm">
      <div className="flex items-center gap-1.5">
        <h2 className="text-base font-semibold text-surface-foreground">Site health</h2>
        <span
          aria-hidden="true"
          title="Calculated from the scorable pages and technical findings in this run."
          className="flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold text-surface-subtle ring-1 ring-inset ring-surface-border"
        >
          i
        </span>
      </div>

      <div className="relative mx-auto mt-3 w-full max-w-[240px]">
        <svg
          viewBox="0 0 200 112"
          className="w-full"
          role="img"
          aria-label={score == null ? 'Site health is not scorable' : `Site health ${score}%`}
        >
          <path
            d={ARC_PATH}
            fill="none"
            stroke="currentColor"
            strokeWidth="14"
            strokeLinecap="round"
            className="text-surface-border"
          />
          <path
            d={ARC_PATH}
            fill="none"
            stroke="currentColor"
            strokeWidth="14"
            strokeLinecap="round"
            className="text-primary transition-[stroke-dashoffset]"
            strokeDasharray={`${CIRCUMFERENCE} ${CIRCUMFERENCE}`}
            strokeDashoffset={dashOffset}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
          <span className="text-4xl font-semibold tracking-tight text-surface-foreground">
            {score == null ? '—' : `${score}%`}
          </span>
          <span className="mt-0.5 text-xs text-surface-subtle">
            {score == null ? 'Not scorable' : (delta ?? 'First audit')}
          </span>
        </div>
      </div>

      <ul className="mt-3 space-y-2 border-t border-surface-border pt-4">
        <li className="flex items-center gap-2 text-sm">
          <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-primary" />
          <span className="flex-1 text-surface-subtle">Your site</span>
          <span className="font-semibold text-surface-foreground">
            {score == null ? '—' : `${score}%`}
          </span>
        </li>
      </ul>
    </article>
  )
}
