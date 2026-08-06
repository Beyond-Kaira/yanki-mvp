import type { EntityCoverage as EntityCoverageData } from '@/lib/insights'

interface EntityCoverageProps {
  coverage: EntityCoverageData
}

const PRESENCE_STYLE: Record<string, { chip: string; text: (n: number) => string }> = {
  present: {
    chip: 'bg-success-soft text-success-strong',
    text: (n) => `Shows up in ${n} of the scored answers, alongside the brand.`,
  },
  'high-impact-missing': {
    chip: 'bg-danger-soft text-danger-strong',
    text: (n) => `Shows up in ${n} of the scored answers — but never alongside the brand.`,
  },
  missing: {
    chip: 'bg-surface-muted text-surface-subtle',
    text: () => `Never appears in any scored answer.`,
  },
}

// The brand's own vocabulary (products/services/use cases/keywords/category)
// checked against the scored answers: does the brand's own language actually
// show up in what the engines say? Every term is spelled out with a plain
// sentence — no reader needs to remember what a colour or a badge means
// (design §3.3).
export default function EntityCoverage({ coverage }: EntityCoverageProps) {
  const highImpactMissing = coverage.entities.filter((e) => e.presence === 'high-impact-missing').length
  const pct = coverage.total > 0 ? Math.round((coverage.present / coverage.total) * 100) : 0

  return (
    <section className="space-y-4 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="coverage-heading">
      <div>
        <h2 id="coverage-heading" className="text-lg font-semibold text-surface-foreground">
          Entity coverage
        </h2>
        <p className="text-sm text-surface-subtle">
          The brand&apos;s own terms — from its profile — checked against what the engines actually said.
        </p>
      </div>

      <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-surface-border bg-surface-border sm:grid-cols-3">
        <div className="flex flex-col bg-white p-3 text-center">
          <dt className="text-xs font-medium uppercase text-surface-subtle">Your coverage</dt>
          <dd className="mt-1 text-xl font-semibold tabular-nums text-surface-foreground">
            {coverage.present}/{coverage.total} · {pct}%
          </dd>
          <dd className="mt-1 text-xs font-normal text-surface-subtle">
            of your own terms show up in answers that also name you
          </dd>
        </div>
        <div className="flex flex-col bg-white p-3 text-center">
          <dt className="text-xs font-medium uppercase text-surface-subtle">High-impact missing</dt>
          <dd className="mt-1 text-xl font-semibold tabular-nums text-danger-strong">{highImpactMissing}</dd>
          <dd className="mt-1 text-xs font-normal text-surface-subtle">
            terms the engines discuss, always without you
          </dd>
        </div>
        <div className="flex flex-col bg-white p-3 text-center">
          <dt className="text-xs font-medium uppercase text-surface-subtle">Your terms tracked</dt>
          <dd className="mt-1 text-xl font-semibold tabular-nums text-surface-foreground">{coverage.total}</dd>
          <dd className="mt-1 text-xs font-normal text-surface-subtle">
            total terms from your own profile
          </dd>
        </div>
      </dl>

      <ul className="space-y-2">
        {coverage.entities.map((entity) => {
          const style = PRESENCE_STYLE[entity.presence ?? 'missing']
          return (
            <li key={entity.name} className="rounded-lg border border-surface-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-surface-foreground">{entity.name}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.chip}`}>
                  {entity.presence === 'present'
                    ? 'Present'
                    : entity.presence === 'high-impact-missing'
                      ? 'High-impact missing'
                      : 'Missing'}
                </span>
              </div>
              <p className="mt-1.5 text-xs text-surface-subtle">{style.text(entity.answers)}</p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
