import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CitationSourcesContent } from "@/components/ai-visibility/CitationSourcesContent";
import { citationCsv, fetchCitationSources } from "@/lib/citation-sources";
import type { CitationSourcesReport } from "@/lib/contracts";

vi.mock("@/lib/citation-sources", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("@/lib/citation-sources")>();
  return { ...original, fetchCitationSources: vi.fn() };
});

const report: CitationSourcesReport = {
  scope: {
    analysis_id: "run-1",
    sector: "Software",
    observed_at: "2026-09-17T10:00:00Z",
    provenance: "grounded",
    models: ["model-a", "model-b"],
    prompt_groups: ["recommendation"],
    competitor_domains: [],
  },
  methodology: "Grounded in Tavily. Not native platform observations.",
  coverage: {
    eligible_responses: 4,
    eligible_prompts: 2,
    excluded_responses: 1,
    rejected_citations: 0,
    exclusion_reasons: { failed_or_unverified_answer: 1 },
    rejection_reasons: {},
  },
  summary: { pages: 1, domains: 1 },
  offset: 0,
  limit: 25,
  total: 1,
  rows: [
    {
      key: "https://publisher.test/guide",
      url: "https://publisher.test/guide",
      title: "A useful guide",
      domain: "publisher.test",
      ownership: "third_party",
      response_count: 2,
      prompt_count: 1,
      page_count: 1,
      response_coverage: 50,
      models: ["model-a"],
      evidence: [
        {
          response_id: "answer-1",
          prompt_id: "prompt-1",
          prompt: "Best tools?",
          model: "model-a",
          answer: "Read the guide [1].",
          source_url: "https://publisher.test/guide",
          result_rank: 1,
          observed_at: "2026-09-17T10:00:00Z",
          mentioned: null,
          competitors: [],
        },
      ],
    },
  ],
};

beforeEach(() => {
  vi.mocked(fetchCitationSources)
    .mockReset()
    .mockResolvedValue(structuredClone(report));
});

describe("Citation sources", () => {
  it("shows counts and opens the underlying answer with a source link", async () => {
    render(<CitationSourcesContent analysisId="run-1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "A useful guide" }),
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Best tools?")).toBeInTheDocument();
    expect(within(dialog).getByText("Read the guide [1].")).toBeInTheDocument();
    expect(within(dialog).getByRole("link")).toHaveAttribute(
      "href",
      "https://publisher.test/guide",
    );
    expect(
      within(dialog).getByText("Brand in answer: Unknown"),
    ).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("sends model and domain view filters to the shared count path", async () => {
    render(<CitationSourcesContent analysisId="run-1" />);
    await screen.findByText("A useful guide");
    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: "model-b" },
    });
    await waitFor(() =>
      expect(fetchCitationSources).toHaveBeenLastCalledWith(
        "run-1",
        expect.objectContaining({ model: "model-b" }),
        0,
        25,
        expect.any(AbortSignal),
      ),
    );
    await screen.findByText("A useful guide");
    fireEvent.click(screen.getByRole("button", { name: "Domains" }));
    await waitFor(() =>
      expect(fetchCitationSources).toHaveBeenLastCalledWith(
        "run-1",
        expect.objectContaining({ model: "model-b", view: "domains" }),
        0,
        25,
        expect.any(AbortSignal),
      ),
    );
  });

  it("explains unknown data without presenting zero performance", async () => {
    vi.mocked(fetchCitationSources).mockResolvedValue({
      ...report,
      rows: [],
      total: 0,
      scope: { ...report.scope, provenance: "unknown" },
    });
    render(<CitationSourcesContent analysisId="run-1" />);
    expect(
      await screen.findByText("This run’s measurement origin is unverified"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(4);
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
  });

  it("exposes a retry after a request fails", async () => {
    vi.mocked(fetchCitationSources).mockRejectedValueOnce(
      new Error("Unavailable"),
    );
    render(<CitationSourcesContent analysisId="run-1" />);
    await screen.findByText("Unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("A useful guide")).toBeInTheDocument();
  });

  it("ignores a stale response after changing a filter", async () => {
    let resolveOld!: (data: CitationSourcesReport) => void;
    vi.mocked(fetchCitationSources).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
    render(<CitationSourcesContent analysisId="run-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Domains" }));
    await screen.findByText("A useful guide");
    resolveOld({ ...report, rows: [], total: 0 });
    await waitFor(() =>
      expect(screen.getByText("A useful guide")).toBeInTheDocument(),
    );
  });

  it("escapes CSV formulas and includes methodology", () => {
    const data = structuredClone(report);
    data.rows[0].title = '=HYPERLINK("https://bad.test")';
    const csv = citationCsv(data);
    expect(csv).toContain('"\'=HYPERLINK(""https://bad.test"")"');
    expect(csv).toContain(report.methodology);
    expect(csv).toContain('"Eligible answers"');
    expect(csv).toContain('"Applied filters"');
    expect(csv).toContain('"grounded"');
    expect(csv).toContain('"50"');
  });

  describe("CSV download", () => {
    const createObjectURL = vi.fn<(blob: Blob) => string>(
      () => "blob:citation-export",
    );
    const revokeObjectURL = vi.fn();
    let downloadedLink: HTMLAnchorElement;

    beforeEach(() => {
      createObjectURL.mockClear();
      revokeObjectURL.mockClear();
      vi.stubGlobal(
        "URL",
        class extends URL {
          static createObjectURL = createObjectURL;
          static revokeObjectURL = revokeObjectURL;
        },
      );
      vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
        function (this: HTMLAnchorElement) {
          downloadedLink = this;
        },
      );
    });

    afterEach(() => {
      vi.restoreAllMocks();
      vi.unstubAllGlobals();
    });

    it("downloads all matching rows with applied filters and releases the file URL", async () => {
      render(<CitationSourcesContent analysisId="run-1" />);
      await screen.findByText("A useful guide");
      fireEvent.change(screen.getByLabelText("Search pages"), {
        target: { value: "guide" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Apply" }));
      await screen.findByText("A useful guide");
      // A draft edit must not silently change the exported filter.
      fireEvent.change(screen.getByLabelText("Search pages"), {
        target: { value: "unapplied search" },
      });
      const rows = Array.from({ length: 26 }, (_, index) => ({
        ...report.rows[0],
        key: `https://publisher.test/guide-${index}`,
        url: `https://publisher.test/guide-${index}`,
        title: `Guide ${index}`,
      }));
      vi.mocked(fetchCitationSources).mockResolvedValueOnce({
        ...report,
        rows,
        total: 26,
        limit: 5000,
      });
      fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

      await waitFor(() => expect(createObjectURL).toHaveBeenCalledOnce());
      expect(fetchCitationSources).toHaveBeenLastCalledWith(
        "run-1",
        expect.objectContaining({ q: "guide" }),
        0,
        5000,
      );
      const blob = createObjectURL.mock.calls[0][0] as Blob;
      expect(blob.type).toBe("text/csv;charset=utf-8");
      const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as ArrayBuffer);
        reader.onerror = () => reject(reader.error);
        reader.readAsArrayBuffer(blob);
      });
      expect(Array.from(new Uint8Array(bytes).slice(0, 3))).toEqual([
        239, 187, 191,
      ]);
      const csv = new TextDecoder().decode(bytes);
      expect(csv.split("\r\n")).toHaveLength(27);
      expect(csv).toContain('"Guide 25"');
      expect(csv).toContain('""q"":""guide""');
      expect(csv).not.toContain("unapplied search");
      const click = vi.mocked(HTMLAnchorElement.prototype.click);
      expect(click).toHaveBeenCalledOnce();
      const link = downloadedLink;
      expect(link.download).toBe("cited-pages-run-1.csv");
      expect(link.getAttribute("href")).toBe("blob:citation-export");
      expect(link.isConnected).toBe(false);
      await waitFor(
        () =>
          expect(revokeObjectURL).toHaveBeenCalledWith("blob:citation-export"),
        { timeout: 2000 },
      );
    });

    it.each([5000, 5001])(
      "handles the export boundary when %i rows match",
      async (total) => {
        render(<CitationSourcesContent analysisId="run-1" />);
        await screen.findByText("A useful guide");
        vi.mocked(fetchCitationSources).mockResolvedValueOnce({
          ...report,
          rows: Array.from({ length: 5000 }, () => ({ ...report.rows[0] })),
          total,
          limit: 5000,
        });
        fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
        if (total === 5001) {
          expect(await screen.findByRole("alert")).toHaveTextContent(
            "This export is too large. Narrow your filters.",
          );
          expect(createObjectURL).not.toHaveBeenCalled();
          expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
        } else {
          await waitFor(() =>
            expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce(),
          );
          expect(screen.queryByRole("alert")).not.toBeInTheDocument();
          await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledOnce(), {
            timeout: 2000,
          });
        }
        expect(
          screen.getByRole("button", { name: "Export CSV" }),
        ).toBeEnabled();
      },
    );

    it("prevents duplicate requests while exporting and allows retry after failure", async () => {
      render(<CitationSourcesContent analysisId="run-1" />);
      await screen.findByText("A useful guide");
      let rejectExport!: (reason: Error) => void;
      vi.mocked(fetchCitationSources).mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            rejectExport = reject;
          }),
      );
      fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
      const pending = screen.getByRole("button", { name: "Exporting…" });
      expect(pending).toBeDisabled();
      fireEvent.click(pending);
      expect(fetchCitationSources).toHaveBeenCalledTimes(2);
      rejectExport(new Error("Export service unavailable"));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Export service unavailable",
      );
      expect(createObjectURL).not.toHaveBeenCalled();
      expect(screen.getByText("A useful guide")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
      await waitFor(() =>
        expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce(),
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Export CSV" })).toBeEnabled();
      await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledOnce(), {
        timeout: 2000,
      });
    });
  });
});
