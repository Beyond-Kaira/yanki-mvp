import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import IntentHeatmap from "@/components/charts/IntentHeatmap";
import OverviewInsightCards from "@/components/ai-visibility/OverviewInsightCards";
import EntityCoverage from "@/components/insights/EntityCoverage";
import EntityLandscape from "@/components/insights/EntityLandscape";
import MentionShare from "@/components/insights/MentionShare";
import MultiLlmComparison from "@/components/insights/MultiLlmComparison";
import VisibilityDrivers from "@/components/insights/VisibilityDrivers";
import VisibilityGap from "@/components/insights/VisibilityGap";
import type { EngineInsight } from "@/lib/insights";
import type { Insights } from "@/lib/insights";

const engines: EngineInsight[] = [
  {
    engine: "openai",
    mentioned: 3,
    total: 4,
    groups: [
      { group: "discovery", mentioned: 2, total: 2 },
      { group: "comparison", mentioned: 1, total: 1 },
      { group: "recommendation", mentioned: 0, total: 1 },
    ],
    brandAnswers: 3,
    competitors: [
      { name: "Globex", answers: 2 },
      { name: "Initech", answers: 1 },
    ],
    share: 0.5,
    firstMentions: 2,
  },
  {
    engine: "anthropic",
    mentioned: 2,
    total: 4,
    groups: [
      { group: "discovery", mentioned: 1, total: 2 },
      { group: "comparison", mentioned: 0, total: 1 },
      { group: "recommendation", mentioned: 1, total: 1 },
    ],
    brandAnswers: 2,
    competitors: [{ name: "Globex", answers: 2 }],
    share: 0.5,
    firstMentions: 1,
  },
];

describe("visibility insights", () => {
  it("reads the question count from the run", () => {
    render(<MultiLlmComparison engines={engines} />);

    expect(
      screen.getByText(
        "The same 4 questions, answered separately by each engine on the panel.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps the original single-hue green heatmap", () => {
    const { container } = render(<IntentHeatmap engines={engines} />);

    expect(container.querySelector(".bg-primary")).toBeInTheDocument();
    expect(container.innerHTML).toContain("bg-primary/40");
    expect(container.querySelector(".bg-danger")).not.toBeInTheDocument();
    expect(container.querySelector(".bg-warning")).not.toBeInTheDocument();
  });

  it("shows competitor labels below mention-share bars", () => {
    render(<MentionShare brand="Yanki Demo Co" engines={engines} />);

    expect(screen.getAllByText(/Globex ·/)).toHaveLength(2);
    expect(screen.getByText(/Initech ·/)).toBeInTheDocument();
  });

  it("explains entity relationships and uses the scored-answer denominator", () => {
    render(
      <EntityLandscape
        scoredAnswers={12}
        landscape={{
          coreThreshold: 6,
          entities: [
            {
              name: "Yanki Demo Co",
              answers: 6,
              ownership: "ours",
              tier: "core",
            },
            {
              name: "Warehouse automation",
              answers: 3,
              ownership: "shared",
              tier: "secondary",
            },
            {
              name: "Globex",
              answers: 9,
              ownership: "competitor",
              tier: "core",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("How to read this")).toBeInTheDocument();
    expect(screen.getByText("Associated with you")).toBeInTheDocument();
    expect(screen.getByText("Seen without you")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Yanki Demo Co: present in 6 of 12 scored answers",
      }),
    ).toHaveAttribute("aria-valuenow", "50");
    expect(
      screen.getByRole("progressbar", {
        name: "Warehouse automation: present in 3 of 12 scored answers",
      }),
    ).toHaveAttribute("aria-valuenow", "25");
  });

  it("shows coverage as tracked profile terms and explains each status", () => {
    render(
      <EntityCoverage
        brand="Yanki Demo Co"
        scoredAnswers={12}
        coverage={{
          present: 1,
          total: 4,
          entities: [
            {
              name: "Warehouse automation",
              answers: 4,
              ownership: "shared",
              tier: "secondary",
              presence: "present",
            },
            {
              name: "Cobot",
              answers: 3,
              ownership: "competitor",
              tier: "secondary",
              presence: "high-impact-missing",
            },
            {
              name: "Safety scanner",
              answers: 0,
              ownership: "unclaimed",
              tier: "none",
              presence: "missing",
            },
            {
              name: "Predictive maintenance",
              answers: 0,
              ownership: "unclaimed",
              tier: "none",
              presence: "missing",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(
      screen.getByText("1 of 4 profile terms are covered"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: /1 covered, 1 association opportunities, and 2 not observed/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cobot")).toBeInTheDocument();
    expect(screen.getByText("3/12")).toBeInTheDocument();
  });

  it("groups answer gaps into three readable intent families", () => {
    render(
      <VisibilityGap
        gap={{
          answersLost: 5,
          total: 8,
          categories: [
            { category: "makers", total: 2, lost: 1, competitors: ["Globex"] },
            {
              category: "best-of",
              total: 1,
              lost: 1,
              competitors: ["Initech"],
            },
            { category: "comparison", total: 1, lost: 1, competitors: [] },
            { category: "alternatives", total: 1, lost: 0, competitors: [] },
            { category: "recommendation", total: 2, lost: 1, competitors: [] },
            { category: "use-case", total: 1, lost: 1, competitors: [] },
          ],
        }}
      />,
    );

    expect(
      screen.getByRole("img", {
        name: "Answer visibility gap: 5 competitor-only answers out of 8",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Other outcome")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Discovery gap: 2 of 3 answers",
      }),
    ).toHaveAttribute("aria-valuenow", "67");
  });

  it("groups visibility drivers and keeps answer rate separate from mention share", () => {
    render(
      <VisibilityDrivers
        promptSet="mvp"
        drivers={[
          { category: "makers", mentioned: 1, total: 2, contribution: 0.2 },
          { category: "best-of", mentioned: 0, total: 1, contribution: 0 },
          { category: "comparison", mentioned: 1, total: 1, contribution: 0.2 },
          { category: "alternatives", mentioned: 0, total: 1, contribution: 0 },
          {
            category: "recommendation",
            mentioned: 2,
            total: 2,
            contribution: 0.4,
          },
          { category: "use-case", mentioned: 1, total: 1, contribution: 0.2 },
        ]}
      />,
    );

    expect(screen.getByText("63%")).toBeInTheDocument();
    expect(
      screen.getByText("Brand appeared in 5 of 8 scored answers"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Recommendation visibility: 3 of 3 answers",
      }),
    ).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("links simple overview charts to their detail pages", () => {
    const insights: Insights = {
      brand: "Yanki Demo Co",
      subject: "warehouse automation",
      promptSet: "mvp",
      scoredAnswers: 8,
      probe: null,
      engines,
      gap: {
        answersLost: 2,
        total: 8,
        categories: [],
      },
      entityCoverage: {
        present: 2,
        total: 4,
        entities: [],
      },
      entityLandscape: {
        coreThreshold: 4,
        entities: [],
      },
      drivers: [],
    };

    render(
      <OverviewInsightCards insights={insights} analysisId="analysis-123" />,
    );

    expect(
      screen.getByRole("img", { name: "Visibility gap: 2 of 8 answers" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Entity coverage: 2 of 4 profile terms",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View answer gap details →" }),
    ).toHaveAttribute("href", "/ai-visibility/drivers?analysis=analysis-123");
    expect(
      screen.getByRole("link", { name: "View entity details →" }),
    ).toHaveAttribute("href", "/ai-visibility/entities?analysis=analysis-123");
  });
});
