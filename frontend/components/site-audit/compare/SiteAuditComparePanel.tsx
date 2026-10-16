"use client";

import { useEffect, useMemo, useState } from "react";
import type { SeoProjectDetail, SiteAuditDetail } from "@/lib/contracts";
import { getSiteAudit } from "@/lib/api";
import EmptyPanel from "@/components/site-audit/shared/EmptyPanel";
import SeverityBadge from "@/components/site-audit/shared/SeverityBadge";
import CompareCountsTable, {
  type CompareCountsRow,
} from "./CompareCountsTable";
import CompareMetricCard from "./CompareMetricCard";
import CompareRunSelector from "./CompareRunSelector";
import {
  COMPARE_METRICS,
  MAX_COMPARED_RUNS,
  comparableRuns,
  compareIssues,
  compareSchemas,
  resolveSelectedRuns,
} from "./compareUtils";

export default function SiteAuditComparePanel({
  projectId,
  project,
  loadedAudit,
}: {
  projectId: string;
  project: SeoProjectDetail;
  /** The run the page already fetched, so comparison never re-requests it. */
  loadedAudit: SiteAuditDetail | null;
}) {
  const available = useMemo(
    () => comparableRuns(project.audits),
    [project.audits],
  );
  // Seeded once from the newest runs, then owned by the customer. The project
  // refetches while a crawl is running, so recomputing this from props every
  // render would undo their choice a few seconds after they made it.
  const [selectedIds, setSelectedIds] = useState<string[]>(() =>
    available.slice(0, MAX_COMPARED_RUNS).map((run) => run.id),
  );
  const runs = useMemo(
    () => resolveSelectedRuns(available, selectedIds),
    [available, selectedIds],
  );
  // The identity of the set, not of the array: the project refetches on a poll
  // and a fresh array of the same runs must not restart the fetches below.
  const runKey = runs.map((run) => run.id).join(",");

  const [details, setDetails] = useState<Record<string, SiteAuditDetail>>({});
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const wanted = runKey ? runKey.split(",") : [];
    if (wanted.length < 2) return;

    let cancelled = false;
    setLoadError(null);

    async function load() {
      const missing = wanted.filter(
        (id) => id !== loadedAudit?.id && !(id in details),
      );
      if (missing.length === 0) return;

      setLoading(true);
      try {
        const fetched = await Promise.all(
          missing.map((id) => getSiteAudit(projectId, id, controller.signal)),
        );
        if (cancelled) return;
        setDetails((current) => ({
          ...current,
          ...Object.fromEntries(fetched.map((detail) => [detail.id, detail])),
        }));
      } catch (error) {
        if (
          cancelled ||
          (error instanceof Error && error.name === "AbortError")
        ) {
          return;
        }
        setLoadError(
          error instanceof Error
            ? error.message
            : "The earlier crawls could not be loaded.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
      controller.abort();
    };
    // `details` is deliberately absent: it is written by this effect, and
    // reading it here would restart the fetch it just satisfied.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, runKey, loadedAudit?.id]);

  if (available.length === 0) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface shadow-sm">
        <EmptyPanel
          title="Nothing to compare yet"
          message="This project has no completed crawl. Once one finishes, its results appear here."
        />
      </section>
    );
  }

  if (available.length === 1) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface shadow-sm">
        <EmptyPanel
          title="Only one crawl so far"
          message="Comparison needs at least two completed crawls. Use “Run audit again” above to crawl this site a second time, then come back."
        />
      </section>
    );
  }

  const detailsByRun = runs.map((run) =>
    run.id === loadedAudit?.id ? loadedAudit : (details[run.id] ?? null),
  );
  const issueRows: CompareCountsRow[] = compareIssues(detailsByRun).map(
    (row) => ({
      key: row.code,
      counts: row.counts,
      label: (
        <div className="flex max-w-md flex-col gap-1">
          <SeverityBadge severity={row.severity} />
          <span className="text-surface-foreground">{row.message}</span>
          <span className="font-mono text-xs text-surface-subtle">
            {row.code}
          </span>
        </div>
      ),
    }),
  );
  const schemaRows: CompareCountsRow[] = compareSchemas(detailsByRun).map(
    (row) => ({
      key: row.type,
      counts: row.counts,
      label: (
        <span className="font-medium text-surface-foreground">{row.type}</span>
      ),
      note: (runIndex) => {
        const unrecognised = row.unrecognised[runIndex];
        return unrecognised ? `${unrecognised} with unknown properties` : null;
      },
    }),
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CompareRunSelector
          runs={available}
          selectedIds={runs.map((run) => run.id)}
          onChange={setSelectedIds}
        />
        <p className="text-xs text-surface-subtle">
          Newest crawl first. Changes are read against the crawl to its right.
        </p>
      </div>

      <section
        aria-label="Crawl metrics compared"
        className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
      >
        {COMPARE_METRICS.map((metric) => (
          <CompareMetricCard key={metric.key} metric={metric} runs={runs} />
        ))}
      </section>

      {loadError ? (
        <p
          role="alert"
          className="rounded-lg bg-danger-soft p-4 text-sm text-danger-strong"
        >
          {loadError}
        </p>
      ) : null}

      {loading ? (
        <p role="status" className="text-sm text-surface-subtle">
          Loading the earlier crawls…
        </p>
      ) : null}

      <CompareCountsTable
        title="Findings by crawl"
        description="How often each finding appeared in every run. A code that drops to zero was fixed; one that appears was introduced."
        runs={runs}
        rows={issueRows}
        direction="down-is-better"
        emptyMessage="No findings were recorded in these crawls."
      />

      <CompareCountsTable
        title="Schema markup by crawl"
        description="Schema.org blocks found per run. Type and property names are checked against the bundled ontology; value types and rich-result eligibility are not."
        runs={runs}
        rows={schemaRows}
        direction="up-is-better"
        emptyMessage="No JSON-LD blocks were found in these crawls."
      />
    </div>
  );
}
