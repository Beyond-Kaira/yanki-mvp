import type { SerpVisibility as SerpVisibilityData } from '@/lib/contracts'

interface SerpVisibilityProps {
  serp: SerpVisibilityData
}

// Why a run has no number, in the user's words. The distinction the whole
// feature turns on: we never draw a zero for a measurement we did not take.
const STATUS_NOTES: Record<string, string> = {
  unavailable:
    'We could not read search results for this run, so there is no SERP score. This usually means the search instance was unreachable or every search engine it queries declined to answer.',
  no_topics:
    'This profile did not give us a product category a buyer would search for, so we did not run any searches.',
}

function rankLabel(rank: number | null): string {
  return rank === null ? 'position unknown' : `position ${rank}`
}

// Where the brand appeared in ordinary search results, alongside the GEO score
// for AI answers. Every row is backed by readable text rather than colour, and
// the "not measured" state is rendered explicitly instead of as a zero.
export default function SerpVisibility({ serp }: SerpVisibilityProps) {
  const measured = serp.score !== null
  const percent = measured ? Math.round((serp.score ?? 0) * 100) : 0
  const note = STATUS_NOTES[serp.status]
  // Unreadable pages are excluded from the score, so they are listed separately
  // rather than mixed in with genuine misses.
  const readable = serp.checks.filter((check) => check.hit !== null)
  const unreadable = serp.checks.filter((check) => check.hit === null)

  return (
    <section className="space-y-3" aria-labelledby="serp-visibility-heading">
      <h2
        id="serp-visibility-heading"
        className="text-xl font-semibold text-surface-foreground"
      >
        Search results visibility
      </h2>

      {measured ? (
        <div className="rounded-lg border border-surface-border bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-surface-foreground">
              Appeared in {serp.hits} of {serp.queries} searches
            </span>
            <span className="text-sm text-surface-subtle">{percent}%</span>
          </div>
          <div
            role="progressbar"
            aria-label={`Appeared in ${serp.hits} of ${serp.queries} searches`}
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-border"
          >
            <div
              className="h-full rounded-full bg-primary motion-safe:transition-[width] motion-safe:duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      ) : (
        <p className="text-sm text-surface-subtle">
          {note ?? 'SERP visibility was not measured for this run.'}
        </p>
      )}

      {readable.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full min-w-[520px] table-fixed border-collapse text-left text-sm">
            <thead>
              <tr className="bg-surface-muted text-xs font-medium uppercase tracking-wider text-surface-subtle">
                <th scope="col" className="w-[40%] px-4 py-3">
                  Search
                </th>
                <th scope="col" className="w-[16%] px-4 py-3">
                  Appeared
                </th>
                <th scope="col" className="w-[44%] px-4 py-3">
                  Top matching result
                </th>
              </tr>
            </thead>
            <tbody>
              {readable.map((check, index) => (
                <tr
                  key={check.id}
                  className={index % 2 === 1 ? 'bg-surface-zebra' : 'bg-white'}
                >
                  <td className="px-4 py-3">
                    <span
                      className="block truncate text-surface-foreground"
                      title={check.query}
                    >
                      {check.query}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {check.hit ? (
                      <span className="inline-flex items-center rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-strong">
                        Yes, {rankLabel(check.rank)}
                      </span>
                    ) : (
                      <span className="text-xs text-surface-subtle">No</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {check.matched_url ? (
                      <span
                        className="block truncate font-mono text-xs text-surface-foreground"
                        title={check.matched_snippet ?? check.matched_url}
                      >
                        {check.matched_url}
                      </span>
                    ) : (
                      <span className="text-xs text-surface-subtle">
                        Not found in the first {check.result_count} results.
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {unreadable.length > 0 ? (
        <p className="text-sm text-surface-subtle">
          {unreadable.length}{' '}
          {unreadable.length === 1 ? 'search' : 'searches'} could not be read and{' '}
          {unreadable.length === 1 ? 'was' : 'were'} left out of the score.
        </p>
      ) : null}
    </section>
  )
}
