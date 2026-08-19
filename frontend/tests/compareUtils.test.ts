import { describe, expect, it } from "vitest";
import {
  changeTone,
  comparableRuns,
  resolveSelectedRuns,
  compareIssues,
  compareSchemas,
  totalIssues,
} from "@/components/site-audit/compare/compareUtils";
import type { SiteAuditDetail, SiteAuditRunSummary } from "@/lib/contracts";

function run(
  id: string,
  over: Partial<SiteAuditRunSummary> = {},
): SiteAuditRunSummary {
  return {
    id,
    project_id: "project-1",
    status: "done",
    progress: 100,
    current_step: null,
    error: null,
    page_limit: 100,
    profile_id: "site_audit_mobile",
    js_rendering: true,
    pages_discovered: 10,
    pages_crawled: 10,
    total_errors: 1,
    total_warnings: 2,
    total_notices: 3,
    health_score: 80,
    created_at: "2026-08-04T09:00:00Z",
    updated_at: "2026-08-04T09:05:00Z",
    started_at: "2026-08-04T09:00:01Z",
    completed_at: "2026-08-04T09:05:00Z",
    ...over,
  };
}

function detail(
  id: string,
  codes: string[],
  schemaTypes: string[] = [],
): SiteAuditDetail {
  return {
    ...run(id),
    pages: [
      {
        id: `${id}-page`,
        requested_url: "https://example.com/",
        final_url: "https://example.com/",
        status_code: 200,
        title: "x",
        h1_count: 1,
        html_lang: "en",
        meta_description: null,
        created_at: "2026-08-04T09:00:02Z",
        issues: codes.map((code) => ({
          code,
          severity: "error" as const,
          message: `${code} happened`,
          details: {},
        })),
        schemas: schemaTypes.map((type) => ({
          type,
          syntax_valid: true,
          structure_status: "ok",
          details: { valid_fields: [], invalid_fields: [] },
          error_detail: null,
        })),
      },
    ],
  };
}

describe("compareUtils", () => {
  it("compares only completed runs, newest first, up to the limit", () => {
    const audits = [
      run("a", { status: "running" }),
      run("b"),
      run("c"),
      run("d", { status: "failed" }),
      run("e"),
      run("f"),
    ];
    expect(comparableRuns(audits, 3).map((item) => item.id)).toEqual([
      "b",
      "c",
      "e",
    ]);
  });

  it("keeps the customer's pick across a poll, and prunes runs that vanished", () => {
    const available = [run("a"), run("b"), run("c"), run("d")];

    // An explicit pick survives, newest-first, regardless of the order asked for.
    expect(
      resolveSelectedRuns(available, ["c", "a"]).map((item) => item.id),
    ).toEqual(["a", "c"]);

    // A run that no longer exists is dropped, and the rest still stand.
    expect(
      resolveSelectedRuns(available, ["b", "gone", "d"]).map((item) => item.id),
    ).toEqual(["b", "d"]);

    // Too few left to compare: fall back to the default rather than render a
    // state the customer never chose.
    expect(
      resolveSelectedRuns(available, ["gone"]).map((item) => item.id),
    ).toEqual(["a", "b", "c"]);

    // Never more columns than fit.
    expect(
      resolveSelectedRuns(available, ["a", "b", "c", "d"]).map(
        (item) => item.id,
      ),
    ).toEqual(["a", "b", "c"]);
  });

  it("adds the three severities into a single issue total", () => {
    expect(totalIssues(run("a"))).toBe(6);
  });

  it("reads improvement in the metric’s own direction", () => {
    expect(changeTone(90, 80, "up-is-better")).toBe("better");
    expect(changeTone(70, 80, "up-is-better")).toBe("worse");
    expect(changeTone(5, 9, "down-is-better")).toBe("better");
    expect(changeTone(9, 5, "down-is-better")).toBe("worse");
    // Notices are informational, so a change is neither a win nor a regression.
    expect(changeTone(9, 5, "neutral")).toBe("same");
    // A run without a health score must not be reported as progress.
    expect(changeTone(null, 80, "up-is-better")).toBe("unknown");
  });

  it("counts a fixed finding as zero, and an unloaded run as unknown", () => {
    const rows = compareIssues([
      detail("newest", ["missing_h1"]),
      null,
      detail("oldest", ["missing_h1", "missing_title"]),
    ]);

    const h1 = rows.find((row) => row.code === "missing_h1");
    expect(h1?.counts).toEqual([1, null, 1]);

    // Present in the oldest run, absent from the loaded newest one: fixed, so a
    // real zero — not a blank that would hide the win.
    const title = rows.find((row) => row.code === "missing_title");
    expect(title?.counts).toEqual([0, null, 1]);
  });

  it("tracks schema types across runs the same way", () => {
    const rows = compareSchemas([
      detail("newest", [], ["Organization"]),
      detail("oldest", [], ["Organization", "FAQPage"]),
    ]);

    expect(rows.find((row) => row.type === "Organization")?.counts).toEqual([
      1, 1,
    ]);
    expect(rows.find((row) => row.type === "FAQPage")?.counts).toEqual([0, 1]);
  });
});
