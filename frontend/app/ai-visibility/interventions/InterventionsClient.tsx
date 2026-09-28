"use client";

import Link from "next/link";
import AnalysisBoundSubpage from "@/components/ai-visibility/AnalysisBoundSubpage";
import {
  interventionsFromAnalysis,
  type InterventionDetail,
} from "@/lib/ai-visibility-data";

type Model = ReturnType<typeof interventionsFromAnalysis>;

function category(label: string | null): string {
  return label ? label.replaceAll("_", " ") : "Action";
}

function evidenceLabel(value: string): string | null {
  if (value === "search_visibility.owned_domain_in_results=false")
    return "Owned domain missing from search results";
  if (value === "search_visibility.brand_in_results=false")
    return "Brand missing from search results";
  if (value === "search_visibility.brand_in_results=true")
    return "Brand appears in search results";
  if (value === "mentioned=False" || value === "mentioned=false")
    return "Brand absent from the answer";
  if (
    value === "citation_metrics.target_brand_cited=False" ||
    value === "citation_metrics.target_brand_cited=false"
  )
    return "Brand not cited in the answer";
  if (value.startsWith("search_visibility.brand_best_rank="))
    return `Best search rank: #${value.split("=")[1]}`;
  return null;
}

function ScoreBar({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null;
  tone: "impact" | "effort";
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="text-surface-subtle">{label}</span>
        <span className="font-semibold tabular-nums text-surface-foreground">
          {value == null ? "Not scored" : `${value}/5`}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-muted">
        {value != null ? (
          <div
            className={`h-full rounded-full ${tone === "impact" ? "bg-primary" : "bg-warning"}`}
            style={{ width: `${value * 20}%` }}
          />
        ) : null}
      </div>
    </div>
  );
}

function ImpactMap({ items }: { items: InterventionDetail[] }) {
  const points = new Map<
    string,
    { impact: number; effort: number; indices: number[] }
  >();
  items.forEach((item, index) => {
    if (item.impact == null || item.effort == null) return;
    const key = `${item.impact}-${item.effort}`;
    const point = points.get(key) ?? {
      impact: item.impact,
      effort: item.effort,
      indices: [],
    };
    point.indices.push(index);
    points.set(key, point);
  });

  if (points.size === 0) return null;

  return (
    <section
      className="rounded-2xl border border-surface-border bg-white p-5 shadow-sm sm:p-6"
      aria-labelledby="impact-map-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
            Decision map
          </p>
          <h2
            id="impact-map-heading"
            className="mt-1 text-xl font-semibold text-surface-foreground"
          >
            Impact versus effort
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-surface-subtle">
            The number in each circle shows how many actions share those scores.
            Select a circle to jump to its first action.
          </p>
        </div>
        <span className="rounded-full bg-primary-soft px-3 py-1 text-xs font-medium text-primary-strong">
          Start in the upper left
        </span>
      </div>

      <div className="mt-6 flex gap-3">
        <div className="flex w-5 shrink-0 items-center justify-center text-[11px] font-semibold uppercase tracking-wider text-surface-subtle [writing-mode:vertical-rl] [transform:rotate(180deg)]">
          Higher impact
        </div>
        <div className="min-w-0 flex-1">
          <div className="relative h-64 overflow-hidden rounded-xl border border-surface-border bg-surface-muted/30 sm:h-72">
            <div
              className="absolute inset-0 grid grid-cols-2 grid-rows-2 text-xs font-medium text-surface-subtle"
              aria-hidden="true"
            >
              <div className="border-b border-r border-surface-border bg-primary-soft/40 p-3">
                Higher impact, lower effort
              </div>
              <div className="border-b border-surface-border p-3 text-right">
                Strategic bets
              </div>
              <div className="border-r border-surface-border p-3 self-end">
                Easy to try
              </div>
              <div className="p-3 text-right self-end">Plan carefully</div>
            </div>
            {[...points.values()].map((point) => (
              <Link
                key={`${point.impact}-${point.effort}`}
                href={`#intervention-${point.indices[0] + 1}`}
                aria-label={`${point.indices.length} recommendation${point.indices.length === 1 ? "" : "s"} with impact ${point.impact} of 5 and effort ${point.effort} of 5`}
                title={`Impact ${point.impact}/5 · Effort ${point.effort}/5`}
                className="absolute z-10 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white bg-primary text-xs font-bold text-white shadow-md transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 sm:h-10 sm:w-10"
                style={{
                  left: `${10 + (point.effort - 1) * 20}%`,
                  top: `${90 - (point.impact - 1) * 20}%`,
                }}
              >
                {point.indices.length}
              </Link>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[11px] font-medium text-surface-subtle">
            <span>Lower effort</span>
            <span>Higher effort</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function InterventionCard({
  item,
  index,
}: {
  item: InterventionDetail;
  index: number;
}) {
  const signals = item.evidence
    .map(evidenceLabel)
    .filter((label): label is string => label !== null)
    .slice(0, 3);
  return (
    <li
      id={`intervention-${index + 1}`}
      className="scroll-mt-24 overflow-hidden rounded-2xl border border-surface-border bg-white shadow-sm"
    >
      <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white tabular-nums">
              {index + 1}
            </span>
            <span className="rounded-full bg-primary-soft px-2.5 py-1 text-xs font-medium capitalize text-primary-strong">
              {category(item.label)}
            </span>
            {item.triggerCount != null ? (
              <span className="text-xs text-surface-subtle">
                Matched {item.triggerCount} prompt
                {item.triggerCount === 1 ? "" : "s"}
              </span>
            ) : null}
          </div>
          <h3 className="mt-3 text-lg font-semibold leading-snug text-surface-foreground">
            {item.title}
          </h3>
          {item.description ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-surface-subtle">
              {item.description}
            </p>
          ) : null}
          {item.expectedOutcome ? (
            <div className="mt-5 rounded-xl border border-primary/15 bg-primary-soft/35 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary-strong">
                Expected outcome
              </p>
              <p className="mt-1 text-sm leading-6 text-surface-foreground">
                {item.expectedOutcome}
              </p>
            </div>
          ) : null}
        </div>
        <div className="space-y-5 rounded-xl bg-surface-muted/55 p-4">
          <ScoreBar
            label="Estimated GEO impact"
            value={item.impact}
            tone="impact"
          />
          <ScoreBar
            label="Implementation effort"
            value={item.effort}
            tone="effort"
          />
          <p className="border-t border-surface-border pt-3 text-xs leading-5 text-surface-subtle">
            Scores are estimates from the intervention library, from 1 to 5.
          </p>
        </div>
      </div>
      {item.gapClaims.length > 0 ||
      item.prompts.length > 0 ||
      item.theory ||
      signals.length > 0 ? (
        <div className="grid gap-5 border-t border-surface-border bg-surface-muted/20 px-5 py-4 text-sm sm:px-6 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-surface-subtle">
              Why this action
            </p>
            {item.gapClaims.length > 0 ? (
              <ul className="mt-2 space-y-1.5 text-surface-foreground">
                {item.gapClaims.slice(0, 2).map((claim) => (
                  <li key={claim}>• {claim}</li>
                ))}
              </ul>
            ) : item.theory ? (
              <p className="mt-2 leading-6 text-surface-foreground">
                {item.theory}
              </p>
            ) : null}
            {signals.length > 0 ? (
              <ul className="mt-3 flex flex-wrap gap-2">
                {signals.map((signal) => (
                  <li
                    key={signal}
                    className="rounded-full border border-surface-border bg-white px-2.5 py-1 text-xs text-surface-subtle"
                  >
                    {signal}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          {item.prompts.length > 0 ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-surface-subtle">
                Affected prompts
              </p>
              <ul className="mt-2 space-y-1.5 text-surface-foreground">
                {item.prompts.slice(0, 2).map((prompt) => (
                  <li key={prompt}>“{prompt}”</li>
                ))}
              </ul>
              {item.prompts.length > 2 ? (
                <p className="mt-1 text-xs text-surface-subtle">
                  +{item.prompts.length - 2} more prompts
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function InterventionsContent({ model }: { model: Model }) {
  const { interventions } = model;
  const quickWins = interventions.filter(
    (item) =>
      item.impact != null &&
      item.impact >= 4 &&
      item.effort != null &&
      item.effort <= 2,
  ).length;
  const matchedPrompts = new Set(interventions.flatMap((item) => item.prompts))
    .size;

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary-soft/70 via-white to-white p-6 shadow-sm sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          From insight to action
        </p>
        <h2 className="mt-2 max-w-3xl text-2xl font-semibold tracking-tight text-surface-foreground sm:text-3xl">
          A focused action plan for {model.domain}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-surface-subtle">
          These suggestions come from the selected analysis. Compare estimated
          impact with effort, then review the measured gaps and prompts behind
          each action.
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[
            { value: interventions.length, label: "Recommended actions" },
            { value: quickWins, label: "High impact, low effort" },
            { value: matchedPrompts, label: "Distinct matched prompts" },
          ].map((metric) => (
            <div
              key={metric.label}
              className="rounded-xl border border-white/80 bg-white/85 px-4 py-3 shadow-sm"
            >
              <p className="text-2xl font-semibold tabular-nums text-surface-foreground">
                {metric.value}
              </p>
              <p className="mt-1 text-xs text-surface-subtle">{metric.label}</p>
            </div>
          ))}
        </div>
      </section>

      {interventions.length === 0 ? (
        <section className="rounded-2xl border border-dashed border-surface-border bg-white p-8 text-center">
          <h2 className="font-semibold text-surface-foreground">
            No interventions for this run yet
          </h2>
          <p className="mt-2 text-sm text-surface-subtle">
            This analysis did not produce a matched recommendation.
          </p>
          <Link
            href={`/ai-visibility/drivers?analysis=${model.analysisId}`}
            className="mt-4 inline-flex text-sm font-medium text-primary hover:text-primary-hover"
          >
            Review drivers and gaps
          </Link>
        </section>
      ) : (
        <>
          <ImpactMap items={interventions} />
          <section aria-labelledby="action-list-heading">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                  Ranked recommendations
                </p>
                <h2
                  id="action-list-heading"
                  className="mt-1 text-xl font-semibold text-surface-foreground"
                >
                  What to do next
                </h2>
                <p className="mt-1 text-sm text-surface-subtle">
                  Ordered by estimated impact relative to effort and repeated
                  matches across the run.
                </p>
              </div>
              <Link
                href={`/ai-visibility/drivers?analysis=${model.analysisId}`}
                className="text-sm font-medium text-primary hover:text-primary-hover"
              >
                Explore drivers & gaps →
              </Link>
            </div>
            <ol className="space-y-4">
              {interventions.map((item, index) => (
                <InterventionCard
                  key={`${item.id}-${index}`}
                  item={item}
                  index={index}
                />
              ))}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}

export default function InterventionsClient() {
  return (
    <AnalysisBoundSubpage title="Recommended interventions">
      {(analysis) => (
        <InterventionsContent model={interventionsFromAnalysis(analysis)} />
      )}
    </AnalysisBoundSubpage>
  );
}
