import type { EntityLandscape as EntityLandscapeData, Ownership } from '@/lib/insights'

interface EntityLandscapeProps {
  landscape: EntityLandscapeData
  scoredAnswers: number
}

const OWNERSHIP_FILL: Record<Ownership, string> = {
  ours: 'bg-primary',
  shared: 'bg-signal',
  competitor: 'bg-surface-subtle/50',
  unclaimed: 'bg-surface-muted',
}

// Spelled out in full sentences under every bar, so no row depends on a
// legend, a colour, or a hover to be understood on its own.
const OWNERSHIP_TEXT: Record<Ownership, (brand: string) => string> = {
  ours: () => 'This is the brand itself.',
  shared: (brand) => `${brand} is named in the same answers as this.`,
  competitor: (brand) => `${brand} is never named in the same answers as this.`,
  unclaimed: () => 'Never appears in any answer.',
}

// Module 4: the full universe of names the engines used for this category —
// brands and topics alike — ranked by how often they came up. A neutral
// market map: it does not distinguish which rows are the brand's own terms —
// that question belongs to EntityCoverage, shown above this on the same page
// (design §3.4).
export default function EntityLandscape({ landscape, scoredAnswers }: EntityLandscapeProps) {
  const brand = landscape.entities.find((e) => e.ownership === 'ours')?.name ?? 'The brand'
  const max = Math.max(...landscape.entities.map((e) => e.answers), 1)

  return (
    <section className="space-y-4 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="landscape-heading">
      <div>
        <h2 id="landscape-heading" className="text-lg font-semibold text-surface-foreground">
          Industry entity landscape
        </h2>
        <p className="text-sm text-surface-subtle">
          Every brand and topic name the engines used, ranked by how many of the {scoredAnswers} scored
          answers it appeared in.
        </p>
      </div>

      <ul className="space-y-2">
        {landscape.entities.map((entity) => {
          const pct = Math.round((entity.answers / max) * 100)
          return (
            <li key={entity.name} className="rounded-lg border border-surface-border p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-surface-foreground">{entity.name}</span>
              </div>
              <div className="mt-2 flex items-center gap-3">
                <div className="h-3 flex-1 overflow-hidden rounded bg-surface-muted">
                  <div className={`h-full rounded ${OWNERSHIP_FILL[entity.ownership]}`} style={{ width: `${pct}%` }} />
                </div>
                <span className="whitespace-nowrap text-xs tabular-nums text-surface-subtle">
                  {entity.answers}/{scoredAnswers} answers
                </span>
              </div>
              <p className="mt-1.5 text-xs text-surface-subtle">{OWNERSHIP_TEXT[entity.ownership](brand)}</p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
