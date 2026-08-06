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
  title: string;
  shortLabel: string;
  description: string;
  empty: string;
  badge: string;
  dot: string;
  stroke: string;
}

const GROUPS: CoverageGroup[] = [
  {
    presence: "present",
    title: "Covered terms",
    shortLabel: "Covered",
    description:
      "Profile terms found in at least one answer that also names your brand.",
    empty: "No profile term is associated with your brand in the answers yet.",
    badge: "bg-success-soft text-success-strong",
    dot: "bg-success",
    stroke: "stroke-success",
  },
  {
    presence: "high-impact-missing",
    title: "Association opportunities",
    shortLabel: "Opportunity",
    description:
      "Terms the engines discuss, but only in answers that leave your brand out.",
    empty: "No high-impact association gaps were detected.",
    badge: "bg-warning-soft text-warning-strong",
    dot: "bg-warning",
    stroke: "stroke-warning",
  },
  {
    presence: "missing",
    title: "Not observed",
    shortLabel: "Not observed",
    description:
      "Profile terms that did not appear in any scored answer in this run.",
    empty: "Every tracked profile term appeared in at least one answer.",
    badge: "bg-surface-muted text-surface-subtle",
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

function termExplanation(
  entity: EntityStat,
  brand: string,
  scoredAnswers: number,
): string {
  const presence = entity.presence ?? "missing";
  if (presence === "present") {
    return `Found in ${entity.answers} of ${scoredAnswers} scored answers. At least one of those answers also names ${brand}.`;
  }
  if (presence === "high-impact-missing") {
    return `Found in ${entity.answers} of ${scoredAnswers} scored answers, but none of them names ${brand}.`;
  }
  return `Not found in any of the ${scoredAnswers} scored answers.`;
}

// Coverage is vocabulary coverage, not answer visibility: the denominator is
// the number of distinct terms extracted from the brand profile. A term is
// covered when at least one scored answer contains both that term and the
// measured brand.
export default function EntityCoverage({
  coverage,
  brand,
  scoredAnswers,
}: EntityCoverageProps) {
  const counts = {
    present: entitiesFor(coverage.entities, "present").length,
    "high-impact-missing": entitiesFor(coverage.entities, "high-impact-missing")
      .length,
    missing: entitiesFor(coverage.entities, "missing").length,
  };
  const coveredPct = percent(counts.present, coverage.total);
  const opportunityPct = percent(counts["high-impact-missing"], coverage.total);
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
      <div className="border-b border-surface-border px-5 py-5 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">
          Brand vocabulary
        </p>
        <h2
          id="coverage-heading"
          className="mt-1 text-xl font-semibold text-surface-foreground"
        >
          Entity coverage
        </h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-surface-subtle">
          Checks whether the products, services, keywords, locations, use cases
          and category in the {brand} profile are associated with the brand in
          AI answers.
        </p>
      </div>

      <div className="grid gap-6 border-b border-surface-border p-5 sm:p-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <div className="flex flex-col items-center justify-center rounded-xl bg-surface-muted p-5 text-center">
          <div
            className="relative h-48 w-48"
            role="img"
            aria-label={`Entity coverage: ${counts.present} covered, ${counts["high-impact-missing"]} association opportunities, and ${counts.missing} not observed out of ${coverage.total} tracked profile terms`}
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
                      strokeLinecap="butt"
                      strokeDasharray={`${slice.value} ${100 - slice.value}`}
                      strokeDashoffset={slice.offset}
                    />
                  ))
                : null}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-4xl font-semibold tabular-nums text-surface-foreground">
                {coveredPct}%
              </span>
              <span className="mt-1 text-xs font-medium uppercase tracking-wide text-surface-subtle">
                covered
              </span>
            </div>
          </div>
          <p className="mt-3 text-sm font-medium text-surface-foreground">
            {counts.present} of {coverage.total} tracked profile terms
          </p>
          <p className="mt-1 max-w-[15rem] text-xs leading-5 text-surface-subtle">
            Coverage = terms associated with {brand} ÷ all tracked profile
            terms.
          </p>
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-surface-foreground">
            What the chart shows
          </h3>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {GROUPS.map((group) => {
              const count = counts[group.presence];
              return (
                <div
                  key={group.presence}
                  className="rounded-lg border border-surface-border p-4"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={`mt-1 h-3 w-3 shrink-0 rounded-full ${group.dot}`}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <p className="text-sm font-medium text-surface-foreground">
                          {group.shortLabel}
                        </p>
                        <p className="text-lg font-semibold tabular-nums text-surface-foreground">
                          {count}
                          <span className="ml-1 text-xs font-normal text-surface-subtle">
                            terms
                          </span>
                        </p>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-surface-subtle">
                        {group.description}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="space-y-6 p-5 sm:p-6">
        <div>
          <h3 className="text-base font-semibold text-surface-foreground">
            Tracked term details
          </h3>
          <p className="mt-1 text-sm text-surface-subtle">
            Terms are grouped by their relationship with {brand}. Answer counts
            count distinct scored answers, not repeated mentions inside one
            answer.
          </p>
        </div>

        {coverage.total === 0 ? (
          <p className="rounded-lg border border-dashed border-surface-border px-4 py-10 text-center text-sm text-surface-subtle">
            No products, services, keywords, locations, use cases or category
            terms were available in the brand profile.
          </p>
        ) : (
          GROUPS.map((group) => {
            const entities = entitiesFor(coverage.entities, group.presence);
            return (
              <section
                key={group.presence}
                aria-labelledby={`coverage-group-${group.presence}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h4
                    id={`coverage-group-${group.presence}`}
                    className="text-sm font-semibold text-surface-foreground"
                  >
                    {group.title}
                  </h4>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${group.badge}`}
                  >
                    {entities.length}
                  </span>
                </div>
                <p className="mt-1 text-xs text-surface-subtle">
                  {group.description}
                </p>

                {entities.length === 0 ? (
                  <p className="mt-3 rounded-lg bg-surface-muted px-4 py-4 text-sm text-surface-subtle">
                    {group.empty}
                  </p>
                ) : (
                  <ul className="mt-3 grid gap-3 md:grid-cols-2">
                    {entities.map((entity) => (
                      <li
                        key={entity.name}
                        className="rounded-lg border border-surface-border p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="font-medium text-surface-foreground">
                            {entity.name}
                          </p>
                          <span className="shrink-0 text-sm font-semibold tabular-nums text-surface-foreground">
                            {percent(entity.answers, scoredAnswers)}%
                          </span>
                        </div>
                        <p className="mt-2 text-xs leading-5 text-surface-subtle">
                          {termExplanation(entity, brand, scoredAnswers)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })
        )}
      </div>
    </section>
  );
}
