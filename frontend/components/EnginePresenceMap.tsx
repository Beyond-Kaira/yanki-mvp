import type { EnginePresence } from '@/lib/contracts'
import { engineLabel } from '@/lib/engines'

interface EnginePresenceMapProps {
  presence: EnginePresence[]
}

// Per-engine footprint: how many answers from each engine named the brand.
// Never color-only — every bar is backed by the "N of M answers" count and an
// accessible progressbar label (brandkit v2 §7).
export default function EnginePresenceMap({ presence }: EnginePresenceMapProps) {
  return (
    <section className="space-y-3" aria-labelledby="engine-presence-heading">
      <h2
        id="engine-presence-heading"
        className="text-xl font-semibold text-surface-foreground"
      >
        Where you show up
      </h2>
      {/* One row per engine instead of a stacked card: name, bar, and count
          share a line so N engines cost N rows of height, not N cards. */}
      <ul className="divide-y divide-surface-border rounded-lg border border-surface-border bg-white">
        {presence.map((engine) => {
          const label = engineLabel(engine.engine)
          const pct =
            engine.total > 0
              ? Math.round((engine.mentioned / engine.total) * 100)
              : 0
          // An engine that returned nothing is listed rather than dropped, and
          // says so — "0 of 0 answers" would read as a measured result.
          const countText =
            engine.total > 0
              ? `Mentioned in ${engine.mentioned} of ${engine.total} answers`
              : 'No answers recorded'
          return (
            <li
              key={engine.engine}
              className="flex items-center gap-3 px-4 py-2.5"
            >
              <span className="w-20 shrink-0 truncate text-sm font-medium text-surface-foreground">
                {label}
              </span>
              <div
                role="progressbar"
                aria-label={`${label}: ${countText}`}
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-border"
              >
                <div
                  className="h-full rounded-full bg-primary motion-safe:transition-[width] motion-safe:duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-24 shrink-0 text-right text-xs tabular-nums text-surface-subtle">
                {engine.total > 0 ? `${engine.mentioned} / ${engine.total}` : '—'}
              </span>
              {/* Screen readers get the full sentence the visible row now only
                  implies in numbers. */}
              <span className="sr-only">{countText}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
