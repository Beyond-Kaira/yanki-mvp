import type { SiteAuditRunSummary } from "@/lib/contracts";
import {
  changeAmount,
  changeTone,
  runLabel,
  type ChangeTone,
  type CompareMetric,
} from "./compareUtils";

const TONE_CLASSES: Record<ChangeTone, string> = {
  better: "bg-success-soft text-success-strong",
  worse: "bg-danger-soft text-danger-strong",
  same: "bg-surface-muted text-surface-subtle",
  unknown: "bg-surface-muted text-surface-subtle",
};

function formatValue(value: number | null, suffix?: string): string {
  return value == null ? "—" : `${value}${suffix ?? ""}`;
}

/**
 * One metric across the selected runs. Bars are sized against the largest value
 * in *this* metric only — comparing "pages crawled" against "errors" on a shared
 * scale would make the smaller of the two invisible and say nothing true.
 */
export default function CompareMetricCard({
  metric,
  runs,
}: {
  metric: CompareMetric;
  runs: SiteAuditRunSummary[];
}) {
  const values = runs.map((run) => metric.valueOf(run));
  const scale = Math.max(1, ...values.map((value) => value ?? 0));
  const [latest, previous] = values;
  const tone = changeTone(latest ?? null, previous ?? null, metric.direction);
  const amount = changeAmount(latest ?? null, previous ?? null);

  return (
    <article className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm">
      <h3 className="text-sm font-medium text-surface-foreground">
        {metric.label}
      </h3>

      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-3xl font-semibold tracking-tight text-surface-foreground">
          {formatValue(latest ?? null, metric.suffix)}
        </span>
        {amount != null && amount !== 0 ? (
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
          >
            {amount > 0 ? `+${amount}` : amount}
          </span>
        ) : (
          <span className="text-xs text-surface-subtle">
            {runs.length < 2 ? "First run" : "No change"}
          </span>
        )}
      </div>

      <ul className="mt-4 space-y-2">
        {runs.map((run, index) => {
          const value = values[index];
          return (
            <li key={run.id}>
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="truncate text-surface-subtle">
                  {runLabel(run)}
                </span>
                <span className="font-medium text-surface-foreground">
                  {formatValue(value, metric.suffix)}
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted">
                <div
                  aria-hidden="true"
                  className={`h-full rounded-full ${index === 0 ? "bg-primary" : "bg-surface-subtle"}`}
                  style={{ width: `${((value ?? 0) / scale) * 100}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </article>
  );
}
