import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  it("ranks the real run data and opens matching actions from the map", async () => {
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
    expect(screen.getByRole("table")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Fix owned pages" }),
    );
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
    const highImpact = screen.getByRole("button", {
      name: /impact 4 of 5 and effort 1 of 5/i,
    });
    await userEvent.click(highImpact);
    expect(highImpact).toHaveAttribute("aria-pressed", "true");
    expect(
      within(
        screen.getByRole("region", { name: "Selected recommendations" }),
      ).getByText(/Showing 1 action/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Fix owned pages" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Improve comparison content" }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /impact 3 of 5 and effort 3 of 5/i }),
    );
    expect(
      screen.getByRole("button", { name: "Improve comparison content" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Fix owned pages" }),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("Category"),
      "codebase",
    );
    expect(
      screen.getByRole("button", { name: "Fix owned pages" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Improve comparison content" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /explore drivers & gaps/i }),
    ).toHaveAttribute("href", "/ai-visibility/drivers?analysis=run-123");
  });

  it("paginates long results and filters by impact and effort", async () => {
    const interventions = Array.from({ length: 12 }, (_, index) => ({
      id: `action-${index}`,
      title: `Action ${index + 1}`,
      priority_score: 12 - index,
      geo_impact_score: index < 2 ? 5 : 1,
      applicability_score: index === 0 ? 1 : 5,
    }));
    render(
      <InterventionsContent
        model={interventionsFromAnalysis(analysisWith(interventions))}
      />,
    );

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(11);
    expect(
      screen.queryByRole("button", { name: "Action 12" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Action 12" }),
    ).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Impact"), "high");
    expect(
      screen.getByText("2 of 12 recommendations shown"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Page 2 of 2")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Action 1" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Action 12" }),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Effort"), "low");
    expect(
      screen.getByText("1 of 12 recommendations shown"),
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Effort"), "all");
    await userEvent.selectOptions(screen.getByLabelText("Impact"), "low");
    expect(
      screen.getByText("10 of 12 recommendations shown"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Action 12" }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Effort"), "low");
    expect(
      screen.getByText("No recommendations match these filters."),
    ).toBeInTheDocument();
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
