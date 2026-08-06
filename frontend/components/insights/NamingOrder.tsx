import { engineLabel } from '@/lib/engines'
import type { EngineInsight } from '@/lib/insights'
import RatioBar from '@/components/charts/RatioBar'

interface NamingOrderProps {
  engines: EngineInsight[]
}

// Of the answers that named the brand, how many named it FIRST — before any
// competitor. A ratio out of the answers that named the brand (not out of all
// scored answers), so it reads with the same n/m bar as everywhere else in
// the dashboard instead of an abstract decimal average. An engine that never
// named the brand has nothing to rank, so it gets its own "not named" row
// rather than a bar reading 0/0.
export default function NamingOrder({ engines }: NamingOrderProps) {
  return (
    <section className="space-y-4 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="order-heading">
      <div>
        <h2 id="order-heading" className="text-lg font-semibold text-surface-foreground">
          Naming order
        </h2>
        <p className="text-sm text-surface-subtle">
          Of the answers naming the brand, how many named it before any competitor.
        </p>
      </div>
      <ul className="divide-y divide-surface-border rounded-lg border border-surface-border">
        {engines.map((engine) => (
          <li key={engine.engine} className="px-3 py-2.5">
            {engine.mentioned === 0 ? (
              <div className="flex items-center justify-between text-sm">
                <span className="text-surface-subtle">{engineLabel(engine.engine)}</span>
                <span className="text-surface-subtle">not named</span>
              </div>
            ) : (
              <>
                <RatioBar
                  label={engineLabel(engine.engine)}
                  mentioned={engine.firstMentions}
                  total={engine.mentioned}
                  compact
                />
                <p className="mt-1 pl-[7rem] text-xs text-surface-subtle">
                  {engine.firstMentions} of {engine.mentioned} answers named you before any competitor.
                </p>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
