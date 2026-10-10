import { authorizedFetch, ApiError, readErrorMessage } from "./api";
import type { CitationSourcesReport } from "./contracts";

export interface CitationFilters {
  view: "pages" | "domains";
  model: string;
  prompt_group: string;
  ownership: "" | "owned" | "competitor" | "third_party";
  q: string;
  competitor_domains: string;
  opportunities: boolean;
}

export const defaultCitationFilters: CitationFilters = {
  view: "pages",
  model: "",
  prompt_group: "",
  ownership: "",
  q: "",
  competitor_domains: "",
  opportunities: false,
};

export async function fetchCitationSources(
  analysisId: string,
  filters: CitationFilters,
  offset = 0,
  limit = 25,
  signal?: AbortSignal,
): Promise<CitationSourcesReport> {
  const query = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  for (const [key, value] of Object.entries(filters)) {
    if (value !== "") query.set(key, String(value));
  }
  const response = await authorizedFetch(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/citation-sources?${query}`,
    { signal },
  );
  if (!response.ok)
    throw new ApiError(await readErrorMessage(response), response.status);
  return response.json() as Promise<CitationSourcesReport>;
}

function cell(value: unknown): string {
  const text = String(value ?? "");
  // Spreadsheet applications can execute cells beginning with these characters.
  const safe = /^[\s]*[=+@-]|^[\t\r\n]/.test(text) ? `'${text}` : text;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function citationCsv(
  report: CitationSourcesReport,
  filters: CitationFilters = defaultCitationFilters,
): string {
  const headers = [
    "Page / domain",
    "Title",
    "Ownership",
    "Answers",
    "Questions",
    "Pages",
    "Answer coverage (%)",
    "Models",
    "Analysis",
    "Sector",
    "Observed at",
    "Methodology",
    "Provenance",
    "Eligible answers",
    "Applied filters",
  ];
  const rows = report.rows.map((row) => [
    row.url || row.domain,
    row.title,
    row.ownership,
    row.response_count,
    row.prompt_count,
    row.page_count,
    row.response_coverage,
    row.models.join("; "),
    report.scope.analysis_id,
    report.scope.sector,
    report.scope.observed_at,
    report.methodology,
    report.scope.provenance,
    report.coverage.eligible_responses,
    JSON.stringify(filters),
  ]);
  return [headers, ...rows].map((row) => row.map(cell).join(",")).join("\r\n");
}
