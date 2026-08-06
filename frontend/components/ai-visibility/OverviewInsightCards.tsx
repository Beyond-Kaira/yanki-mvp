import Link from "next/link";
import type { Insights } from "@/lib/insights";

interface OverviewInsightCardsProps {
  insights: Insights;
  analysisId: string | null;
}

function percent(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((value / total) * 100);
}

function detailHref(path: string, analysisId: string | null): string {
  return analysisId
    ? `${path}?analysis=${encodeURIComponent(analysisId)}`
    : path;
}

function MiniRing({
  value,
  label,
  tone,
}: {
  value: number;
  label: string;
  tone: "primary" | "danger";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const stroke = tone === "danger" ? "stroke-danger" : "stroke-primary";

  return (
    <div className="relative h-24 w-24 shrink-0" role="img" aria-label={label}>
      <svg
        viewBox="0 0 100 100"
        className="h-full w-full -rotate-90"
        aria-hidden="true"
      >
        <circle
          cx="50"
          cy="50"
          r="38"
          pathLength="100"
          fill="none"
          className="stroke-surface-border"
          strokeWidth="10"
        />
        <circle
          cx="50"
          cy="50"
          r="38"
          pathLength="100"
          fill="none"
          className={stroke}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${clamped} ${100 - clamped}`}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xl font-semibold tabular-nums text-surface-foreground">
        {clamped}%
      </span>
    </div>
  );
}

export default function OverviewInsightCards({
  insights,
  analysisId,
}: OverviewInsightCardsProps) {
  const gapPct = percent(insights.gap.answersLost, insights.gap.total);
  const coveragePct = percent(
    insights.entityCoverage.present,
    insights.entityCoverage.total,
  );

  return (
    <section
      className="mt-4 grid gap-4 md:grid-cols-2"
      aria-label="Visibility insight summary"
    >
      <article className="rounded-2xl border border-surface-border bg-surface p-5 shadow-sm">
        <div className="flex items-center justify-between gap-5">
          <div className="min-w-0">
            <h2 className="text-sm font-medium text-surface-foreground">
              Answer visibility gap
            </h2>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-surface-foreground">
              {insights.gap.answersLost}/{insights.gap.total}
              <span className="ml-1 text-sm font-normal text-surface-subtle">
                answers
              </span>
            </p>
            <p className="mt-1 text-xs leading-5 text-surface-subtle">
              Competitor-only answers; other outcomes may include no-signal
              results.
            </p>
          </div>
          <MiniRing
            value={gapPct}
            tone="danger"
            label={`Visibility gap: ${insights.gap.answersLost} of ${insights.gap.total} answers`}
          />
        </div>
        <Link
          href={detailHref("/ai-visibility/drivers", analysisId)}
          className="mt-4 inline-flex text-sm font-medium text-primary hover:text-primary-hover"
        >
          View answer gap details →
        </Link>
      </article>

      <article className="rounded-2xl border border-surface-border bg-surface p-5 shadow-sm">
        <div className="flex items-center justify-between gap-5">
          <div className="min-w-0">
            <h2 className="text-sm font-medium text-surface-foreground">
              Entity coverage
            </h2>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-surface-foreground">
              {insights.entityCoverage.present}/{insights.entityCoverage.total}
              <span className="ml-1 text-sm font-normal text-surface-subtle">
                terms
              </span>
            </p>
            <p className="mt-1 text-xs leading-5 text-surface-subtle">
              Profile terms associated with {insights.brand} in answers.
            </p>
          </div>
          <MiniRing
            value={coveragePct}
            tone="primary"
            label={`Entity coverage: ${insights.entityCoverage.present} of ${insights.entityCoverage.total} profile terms`}
          />
        </div>
        <Link
          href={detailHref("/ai-visibility/entities", analysisId)}
          className="mt-4 inline-flex text-sm font-medium text-primary hover:text-primary-hover"
        >
          View entity details →
        </Link>
      </article>
    </section>
  );
}
