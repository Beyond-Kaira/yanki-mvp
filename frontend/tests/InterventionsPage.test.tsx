import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InterventionsContent } from "@/app/ai-visibility/interventions/InterventionsClient";
import { interventionsFromAnalysis } from "@/lib/ai-visibility-data";
import type { Analysis } from "@/lib/contracts";

function analysisWith(interventions: unknown[]): Analysis {
  return {
    id: "run-123",
    url: "https://example.com",
    result: { kyc: null, interventions },
  } as unknown as Analysis;
}

describe("recommended interventions page", () => {
  it("ranks the real run data and explains impact, effort and evidence", () => {
    const model = interventionsFromAnalysis(
      analysisWith([
        {
          id: "later",
          title: "Improve comparison content",
          label: "content",
          priority_score: 1,
          geo_impact_score: 3,
          applicability_score: 3,
        },
        {
          id: "first",
          title: "Fix owned pages",
          description: "Make the answer easy to retrieve.",
          label: "codebase",
          priority_score: 4,
          geo_impact_score: 4,
          applicability_score: 1,
          expected_outcome: "More owned citations",
          trigger_count: 2,
          triggered_prompts: ["best tools", "best tools", "compare tools"],
          triggered_by: {
            gap_claims: ["Owned pages are missing"],
            evidence: ["search_visibility.owned_domain_in_results=false"],
          },
        },
      ]),
    );

    expect(model.interventions.map((item) => item.id)).toEqual([
      "first",
      "later",
    ]);
    render(<InterventionsContent model={model} />);

    expect(
      screen.getByText("A focused action plan for example.com"),
    ).toBeInTheDocument();
    expect(screen.getByText("More owned citations")).toBeInTheDocument();
    expect(screen.getByText("• Owned pages are missing")).toBeInTheDocument();
    expect(
      screen.getByText("Owned domain missing from search results"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("High impact, low effort").previousSibling,
    ).toHaveTextContent("1");
    expect(
      screen.getByText("Distinct matched prompts").previousSibling,
    ).toHaveTextContent("2");
    expect(
      screen.getByRole("link", { name: /impact 4 of 5 and effort 1 of 5/i }),
    ).toHaveAttribute("href", "#intervention-1");
    expect(
      screen.getByRole("link", { name: /explore drivers & gaps/i }),
    ).toHaveAttribute("href", "/ai-visibility/drivers?analysis=run-123");
  });

  it("offers the gap view when no intervention matched", () => {
    render(
      <InterventionsContent
        model={interventionsFromAnalysis(analysisWith([]))}
      />,
    );
    expect(
      screen.getByText("No interventions for this run yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review drivers and gaps" }),
    ).toHaveAttribute("href", "/ai-visibility/drivers?analysis=run-123");
  });
});
