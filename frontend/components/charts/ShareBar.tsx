import type { CompetitorMention } from '@/lib/insights'
import ChartTooltip from './ChartTooltip'

interface ShareBarProps {
  label: string
  brandName: string
  brandAnswers: number
  competitors: CompetitorMention[]
}

// One engine's mention share: how many of its answers named the brand versus
// each competitor, counted in ANSWERS (not raw string occurrences), stacked
// end to end. Every segment is a tooltip target and the brand segment's count
// is printed inline — colour is never the only way to read the split.
export default function ShareBar({ label, brandName, brandAnswers, competitors }: ShareBarProps) {
  const total = brandAnswers + competitors.reduce((sum, c) => sum + c.answers, 0)
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0)
  const competitorClasses = ['bg-surface-subtle/60', 'bg-surface-subtle/40', 'bg-surface-subtle/25']

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-surface-subtle">
        <span>{label}</span>
        <span className="tabular-nums">
          {total > 0 ? `${pct(brandAnswers)}% you` : 'no answers named a brand'}
        </span>
      </div>
      <div className="flex h-4 w-full overflow-hidden rounded" role="img" aria-label={`${label}: ${brandName} named in ${brandAnswers} answers; ${competitors.map((c) => `${c.name} in ${c.answers}`).join(', ')}`}>
        {total === 0 ? (
          <div className="h-full w-full bg-surface-muted" />
        ) : (
          <>
            <ChartTooltip
              content={`${brandName}: ${brandAnswers} answers (${pct(brandAnswers)}%)`}
              style={{ width: `${pct(brandAnswers)}%`, flexShrink: 0 }}
            >
              <div className="h-full w-full bg-primary" />
            </ChartTooltip>
            {competitors.map((c, i) => (
              <ChartTooltip
                key={c.name}
                content={`${c.name}: ${c.answers} answers (${pct(c.answers)}%)`}
                style={{ width: `${pct(c.answers)}%`, flexShrink: 0 }}
              >
                <div className={`h-full w-full ${competitorClasses[i % competitorClasses.length]}`} />
              </ChartTooltip>
            ))}
          </>
        )}
      </div>
      {total > 0 ? (
        <ul className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-surface-subtle">
          <li className="inline-flex items-center gap-1">
            <span className="h-2 w-2 shrink-0 rounded-sm bg-primary" aria-hidden="true" />
            {brandName} · {pct(brandAnswers)}%
          </li>
          {competitors.map((c, i) => (
            <li key={c.name} className="inline-flex items-center gap-1">
              <span
                className={`h-2 w-2 shrink-0 rounded-sm ${competitorClasses[i % competitorClasses.length]}`}
                aria-hidden="true"
              />
              {c.name} · {pct(c.answers)}%
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
