import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  SeoProjectDetail,
  SiteAuditDetail,
  SiteAuditRunSummary,
} from "@/lib/contracts";
import { axeCheck } from "./a11y";

const mockedGetSiteAudit = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ getSiteAudit: mockedGetSiteAudit }));

import SiteAuditComparePanel from "@/components/site-audit/compare/SiteAuditComparePanel";

function summary(
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
    pages_discovered: 20,
    pages_crawled: 20,
    total_errors: 2,
    total_warnings: 1,
    total_notices: 1,
    health_score: 70,
    created_at: "2026-08-10T09:00:00Z",
    updated_at: "2026-08-10T09:30:00Z",
    started_at: "2026-08-10T09:00:01Z",
    completed_at: "2026-08-10T09:30:00Z",
    ...over,
  };
}

function detail(base: SiteAuditRunSummary, codes: string[]): SiteAuditDetail {
  return {
    ...base,
    pages: [
      {
        id: `${base.id}-page`,
        requested_url: "https://example.com/",
        final_url: "https://example.com/",
        status_code: 200,
        title: "Example",
        h1_count: 1,
        html_lang: "en",
        meta_description: null,
        created_at: "2026-08-10T09:00:05Z",
        issues: codes.map((code) => ({
          code,
          severity: "warning" as const,
          message: `${code} happened`,
          details: {},
        })),
        schemas: [
          {
            type: "Organization",
            syntax_valid: true,
            structure_status: "ok",
            details: { valid_fields: ["name"], invalid_fields: [] },
            error_detail: null,
          },
        ],
      },
    ],
  };
}

const NEWEST = summary("audit-new", { completed_at: "2026-08-17T11:49:00Z" });
const OLDER = summary("audit-old");

const PROJECT: SeoProjectDetail = {
  id: "project-1",
  name: "Example",
  domain: "https://example.com/",
  created_at: "2026-08-01T09:00:00Z",
  updated_at: "2026-08-17T11:49:00Z",
  latest_audit: NEWEST,
  audits: [NEWEST, OLDER],
};

describe("SiteAuditComparePanel accessibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetSiteAudit.mockResolvedValue(
      detail(OLDER, ["missing_h1", "short_title"]),
    );
  });

  it("has no axe violations once both crawls are compared", async () => {
    const { container } = render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={PROJECT}
        loadedAudit={detail(NEWEST, ["missing_h1"])}
      />,
    );

    await screen.findByText("short_title");
    expect(await axeCheck(container)).toHaveNoViolations();
  });

  it("has no axe violations in the single-crawl empty state", async () => {
    const { container } = render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={{ ...PROJECT, audits: [NEWEST] }}
        loadedAudit={detail(NEWEST, [])}
      />,
    );

    expect(await axeCheck(container)).toHaveNoViolations();
  });
});
