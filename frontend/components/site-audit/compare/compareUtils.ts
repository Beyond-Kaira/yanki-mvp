import type {
  SiteAuditDetail,
  SiteAuditIssue,
  SiteAuditRunSummary,
} from "@/lib/contracts";

/**
 * Comparison reads the run *summaries* the project detail already carries, so
 * the headline numbers need no extra request. Only the per-issue and per-schema
 * breakdowns need a run's pages, and those are fetched on demand.
 */

/**
 * Completed runs, newest first. A queued or failed run has nothing to compare.
 * Returns all of them by default: the selector needs the full list even though
 * only a few are charted at once.
 */
export function comparableRuns(
  audits: SiteAuditRunSummary[],
  limit?: number,
): SiteAuditRunSummary[] {
  const done = audits.filter((run) => run.status === "done");
  return limit == null ? done : done.slice(0, limit);
}

/** Comparing one run with itself says nothing; four columns stop fitting. */
export const MIN_COMPARED_RUNS = 2;
export const MAX_COMPARED_RUNS = 3;

/**
 * The runs to chart, given what the customer picked.
 *
 * Selection survives a poll — the project refetches every few seconds while a
 * crawl runs, and silently resetting the customer's choice each time would make
 * the control feel broken. Ids that no longer exist are dropped (a deleted or
 * superseded run), and if too few survive to compare, the default set stands in
 * rather than leaving the panel in a state the customer did not ask for.
 */
export function resolveSelectedRuns(
  available: SiteAuditRunSummary[],
  selectedIds: string[],
): SiteAuditRunSummary[] {
  const kept = available.filter((run) => selectedIds.includes(run.id));
  if (kept.length >= MIN_COMPARED_RUNS) return kept.slice(0, MAX_COMPARED_RUNS);
  return available.slice(0, MAX_COMPARED_RUNS);
}

export function totalIssues(run: SiteAuditRunSummary): number {
  return run.total_errors + run.total_warnings + run.total_notices;
}

/**
 * Which way is progress. Notices are deliberately `neutral`: they are
 * informational signals (robots blocks, redirects), so more of them is neither
 * a win nor a regression, and colouring them would tell the customer something
 * we do not know.
 */
export type MetricDirection = "up-is-better" | "down-is-better" | "neutral";

export interface CompareMetric {
  key: string;
  label: string;
  direction: MetricDirection;
  suffix?: string;
  valueOf: (run: SiteAuditRunSummary) => number | null;
}

export const COMPARE_METRICS: CompareMetric[] = [
  {
    key: "pages_crawled",
    label: "Pages crawled",
    direction: "up-is-better",
    valueOf: (run) => run.pages_crawled,
  },
  {
    key: "health_score",
    label: "Site health",
    direction: "up-is-better",
    suffix: "%",
    valueOf: (run) => run.health_score,
  },
  {
    key: "total_issues",
    label: "Total issues",
    direction: "down-is-better",
    valueOf: totalIssues,
  },
  {
    key: "total_errors",
    label: "Errors",
    direction: "down-is-better",
    valueOf: (run) => run.total_errors,
  },
  {
    key: "total_warnings",
    label: "Warnings",
    direction: "down-is-better",
    valueOf: (run) => run.total_warnings,
  },
  {
    key: "total_notices",
    label: "Notices",
    direction: "neutral",
    valueOf: (run) => run.total_notices,
  },
];

export type ChangeTone = "better" | "worse" | "same" | "unknown";

/** How a run compares with the one before it, in the metric's own terms. */
export function changeTone(
  current: number | null,
  previous: number | null,
  direction: MetricDirection,
): ChangeTone {
  if (current == null || previous == null) return "unknown";
  if (current === previous) return "same";
  if (direction === "neutral") return "same";
  const improved =
    direction === "up-is-better" ? current > previous : current < previous;
  return improved ? "better" : "worse";
}

/** Signed difference, or null when either side is unknown. */
export function changeAmount(
  current: number | null,
  previous: number | null,
): number | null {
  if (current == null || previous == null) return null;
  return current - previous;
}

export interface IssueComparisonRow {
  code: string;
  severity: SiteAuditIssue["severity"];
  message: string;
  /** Aligned with the runs passed in; `null` means that run is not loaded yet. */
  counts: (number | null)[];
}

const SEVERITY_RANK: Record<SiteAuditIssue["severity"], number> = {
  error: 0,
  warning: 1,
  notice: 2,
};

/**
 * One row per finding code, counted across every run. A code absent from a
 * loaded run is a real zero — that is the whole point, it is how a fixed issue
 * shows up — while a run still loading is `null` so the table can say "not
 * loaded" rather than claim the issue is gone.
 */
export function compareIssues(
  runDetails: (SiteAuditDetail | null)[],
): IssueComparisonRow[] {
  const rows = new Map<string, IssueComparisonRow>();

  runDetails.forEach((detail, runIndex) => {
    if (!detail) return;
    for (const page of detail.pages) {
      for (const issue of page.issues) {
        let row = rows.get(issue.code);
        if (!row) {
          row = {
            code: issue.code,
            severity: issue.severity,
            message: issue.message,
            counts: runDetails.map(() => null),
          };
          rows.set(issue.code, row);
        }
        row.counts[runIndex] = (row.counts[runIndex] ?? 0) + 1;
      }
    }
  });

  // A loaded run that never saw a code scores zero, not "unknown".
  for (const row of rows.values()) {
    runDetails.forEach((detail, runIndex) => {
      if (detail && row.counts[runIndex] == null) row.counts[runIndex] = 0;
    });
  }

  return Array.from(rows.values()).sort(
    (left, right) =>
      SEVERITY_RANK[left.severity] - SEVERITY_RANK[right.severity] ||
      (right.counts[0] ?? 0) - (left.counts[0] ?? 0) ||
      left.message.localeCompare(right.message),
  );
}

export interface SchemaComparisonRow {
  type: string;
  /** How many blocks of this type each run found. */
  counts: (number | null)[];
  /** How many of those had a property the ontology does not recognise. */
  unrecognised: (number | null)[];
}

/** One row per Schema.org type, so a markup block that disappears is visible. */
export function compareSchemas(
  runDetails: (SiteAuditDetail | null)[],
): SchemaComparisonRow[] {
  const rows = new Map<string, SchemaComparisonRow>();

  runDetails.forEach((detail, runIndex) => {
    if (!detail) return;
    for (const page of detail.pages) {
      for (const schema of page.schemas) {
        let row = rows.get(schema.type);
        if (!row) {
          row = {
            type: schema.type,
            counts: runDetails.map(() => null),
            unrecognised: runDetails.map(() => null),
          };
          rows.set(schema.type, row);
        }
        row.counts[runIndex] = (row.counts[runIndex] ?? 0) + 1;
        const invalid = schema.details?.invalid_fields?.length ?? 0;
        row.unrecognised[runIndex] =
          (row.unrecognised[runIndex] ?? 0) + (invalid ? 1 : 0);
      }
    }
  });

  for (const row of rows.values()) {
    runDetails.forEach((detail, runIndex) => {
      if (!detail) return;
      if (row.counts[runIndex] == null) row.counts[runIndex] = 0;
      if (row.unrecognised[runIndex] == null) row.unrecognised[runIndex] = 0;
    });
  }

  return Array.from(rows.values()).sort(
    (left, right) =>
      (right.counts[0] ?? 0) - (left.counts[0] ?? 0) ||
      left.type.localeCompare(right.type),
  );
}

const RUN_LABEL_FORMATTER = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Short, unambiguous label for a run: two crawls a day apart need the time. */
export function runLabel(run: SiteAuditRunSummary): string {
  const stamp = run.completed_at ?? run.started_at ?? run.created_at;
  const date = new Date(stamp);
  return Number.isNaN(date.getTime())
    ? "Unknown date"
    : RUN_LABEL_FORMATTER.format(date);
}
