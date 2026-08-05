export default function SiteHealthCard({ score }: { score: number | null }) {
  const normalizedScore = score == null ? 0 : Math.min(100, Math.max(0, score))
  const angle = normalizedScore * 3.6

  return (
    <article className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm">
      <div>
        <h2 className="text-base font-semibold text-surface-foreground">Site health</h2>
        <p className="mt-1 text-xs leading-relaxed text-surface-subtle">
          Calculated from the scorable pages and technical findings in this run.
        </p>
      </div>

      <div className="mt-5 flex flex-col items-center">
        <div
          role="img"
          aria-label={
            score == null ? 'Site health is not scorable' : `Site health ${score}%`
          }
          className="relative h-44 w-44 rounded-full bg-surface-border text-primary"
        >
          <div
            aria-hidden="true"
            className="absolute inset-0 rounded-full"
            style={{
              background: `conic-gradient(currentColor ${angle}deg, transparent ${angle}deg)`,
            }}
          />
          <div className="absolute inset-4 flex flex-col items-center justify-center rounded-full bg-surface">
            <span className="text-4xl font-semibold tracking-tight text-surface-foreground">
              {score == null ? '—' : `${score}%`}
            </span>
            <span className="mt-1 text-xs text-surface-subtle">
              {score == null ? 'Not scorable' : 'Latest audit'}
            </span>
          </div>
        </div>
      </div>
    </article>
  )
}
