import type {
  EntityCoverage as EntityCoverageData,
  EntityStat,
  Presence,
} from "@/lib/insights";

interface EntityCoverageProps {
  coverage: EntityCoverageData;
  brand: string;
  scoredAnswers: number;
}

interface CoverageGroup {
  presence: Presence;
  label: string;
  description: string;
  dot: string;
  stroke: string;
}

const GROUPS: CoverageGroup[] = [
  {
    presence: "present",
    label: "Covered",
    description: "Seen in an answer that also names your brand.",
    dot: "bg-success",
    stroke: "stroke-success",
  },
  {
    presence: "high-impact-missing",
    label: "Opportunity",
    description: "Seen in answers, but never together with your brand.",
    dot: "bg-warning",
    stroke: "stroke-warning",
  },
  {
    presence: "missing",
    label: "Not observed",
    description: "Not seen in any scored answer.",
    dot: "bg-surface-subtle/50",
    stroke: "stroke-surface-subtle/30",
  },
];

function percent(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((value / total) * 100);
}

function entitiesFor(entities: EntityStat[], presence: Presence): EntityStat[] {
  return entities
    .filter((entity) => (entity.presence ?? "missing") === presence)
    .sort(
      (a, b) =>
        b.answers - a.answers || a.name.localeCompare(b.name, undefined),
    );
}

// Coverage measures the brand profile's vocabulary, not answer visibility.
// One tracked term is covered when at least one scored answer contains both
// that term and the measured brand.
export default function EntityCoverage({
  coverage,
  brand,
  scoredAnswers,
}: EntityCoverageProps) {
  const grouped = Object.fromEntries(
    GROUPS.map((group) => [
      group.presence,
      entitiesFor(coverage.entities, group.presence),
    ]),
  ) as Record<Presence, EntityStat[]>;

  const coveredPct = percent(grouped.present.length, coverage.total);
  const opportunityPct = percent(
    grouped["high-impact-missing"].length,
    coverage.total,
  );
  const missingPct = Math.max(0, 100 - coveredPct - opportunityPct);
  const slices = [
    { ...GROUPS[0], value: coveredPct, offset: 0 },
    { ...GROUPS[1], value: opportunityPct, offset: -coveredPct },
    {
      ...GROUPS[2],
      value: missingPct,
      offset: -(coveredPct + opportunityPct),
    },
  ];

  return (
    <section
      className="overflow-hidden rounded-xl border border-surface-border bg-white shadow-sm"
      aria-labelledby="coverage-heading"
    >
      <div className="px-5 py-5 sm:px-6">
        <h2
          id="coverage-heading"
          className="text-xl font-semibold text-surface-foreground"
        >
          Entity coverage
        </h2>
        <p className="mt-1 text-sm text-surface-subtle">
          How much of the {brand} profile vocabulary is associated with the
          brand in AI answers.
        </p>
      </div>

      <div className="grid items-center gap-6 border-y border-surface-border bg-surface-muted/60 p-5 sm:p-6 md:grid-cols-[13rem_minmax(0,1fr)]">
        <div className="flex justify-center">
          <div
            className="relative h-40 w-40"
            role="img"
            aria-label={`Entity coverage: ${grouped.present.length} covered, ${grouped["high-impact-missing"].length} association opportunities, and ${grouped.missing.length} not observed out of ${coverage.total} tracked profile terms`}
          >
            <svg
              viewBox="0 0 120 120"
              className="h-full w-full -rotate-90"
              aria-hidden="true"
            >
              <circle
                cx="60"
                cy="60"
                r="46"
                fill="none"
                className="stroke-surface-border"
                strokeWidth="16"
              />
              {coverage.total > 0
                ? slices.map((slice) => (
                    <circle
                      key={slice.presence}
                      cx="60"
                      cy="60"
                      r="46"
                      pathLength="100"
                      fill="none"
                      className={slice.stroke}
                      strokeWidth="16"
                      strokeDasharray={`${slice.value} ${100 - slice.value}`}
                      strokeDashoffset={slice.offset}
                    />
                  ))
                : null}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-semibold tabular-nums text-surface-foreground">
                {coveredPct}%
              </span>
              <span className="text-xs text-surface-subtle">coverage</span>
            </div>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-surface-foreground">
            {grouped.present.length} of {coverage.total} profile terms are
            covered
          </p>
          <p className="mt-1 text-xs text-surface-subtle">
            Coverage = terms seen with {brand} ÷ all tracked profile terms.
          </p>
          <ul className="mt-4 divide-y divide-surface-border rounded-lg border border-surface-border bg-white">
            {GROUPS.map((group) => (
              <li
                key={group.presence}
                className="flex items-center gap-3 px-3 py-2.5"
              >
                <span
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${group.dot}`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-surface-foreground">
                    {group.label}
                  </p>
                  <p className="text-xs text-surface-subtle">
                    {group.description}
                  </p>
                </div>
                <span className="text-base font-semibold tabular-nums text-surface-foreground">
                  {grouped[group.presence].length}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <h3 className="text-sm font-semibold text-surface-foreground">
          Profile terms
        </h3>
        <p className="mt-1 text-xs text-surface-subtle">
          The small count shows how many of the {scoredAnswers} scored answers
          contain that term.
        </p>

        {coverage.total === 0 ? (
          <p className="mt-4 rounded-lg border border-dashed border-surface-border px-4 py-8 text-center text-sm text-surface-subtle">
            No profile terms were available for this analysis.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {GROUPS.map((group) => (
              <section
                key={group.presence}
                className="rounded-lg border border-surface-border p-3"
                aria-labelledby={`coverage-group-${group.presence}`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${group.dot}`}
                    aria-hidden="true"
                  />
                  <h4
                    id={`coverage-group-${group.presence}`}
                    className="text-sm font-medium text-surface-foreground"
                  >
                    {group.label}
                  </h4>
                  <span className="ml-auto text-xs tabular-nums text-surface-subtle">
                    {grouped[group.presence].length}
                  </span>
                </div>

                {grouped[group.presence].length === 0 ? (
                  <p className="mt-3 text-xs text-surface-subtle">None</p>
                ) : (
                  <ul className="mt-3 space-y-1.5">
                    {grouped[group.presence].map((entity) => (
                      <li
                        key={entity.name}
                        className="flex items-start justify-between gap-2 rounded-md bg-surface-muted px-2.5 py-2 text-xs"
                      >
                        <span className="min-w-0 break-words text-surface-foreground">
                          {entity.name}
                        </span>
                        <span className="shrink-0 tabular-nums text-surface-subtle">
                          {entity.answers}/{scoredAnswers}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
