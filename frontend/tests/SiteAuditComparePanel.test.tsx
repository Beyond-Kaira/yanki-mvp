import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  SeoProjectDetail,
  SiteAuditDetail,
  SiteAuditRunSummary,
} from "@/lib/contracts";

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
    total_notices: 0,
    health_score: 70,
    created_at: "2026-08-10T09:00:00Z",
    updated_at: "2026-08-10T09:30:00Z",
    started_at: "2026-08-10T09:00:01Z",
    completed_at: "2026-08-10T09:30:00Z",
    ...over,
  };
}

function withPages(
  base: SiteAuditRunSummary,
  codes: string[],
): SiteAuditDetail {
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
          severity: "error" as const,
          message: `${code} happened`,
          details: {},
        })),
        schemas: [],
      },
    ],
  };
}

const NEWEST = summary("audit-new", {
  health_score: 88,
  pages_crawled: 40,
  total_errors: 1,
  completed_at: "2026-08-17T11:49:00Z",
});
const OLDER = summary("audit-old", {
  health_score: 70,
  pages_crawled: 20,
  total_errors: 3,
  completed_at: "2026-08-10T09:30:00Z",
});

function project(audits: SiteAuditRunSummary[]): SeoProjectDetail {
  return {
    id: "project-1",
    name: "Example",
    domain: "https://example.com/",
    created_at: "2026-08-01T09:00:00Z",
    updated_at: "2026-08-17T11:49:00Z",
    latest_audit: audits[0] ?? null,
    audits,
  };
}

describe("SiteAuditComparePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetSiteAudit.mockResolvedValue(
      withPages(OLDER, ["missing_h1", "missing_title"]),
    );
  });

  it("asks for a second crawl instead of comparing a run with itself", () => {
    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST])}
        loadedAudit={withPages(NEWEST, [])}
      />,
    );

    expect(screen.getByText(/only one crawl so far/i)).toBeInTheDocument();
    expect(mockedGetSiteAudit).not.toHaveBeenCalled();
  });

  it("charts the headline metrics straight from the run summaries", async () => {
    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST, OLDER])}
        loadedAudit={withPages(NEWEST, ["missing_h1"])}
      />,
    );

    const metrics = screen.getByRole("region", {
      name: /crawl metrics compared/i,
    });
    const card = (name: string) =>
      within(metrics).getByRole("heading", { name }).closest("article")!;

    // Health rose 70 -> 88. The headline repeats the newest run's own bar value,
    // so scope to the card rather than to the whole panel.
    expect(
      within(card("Site health")).getAllByText("88%").length,
    ).toBeGreaterThan(0);
    expect(within(card("Site health")).getByText("+18")).toBeInTheDocument();

    // Errors fell 3 -> 1: an improvement, despite the negative sign.
    expect(within(card("Errors")).getByText("-2")).toBeInTheDocument();

    // Pages crawled doubled, read from the summary with no extra request.
    expect(within(card("Pages crawled")).getByText("+20")).toBeInTheDocument();
  });

  it("fetches only the runs the page has not already loaded", async () => {
    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST, OLDER])}
        loadedAudit={withPages(NEWEST, ["missing_h1"])}
      />,
    );

    await waitFor(() => expect(mockedGetSiteAudit).toHaveBeenCalledTimes(1));
    expect(mockedGetSiteAudit).toHaveBeenCalledWith(
      "project-1",
      "audit-old",
      expect.any(AbortSignal),
    );
  });

  it("shows a finding that disappeared as zero, not as blank", async () => {
    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST, OLDER])}
        loadedAudit={withPages(NEWEST, ["missing_h1"])}
      />,
    );

    const fixed = await screen.findByText("missing_title");
    const row = fixed.closest("tr")!;
    const cells = within(row).getAllByRole("cell");
    expect(cells[1]).toHaveTextContent("0");
    expect(cells[2]).toHaveTextContent("1");
    expect(cells[3]).toHaveTextContent("-1");
  });

  it("lets the customer choose which crawls are compared", async () => {
    const user = userEvent.setup();
    const THIRD = summary("audit-third", {
      pages_crawled: 5,
      completed_at: "2026-08-01T09:30:00Z",
    });
    mockedGetSiteAudit.mockResolvedValue(withPages(THIRD, []));

    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST, OLDER, THIRD])}
        loadedAudit={withPages(NEWEST, ["missing_h1"])}
      />,
    );

    // Seeded with every run that fits, so the panel is useful before any click.
    const trigger = screen.getByRole("button", {
      name: /comparing 3 of 3 crawls/i,
    });
    await user.click(trigger);

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);
    expect(
      options.every(
        (option) => option.getAttribute("aria-selected") === "true",
      ),
    ).toBe(true);

    // Dropping one narrows the comparison to the two that remain.
    await user.click(within(options[2]).getByRole("button"));
    expect(
      screen.getByRole("button", { name: /comparing 2 of 3 crawls/i }),
    ).toBeInTheDocument();
  });

  it("refuses to drop below two crawls, since one compares with nothing", async () => {
    const user = userEvent.setup();
    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST, OLDER])}
        loadedAudit={withPages(NEWEST, ["missing_h1"])}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /comparing 2 of 2 crawls/i }),
    );
    for (const option of screen.getAllByRole("option")) {
      expect(within(option).getByRole("button")).toBeDisabled();
    }
  });

  it("surfaces a failure to load the earlier crawls", async () => {
    mockedGetSiteAudit.mockRejectedValueOnce(
      new Error("The server is offline."),
    );
    render(
      <SiteAuditComparePanel
        projectId="project-1"
        project={project([NEWEST, OLDER])}
        loadedAudit={withPages(NEWEST, ["missing_h1"])}
      />,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The server is offline.",
    );
  });
});
