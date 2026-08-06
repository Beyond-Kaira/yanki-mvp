import type {
  EntityLandscape as EntityLandscapeData,
  Ownership,
  Tier,
} from "@/lib/insights";

interface EntityLandscapeProps {
  landscape: EntityLandscapeData;
  scoredAnswers: number;
}

interface RelationshipMeta {
  label: string;
  badge: string;
  dot: string;
  description: (brand: string) => string;
}

// Colour is deliberately secondary here. Every relationship has a persistent
// text label and explanation, so the chart remains understandable without a
// legend, hover state or colour perception.
const RELATIONSHIP: Record<Ownership, RelationshipMeta> = {
  ours: {
    label: "Your brand",
    badge: "bg-primary-soft text-primary-strong",
    dot: "bg-primary",
    description: () => "The brand being measured in this analysis.",
  },
  shared: {
    label: "Associated with you",
    badge: "bg-success-soft text-success-strong",
    dot: "bg-success",
    description: (brand) =>
      `Appeared in at least one answer that also named ${brand}.`,
  },
  competitor: {
    label: "Seen without you",
    badge: "bg-warning-soft text-warning-strong",
    dot: "bg-warning",
    description: (brand) =>
      `Appeared in answers, but never in the same answer as ${brand}.`,
  },
  unclaimed: {
    label: "Not observed",
    badge: "bg-surface-muted text-surface-subtle",
    dot: "bg-surface-subtle/50",
    description: () => "Did not appear in any scored answer.",
  },
};

const TIER_LABEL: Record<Tier, string> = {
  core: "Core entity",
  secondary: "Secondary entity",
  none: "Not observed",
};

function answerPercent(answers: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((answers / total) * 100);
}

// A ranked map of the names and topics detected across the scored answers.
// Bars use the real scored-answer denominator, rather than scaling relative to
// the largest row. That makes 50% mean the same thing on every card.
export default function EntityLandscape({
  landscape,
  scoredAnswers,
}: EntityLandscapeProps) {
  const brand =
    landscape.entities.find((entity) => entity.ownership === "ours")?.name ??
    "the brand";
  const observed = landscape.entities.filter((entity) => entity.answers > 0);
  const coreCount = observed.filter((entity) => entity.tier === "core").length;
  const brandEntity = landscape.entities.find(
    (entity) => entity.ownership === "ours",
  );
  const brandPct = answerPercent(brandEntity?.answers ?? 0, scoredAnswers);

  return (
    <section
      className="overflow-hidden rounded-xl border border-surface-border bg-white shadow-sm"
      aria-labelledby="landscape-heading"
    >
      <div className="border-b border-surface-border px-5 py-5 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">
          Answer-level entity analysis
        </p>
        <h2
          id="landscape-heading"
          className="mt-1 text-xl font-semibold text-surface-foreground"
        >
          Industry entity landscape
        </h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-surface-subtle">
          The brands, companies, locations and topics found across the scored
          answers. Each entity is counted once per answer, even when it is
          repeated several times. One-off external names are filtered out to
          reduce noise.
        </p>
      </div>

      <dl className="grid border-b border-surface-border bg-surface-muted sm:grid-cols-3 sm:divide-x sm:divide-surface-border">
        <div className="px-5 py-4 sm:px-6">
          <dt className="text-xs font-medium text-surface-subtle">
            Your brand visibility
          </dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums text-surface-foreground">
            {brandPct}%
          </dd>
          <dd className="mt-1 text-xs text-surface-subtle">
            {brandEntity?.answers ?? 0} of {scoredAnswers} scored answers
          </dd>
        </div>
        <div className="border-t border-surface-border px-5 py-4 sm:border-t-0 sm:px-6">
          <dt className="text-xs font-medium text-surface-subtle">
            Entities observed
          </dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums text-surface-foreground">
            {observed.length}
          </dd>
          <dd className="mt-1 text-xs text-surface-subtle">
            unique names or topics in this run
          </dd>
        </div>
        <div className="border-t border-surface-border px-5 py-4 sm:border-t-0 sm:px-6">
          <dt className="text-xs font-medium text-surface-subtle">
            Core entities
          </dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums text-surface-foreground">
            {coreCount}
          </dd>
          <dd className="mt-1 text-xs text-surface-subtle">
            seen in at least {landscape.coreThreshold} answers
          </dd>
        </div>
      </dl>

      <div className="space-y-5 p-5 sm:p-6">
        <div className="rounded-lg border border-primary/20 bg-primary-soft/60 p-4">
          <h3 className="text-sm font-semibold text-surface-foreground">
            How to read this
          </h3>
          <p className="mt-1 text-sm leading-6 text-surface-subtle">
            The percentage and green bar show presence across all{" "}
            {scoredAnswers} scored answers. The relationship label explains
            whether an entity appeared with {brand}, without {brand}, or is the
            measured brand itself.
          </p>
          <ul className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
            {(["ours", "shared", "competitor"] as const).map((ownership) => {
              const meta = RELATIONSHIP[ownership];
              return (
                <li
                  key={ownership}
                  className="flex items-center gap-2 rounded-md bg-white/80 px-3 py-2 text-surface-subtle"
                >
                  <span
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${meta.dot}`}
                    aria-hidden="true"
                  />
                  <span>
                    <strong className="font-medium text-surface-foreground">
                      {meta.label}:
                    </strong>{" "}
                    {ownership === "ours"
                      ? "the measured brand"
                      : ownership === "shared"
                        ? "seen together"
                        : "never seen together"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>

        {landscape.entities.length === 0 ? (
          <p className="rounded-lg border border-dashed border-surface-border px-4 py-10 text-center text-sm text-surface-subtle">
            No entities were detected in the scored answers.
          </p>
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {landscape.entities.map((entity) => {
              const relationship = RELATIONSHIP[entity.ownership];
              const pct = answerPercent(entity.answers, scoredAnswers);

              return (
                <li
                  key={entity.name}
                  className="flex min-w-0 flex-col rounded-lg border border-surface-border bg-white p-4 transition-shadow hover:shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-surface-foreground">
                        {entity.name}
                      </p>
                      <p className="mt-0.5 text-xs text-surface-subtle">
                        {TIER_LABEL[entity.tier]}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${relationship.badge}`}
                    >
                      {relationship.label}
                    </span>
                  </div>

                  <div className="mt-4 flex items-end justify-between gap-3">
                    <span className="text-sm text-surface-subtle">
                      Answer presence
                    </span>
                    <span className="text-lg font-semibold tabular-nums text-surface-foreground">
                      {pct}%
                    </span>
                  </div>
                  <div
                    className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-surface-muted"
                    role="progressbar"
                    aria-label={`${entity.name}: present in ${entity.answers} of ${scoredAnswers} scored answers`}
                    aria-valuenow={pct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs tabular-nums text-surface-subtle">
                    Found in {entity.answers} of {scoredAnswers} scored answers
                  </p>
                  <p className="mt-3 border-t border-surface-border pt-3 text-xs leading-5 text-surface-subtle">
                    {relationship.description(brand)}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
