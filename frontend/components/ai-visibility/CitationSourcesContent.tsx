"use client";

import { useEffect, useState } from "react";
import ModalDialog from "@/components/ModalDialog";
import {
  citationCsv,
  defaultCitationFilters,
  fetchCitationSources,
  type CitationFilters,
} from "@/lib/citation-sources";
import type { CitationSourceRow, CitationSourcesReport } from "@/lib/contracts";

const PAGE_SIZE = 25;
const inputClass =
  "rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-surface-foreground";
const buttonClass =
  "rounded-lg border border-surface-border px-3 py-2 text-sm font-medium hover:bg-surface-muted disabled:opacity-40";
const ownershipLabel = {
  owned: "Your site",
  competitor: "Competitor",
  third_party: "Third party",
};

export function CitationSourcesContent({ analysisId }: { analysisId: string }) {
  const [filters, setFilters] = useState<CitationFilters>(
    defaultCitationFilters,
  );
  const [search, setSearch] = useState("");
  const [competitors, setCompetitors] = useState("");
  const [offset, setOffset] = useState(0);
  const [report, setReport] = useState<CitationSourcesReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [selected, setSelected] = useState<CitationSourceRow | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setReport(null);
    setError(null);
    setSelected(null);
    setExportError(null);
    fetchCitationSources(
      analysisId,
      filters,
      offset,
      PAGE_SIZE,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setReport(data);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error ? cause.message : "Could not load sources.",
          );
      });
    return () => controller.abort();
  }, [analysisId, filters, offset, retry]);

  function update(patch: Partial<CitationFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
    setOffset(0);
  }

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const all = await fetchCitationSources(analysisId, filters, 0, 5000);
      if (all.total > all.rows.length)
        throw new Error("This export is too large. Narrow your filters.");
      const blob = new Blob(["\uFEFF", citationCsv(all, filters)], {
        type: "text/csv;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `cited-${filters.view}-${analysisId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setExportError(cause instanceof Error ? cause.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <p className="text-surface-subtle">
        The pages most often cited in answers to your selected industry
        questions.
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2" role="group" aria-label="Source view">
          {(["pages", "domains"] as const).map((view) => (
            <button
              key={view}
              type="button"
              aria-pressed={filters.view === view}
              className={`${buttonClass} ${filters.view === view ? "bg-primary text-white" : ""}`}
              onClick={() => update({ view })}
            >
              {view === "pages" ? "Pages" : "Domains"}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={buttonClass}
          disabled={!report?.total || exporting}
          onClick={exportCsv}
        >
          {exporting ? "Exporting…" : "Export CSV"}
        </button>
      </div>
      <form
        className="flex flex-wrap items-end gap-3 rounded-xl border border-surface-border p-4"
        onSubmit={(event) => {
          event.preventDefault();
          update({ q: search, competitor_domains: competitors });
        }}
      >
        <label className="grid gap-1 text-xs">
          Search pages
          <input
            className={inputClass}
            value={search}
            maxLength={300}
            placeholder="URL or title"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-xs">
          Competitor domains
          <input
            className={inputClass}
            value={competitors}
            maxLength={1000}
            placeholder="rival.com, another.com"
            onChange={(event) => setCompetitors(event.target.value)}
          />
        </label>
        <button type="submit" className={buttonClass}>
          Apply
        </button>
        <label className="grid gap-1 text-xs">
          Model
          <select
            className={inputClass}
            value={filters.model}
            onChange={(e) => update({ model: e.target.value })}
          >
            <option value="">All models</option>
            {(
              report?.scope.models ?? (filters.model ? [filters.model] : [])
            ).map((model) => (
              <option key={model}>{model}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          Question group
          <select
            className={inputClass}
            value={filters.prompt_group}
            onChange={(e) => update({ prompt_group: e.target.value })}
          >
            <option value="">All groups</option>
            {(
              report?.scope.prompt_groups ??
              (filters.prompt_group ? [filters.prompt_group] : [])
            ).map((group) => (
              <option key={group}>{group}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          Ownership
          <select
            className={inputClass}
            value={filters.ownership}
            onChange={(e) =>
              update({
                ownership: e.target.value as CitationFilters["ownership"],
              })
            }
          >
            <option value="">All sources</option>
            <option value="owned">Your site</option>
            <option value="competitor">Competitors</option>
            <option value="third_party">Third parties</option>
          </select>
        </label>
        <label className="flex items-center gap-2 py-2 text-sm">
          <input
            type="checkbox"
            checked={filters.opportunities}
            onChange={(e) => update({ opportunities: e.target.checked })}
          />
          Source opportunities
        </label>
      </form>
      <p className="text-xs text-surface-subtle">
        Competitor ownership uses the domains you enter. Opportunities show
        third-party sources in answers mentioning known competitors but not your
        brand.
      </p>
      {exportError && <p role="alert">{exportError}</p>}
      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-surface-border p-5"
        >
          <p>{error}</p>
          <button
            type="button"
            className={`${buttonClass} mt-3`}
            onClick={() => setRetry((n) => n + 1)}
          >
            Retry
          </button>
        </div>
      ) : !report ? (
        <p role="status">Loading citation sources…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Cited pages", report.summary.pages],
              ["Source domains", report.summary.domains],
              ["Eligible answers", report.coverage.eligible_responses],
              ["Questions measured", report.coverage.eligible_prompts],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-xl border border-surface-border p-4"
              >
                <p className="text-xs text-surface-subtle">{label}</p>
                <p className="mt-2 text-2xl font-semibold">
                  {report.scope.provenance === "grounded" &&
                  report.coverage.eligible_responses > 0
                    ? value
                    : "—"}
                </p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-surface-border bg-surface-muted p-4 text-sm text-surface-subtle">
            <p className="font-medium text-surface-foreground">
              {report.scope.sector || "Selected questions"} ·{" "}
              {report.scope.observed_at
                ? new Date(report.scope.observed_at).toLocaleString()
                : "Date unavailable"}
            </p>
            <p className="mt-2">{report.methodology}</p>
            {(report.coverage.excluded_responses > 0 ||
              report.coverage.rejected_citations > 0) && (
              <p className="mt-2">
                Excluded answers: {report.coverage.excluded_responses}. Rejected
                citations: {report.coverage.rejected_citations}.{" "}
                {Object.entries(report.coverage.exclusion_reasons ?? {})
                  .map(
                    ([reason, count]) =>
                      `${reason.replaceAll("_", " ")}: ${count}`,
                  )
                  .join(" · ")}{" "}
                {Object.entries(report.coverage.rejection_reasons ?? {})
                  .map(
                    ([reason, count]) =>
                      `${reason.replaceAll("_", " ")}: ${count}`,
                  )
                  .join(" · ")}
              </p>
            )}
          </div>
          {report.rows.length === 0 ? (
            <div
              className="rounded-xl border border-dashed border-surface-border p-8 text-center"
              role="status"
            >
              <h2 className="font-semibold">
                {report.scope.provenance === "mock"
                  ? "Demo data is excluded from rankings"
                  : report.scope.provenance === "simulated"
                    ? "Simulated sources are excluded from rankings"
                    : report.scope.provenance === "unknown"
                      ? "This run’s measurement origin is unverified"
                      : report.coverage.eligible_responses === 0
                        ? "No eligible answers for this selection"
                        : "No verified citations match this selection"}
              </h2>
              <p className="mt-2 text-sm text-surface-subtle">
                {report.scope.provenance === "grounded"
                  ? "Try a different model, question group or source filter. Only sources linked to stored search evidence and cited in an answer are listed."
                  : "Run a new measured analysis to build an evidence-backed source ranking."}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-surface-border">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">
                  Top cited {filters.view}, ranked by distinct answers
                </caption>
                <thead className="bg-surface-muted text-xs text-surface-subtle">
                  <tr>
                    <th scope="col" className="px-4 py-3">
                      {filters.view === "pages" ? "Page" : "Domain"}
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Ownership
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Answers
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Coverage
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Questions
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Models
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.rows.map((row) => (
                    <tr
                      key={row.key}
                      className="border-t border-surface-border"
                    >
                      <td className="min-w-64 max-w-md px-4 py-4">
                        <button
                          type="button"
                          className="text-left font-medium text-primary hover:underline"
                          onClick={() => setSelected(row)}
                        >
                          {row.title}
                        </button>
                        <p className="mt-1 break-all text-xs text-surface-subtle">
                          {row.url ||
                            `${row.page_count} cited pages on ${row.domain}`}
                        </p>
                      </td>
                      <td className="px-4 py-4">
                        {ownershipLabel[row.ownership]}
                      </td>
                      <td className="px-4 py-4 tabular-nums">
                        {row.response_count}
                      </td>
                      <td className="px-4 py-4 tabular-nums">
                        {row.response_coverage == null
                          ? "—"
                          : `${row.response_coverage}%`}
                      </td>
                      <td className="px-4 py-4 tabular-nums">
                        {row.prompt_count}
                      </td>
                      <td className="px-4 py-4 text-xs">
                        {row.models.join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex items-center justify-between text-sm">
            <p>
              {report.total} {filters.view} · {report.total ? offset + 1 : 0}–
              {Math.min(offset + PAGE_SIZE, report.total)}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className={buttonClass}
                disabled={offset === 0}
                onClick={() => setOffset((n) => Math.max(0, n - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className={buttonClass}
                disabled={offset + PAGE_SIZE >= report.total}
                onClick={() => setOffset((n) => n + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
      {selected && (
        <ModalDialog
          labelledBy="citation-details-title"
          onDismiss={() => setSelected(null)}
          panelClassName="w-full sm:max-w-3xl"
        >
          <div className="max-h-[80dvh] overflow-y-auto p-6">
            <div className="flex items-start justify-between gap-4">
              <h2
                id="citation-details-title"
                className="break-words text-xl font-semibold"
              >
                {selected.title}
              </h2>
              <button
                type="button"
                className={buttonClass}
                onClick={() => setSelected(null)}
              >
                Close
              </button>
            </div>
            <p className="mt-2 text-sm text-surface-subtle">
              {selected.response_count} distinct answers ·{" "}
              {selected.prompt_count} questions
            </p>
            <div className="mt-5 space-y-5">
              {selected.evidence.map((item) => (
                <article
                  key={`${item.response_id}-${item.source_url}`}
                  className="rounded-xl border border-surface-border p-4"
                >
                  <h3 className="font-semibold">{item.prompt}</h3>
                  <p className="mt-1 text-xs text-surface-subtle">
                    {item.model} ·{" "}
                    {item.observed_at
                      ? new Date(item.observed_at).toLocaleString()
                      : "Date unavailable"}
                  </p>
                  <p className="mt-3 whitespace-pre-wrap text-sm">
                    {item.answer}
                  </p>
                  <a
                    className="mt-3 block break-all text-sm text-primary hover:underline"
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Source [{item.result_rank}]: {item.source_url}
                  </a>
                  <p className="mt-2 text-xs text-surface-subtle">
                    Brand in answer:{" "}
                    {item.mentioned == null
                      ? "Unknown"
                      : item.mentioned
                        ? "Yes"
                        : "No"}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </ModalDialog>
      )}
    </>
  );
}
