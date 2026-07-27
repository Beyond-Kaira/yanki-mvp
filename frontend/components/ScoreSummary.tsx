import ScoreGauge from './ScoreGauge'
import { scoreBand } from '@/lib/score'
import type { ScoreBand } from '@/lib/score'

interface ScoreSummaryProps {
  // GEO score as a whole-number percentage, 0–100.
  score: number
  footprintCount: number
  totalResponses: number
  questionCount: number
  engineCount: number
}

// Plain-language reading of the score band — a restatement of the same ratio
// the gauge shows, never a claim the numbers do not support.
const BAND_SENTENCE: Record<ScoreBand, string> = {
  danger: 'Engines rarely name you when buyers ask about your category.',
  warning: 'You make it into some answers, but most still leave you out.',
  success: 'Engines name you in most of the answers your buyers would read.',
}

// The at-a-glance header of the results screen: the score, what it means in a
// sentence, and the size of the run behind it.
export default function ScoreSummary({
  score,
  footprintCount,
  totalResponses,
  questionCount,
  engineCount,
}: ScoreSummaryProps) {
  const stats = [
    { label: 'Questions', value: questionCount },
    { label: 'Engines', value: engineCount },
    { label: 'Answers', value: totalResponses },
    { label: 'Mentions', value: footprintCount },
  ]

  return (
    <section className="overflow-hidden rounded-xl border border-surface-border bg-white shadow-sm">
      <div className="space-y-3 p-6">
        <ScoreGauge
          score={score}
          footprintCount={footprintCount}
          totalResponses={totalResponses}
        />
        <p className="mx-auto max-w-prose text-center text-sm font-medium text-surface-foreground">
          {BAND_SENTENCE[scoreBand(score)]}
        </p>
      </div>

      {/* gap-px over a border-colored track draws the hairlines, so the cells
          keep clean 1px separators when they wrap to two columns on mobile. */}
      <dl className="grid grid-cols-2 gap-px border-t border-surface-border bg-surface-border sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-white px-3 py-4 text-center">
            <dd className="text-xl font-semibold tabular-nums text-surface-foreground">
              {stat.value}
            </dd>
            <dt className="text-xs uppercase tracking-wider text-surface-subtle">
              {stat.label}
            </dt>
          </div>
        ))}
      </dl>
    </section>
  )
}
