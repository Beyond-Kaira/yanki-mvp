import { engineLabel } from '@/lib/engines'
import type { EngineInsight } from '@/lib/insights'
import ShareBar from '@/components/charts/ShareBar'

interface MentionShareProps {
  brand: string
  engines: EngineInsight[]
}

// Per engine, how its answers split between the brand and the competitors
// named alongside it — in answers, never raw string occurrences (design §3.1).
export default function MentionShare({ brand, engines }: MentionShareProps) {
  return (
    <section className="space-y-4 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="share-heading">
      <div>
        <h2 id="share-heading" className="text-lg font-semibold text-surface-foreground">
          Mention share
        </h2>
        <p className="text-sm text-surface-subtle">
          {brand} vs. the competitors named alongside it, per engine.
        </p>
      </div>
      <div className="space-y-3 rounded-lg bg-surface-muted p-3">
        {engines.map((engine) => (
          <ShareBar
            key={engine.engine}
            label={engineLabel(engine.engine)}
            brandName={brand}
            brandAnswers={engine.brandAnswers}
            competitors={engine.competitors}
          />
        ))}
      </div>
    </section>
  )
}
