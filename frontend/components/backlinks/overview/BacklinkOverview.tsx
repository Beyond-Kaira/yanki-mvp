'use client'

import {
  ANCHOR_CLASS_LABELS,
  TOXICITY_TONE,
  formatCount,
  formatDate,
  formatMetric,
  formatPercent,
  readAuthorityCaveats,
  readAuthorityComponents,
} from '@/components/backlinks/backlinkUtils'
import type { BacklinkSummary } from '@/lib/contracts'

export default function BacklinkOverview({
  summary,
  onViewDomains,
}: {
  summary: BacklinkSummary
  onViewDomains: () => void
}) {
  const terms = readAuthorityComponents(summary.authority_components)
  const caveats = readAuthorityCaveats(summary.authority_components)
  const anchors = summary.anchors
  const velocity = summary.velocity ?? []

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <AuthorityCard
        value={summary.authority}
        version={summary.authority_version}
        terms={terms}
        caveats={caveats}
      />
      <VelocityCard velocity={velocity} />
      <AnchorsCard anchors={anchors} />
      <ToxicityCard toxicity={summary.toxicity} onViewDomains={onViewDomains} />
    </div>
  )
}

function AuthorityCard({
  value,
  version,
  terms,
  caveats,
}: {
  value: number | null | undefined
  version: string | null | undefined
  terms: ReturnType<typeof readAuthorityComponents>
  caveats: string[]
}) {
  const total = terms.reduce((sum, term) => sum + term.points, 0)

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm sm:p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold text-surface-foreground">
          Yanki Authority
        </h2>
        <span className="text-3xl font-semibold text-surface-foreground">
          {formatMetric(value)}
        </span>
      </div>
      <p className="mt-1 text-sm text-surface-subtle">
        A published formula, not a black box{version ? ` (${version})` : ''}. The
        terms below sum to the score.
      </p>

      {terms.length ? (
        <>
          {/* dl > div > dt + dd only. The explaining sentence rides inside the
              dd rather than as a sibling paragraph, which would be invalid
              markup and is exactly what axe fails the page for. */}
          <dl className="mt-4 space-y-3">
            {terms.map((term) => (
              <div
                key={term.key}
                className="flex flex-wrap items-baseline justify-between gap-x-3"
              >
                <dt className="text-sm font-medium text-surface-foreground">
                  {term.label}
                </dt>
                <dd className="text-sm text-surface-foreground">
                  {term.points.toFixed(1)}
                  <span className="text-surface-subtle"> / {term.weight}</span>
                  {term.explains ? (
                    <span className="mt-0.5 block w-full text-xs text-surface-subtle">
                      {term.explains}
                    </span>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 border-t border-surface-border pt-3 text-sm text-surface-subtle">
            Total {total.toFixed(1)}
          </p>
        </>
      ) : (
        <p className="mt-4 text-sm text-surface-subtle">
          No score yet — run a refresh to compute one.
        </p>
      )}

      {caveats.length ? (
        <div className="mt-4 rounded-lg bg-surface-muted p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-surface-subtle">
            What this score does not say
          </h3>
          <ul className="mt-2 space-y-1">
            {caveats.map((caveat) => (
              <li key={caveat} className="text-xs text-surface-subtle">
                {caveat}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function VelocityCard({
  velocity,
}: {
  velocity: BacklinkSummary['velocity']
}) {
  const points = velocity ?? []
  const peak = Math.max(1, ...points.map((p) => Math.max(p.new, p.lost)))

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm sm:p-6">
      <h2 className="text-lg font-semibold text-surface-foreground">
        Link velocity
      </h2>
      <p className="mt-1 text-sm text-surface-subtle">
        New and lost links per refresh, oldest first.
      </p>

      {!points.length ? (
        <p className="mt-4 text-sm text-surface-subtle">
          No refreshes recorded yet.
        </p>
      ) : (
        <table className="mt-4 w-full text-left text-sm">
          <caption className="sr-only">
            New and lost backlinks for each recorded refresh
          </caption>
          <thead className="text-xs font-medium uppercase tracking-wide text-surface-subtle">
            <tr>
              <th scope="col" className="py-2">Refresh</th>
              <th scope="col" className="py-2 text-right">New</th>
              <th scope="col" className="py-2 text-right">Lost</th>
              <th scope="col" className="py-2 text-right">Authority</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {points.map((point, index) => (
              <tr key={`${point.at ?? 'unknown'}-${index}`}>
                <th scope="row" className="py-2 font-normal text-surface-foreground">
                  {formatDate(point.at)}
                  {/* An unmeasurable refresh is marked in place. Its zero-lost is
                      a refusal to claim, not an observation of stability. */}
                  {point.measurable ? null : (
                    <span className="ml-2 rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning-strong">
                      incomplete
                    </span>
                  )}
                </th>
                <td className="py-2 text-right text-success-strong">
                  +{formatCount(point.new)}
                </td>
                <td className="py-2 text-right text-danger-strong">
                  −{formatCount(point.lost)}
                </td>
                <td className="py-2 text-right text-surface-foreground">
                  {formatMetric(point.authority)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="sr-only">Peak movement in this window: {peak}</p>
    </section>
  )
}

function AnchorsCard({ anchors }: { anchors: BacklinkSummary['anchors'] }) {
  const counts = anchors?.counts ?? {}
  const shares = anchors?.shares ?? {}
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const moneyShare = anchors?.money_anchor_share ?? 0

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm sm:p-6">
      <h2 className="text-lg font-semibold text-surface-foreground">
        Anchor text
      </h2>
      <p className="mt-1 text-sm text-surface-subtle">
        {formatCount(anchors?.total)} anchors across{' '}
        {entries.length} class{entries.length === 1 ? '' : 'es'}.
      </p>

      {!entries.length ? (
        <p className="mt-4 text-sm text-surface-subtle">
          No anchors to analyse yet.
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {entries.map(([anchorClass, count]) => (
            <li key={anchorClass}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-surface-foreground">
                  {ANCHOR_CLASS_LABELS[anchorClass] ?? anchorClass}
                </span>
                <span className="text-surface-subtle">
                  {formatCount(count)} · {formatPercent(shares[anchorClass])}
                </span>
              </div>
              <div
                className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
                aria-hidden="true"
              >
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${Math.round((shares[anchorClass] ?? 0) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      {moneyShare > 0.2 ? (
        <p className="mt-4 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning-strong">
          {formatPercent(moneyShare)} of anchors are exact-match commercial
          phrases — the classic over-optimization pattern.
        </p>
      ) : null}
    </section>
  )
}

function ToxicityCard({
  toxicity,
  onViewDomains,
}: {
  toxicity: BacklinkSummary['toxicity']
  onViewDomains: () => void
}) {
  const bands = toxicity ?? {}
  const order: ('high' | 'medium' | 'low')[] = ['high', 'medium', 'low']

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm sm:p-6">
      <h2 className="text-lg font-semibold text-surface-foreground">
        Toxicity
      </h2>
      <p className="mt-1 text-sm text-surface-subtle">
        Advisory only. Every flag decomposes into the reasons behind it, and
        nothing is disavowed automatically.
      </p>

      <dl className="mt-4 grid grid-cols-3 gap-3">
        {order.map((band) => (
          <div
            key={band}
            className={`rounded-lg px-3 py-3 text-center ${TOXICITY_TONE[band]}`}
          >
            <dt className="text-xs font-medium capitalize">{band}</dt>
            <dd className="mt-1 text-xl font-semibold">
              {formatCount(bands[band] ?? 0)}
            </dd>
          </div>
        ))}
      </dl>

      <button
        type="button"
        onClick={onViewDomains}
        className="mt-4 min-h-[44px] text-sm font-semibold text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        Review referring domains
      </button>
    </section>
  )
}
