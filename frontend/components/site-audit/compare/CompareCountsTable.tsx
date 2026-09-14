import type { ReactNode } from "react";
import type { SiteAuditRunSummary } from "@/lib/contracts";
import EmptyPanel from "@/components/site-audit/shared/EmptyPanel";
import {
  changeAmount,
  changeTone,
  runLabel,
  type ChangeTone,
  type MetricDirection,
} from "./compareUtils";

const TONE_CLASSES: Record<ChangeTone, string> = {
  better: "text-success-strong",
  worse: "text-danger-strong",
  same: "text-surface-subtle",
  unknown: "text-surface-subtle",
};

export interface CompareCountsRow {
  key: string;
  /** The row's identity cell — a badge and a message, or a schema type. */
  label: ReactNode;
  counts: (number | null)[];
  /** Optional second line under the count, e.g. "3 with unknown properties". */
  note?: (runIndex: number) => ReactNode;
}

/**
 * Rows against runs. Shared by the finding and schema comparisons because the
 * shape is the same question both times: did this thing get better or worse
 * between crawls. A `null` count means that run's pages are not loaded, which
 * is not the same as zero and must not be rendered as progress.
 */
export default function CompareCountsTable({
  title,
  description,
  runs,
  rows,
  direction,
  emptyMessage,
}: {
  title: string;
  description: string;
  runs: SiteAuditRunSummary[];
  rows: CompareCountsRow[];
  direction: MetricDirection;
  emptyMessage: string;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
      <header className="border-b border-surface-border px-6 py-4">
        <h2 className="text-xl font-semibold text-surface-foreground">
          {title}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-surface-subtle">
          {description}
        </p>
      </header>

      {rows.length === 0 ? (
        <EmptyPanel message={emptyMessage} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-surface-border text-left">
                <th
                  scope="col"
                  className="px-6 py-3 font-medium text-surface-subtle"
                >
                  Finding
                </th>
                {runs.map((run, index) => (
                  <th
                    key={run.id}
                    scope="col"
                    className="px-4 py-3 text-right font-medium text-surface-subtle"
                  >
                    {runLabel(run)}
                    {index === 0 ? (
                      <span className="ml-1 text-[10px] uppercase tracking-wide text-primary-strong">
                        latest
                      </span>
                    ) : null}
                  </th>
                ))}
                <th
                  scope="col"
                  className="px-6 py-3 text-right font-medium text-surface-subtle"
                >
                  Change
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const [latest, previous] = row.counts;
                const tone = changeTone(
                  latest ?? null,
                  previous ?? null,
                  direction,
                );
                const amount = changeAmount(latest ?? null, previous ?? null);
                return (
                  <tr
                    key={row.key}
                    className="border-b border-surface-border last:border-0"
                  >
                    <td className="px-6 py-3 align-top">{row.label}</td>
                    {row.counts.map((count, runIndex) => (
                      <td
                        key={runs[runIndex]?.id ?? runIndex}
                        className="px-4 py-3 text-right align-top tabular-nums text-surface-foreground"
                      >
                        {count == null ? (
                          <span className="text-surface-subtle">—</span>
                        ) : (
                          count
                        )}
                        {row.note ? (
                          <span className="mt-0.5 block text-xs text-surface-subtle">
                            {row.note(runIndex)}
                          </span>
                        ) : null}
                      </td>
                    ))}
                    <td
                      className={`px-6 py-3 text-right align-top tabular-nums font-medium ${TONE_CLASSES[tone]}`}
                    >
                      {amount == null
                        ? "—"
                        : amount === 0
                          ? "same"
                          : amount > 0
                            ? `+${amount}`
                            : amount}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
