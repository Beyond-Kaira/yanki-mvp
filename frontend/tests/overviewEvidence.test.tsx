import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import OverviewEvidenceCard from "@/components/ai-visibility/OverviewEvidenceCard";
import { emptyAnalysisResult } from "@/lib/analysis-bundle";
import { overviewFromAnalysis } from "@/lib/ai-overview";
import type { Analysis, AnalysisResponse, Prompt } from "@/lib/contracts";

function analysisWith(
  result: Partial<Analysis["result"]>,
): Analysis {
  return {
    id: "run-123",
    url: "https://acme.test",
    result: { ...emptyAnalysisResult(), ...result },
  } as Analysis;
}

function prompt(id: string, text: string): Prompt {
  return {
    id,
    text,
    category: "recommendation",
    source: "generated",
    locked: false,
    editable: true,
  };
}

function response(
  id: string,
  promptId: string,
  model: string,
  footprint: boolean | null,
  rawText = "Recorded answer",
): AnalysisResponse {
  return {
    id,
    prompt_id: promptId,
    model,
    llm_provider: "openrouter",
    footprint,
    raw_text: rawText,
    matched_snippet: null,
    cost_usd: 0,
  };
}

describe("Overview answer evidence", () => {
  it("counts only saved answers and shows recorded model outcomes for a mixed question", () => {
    const model = overviewFromAnalysis(
      analysisWith({
        prompts: [
          prompt("p1", "Which tools do you recommend?"),
          prompt("p2", "Where should a buyer start?"),
        ],
        responses: [
          response("r1", "p1", "openai/gpt-4o-mini", true),
          response("r2", "p1", "anthropic/claude-sonnet-4.5", false),
          response("r3", "p2", "google/gemini-2.5-flash", null),
          response("r4", "p2", "openai/gpt-4o-mini", true, ""),
        ],
      }),
    );

    expect(model.evidence).toMatchObject({
      questionCount: 2,
      answerCount: 3,
      scoredCount: 2,
      mentionedCount: 1,
      example: {
        question: "Which tools do you recommend?",
        outcomes: [
          { label: "GPT-4o mini", mentioned: true },
          { label: "Claude Sonnet 4.5", mentioned: false },
        ],
      },
    });

    render(<OverviewEvidenceCard model={model} />);
    expect(
      screen.getByRole("link", { name: /Explore prompts & answers/ }),
    ).toHaveAttribute(
      "href",
      "/ai-visibility/prompts?analysis=run-123",
    );
    expect(screen.getByText(/appeared in 1 of 2 scored answers/)).toBeInTheDocument();
  });

  it("uses grounded records when a run has no legacy prompt answers", () => {
    const model = overviewFromAnalysis(
      analysisWith({
        geo_records: [
          {
            id: "geo-1",
            response_id: "response-1",
            brand: "Acme",
            prompt: "Who sells Acme products?",
            grounded_answer: "Acme does.",
            mentioned: true,
          },
          {
            id: "geo-2",
            response_id: "response-2",
            brand: "Acme",
            prompt: "What are the alternatives?",
            grounded_answer: "Other brands.",
            mentioned: false,
          },
        ],
      }),
    );

    expect(model.evidence).toMatchObject({
      questionCount: 2,
      answerCount: 2,
      scoredCount: 2,
      mentionedCount: 1,
      example: {
        question: "What are the alternatives?",
        outcomes: [{ label: "Recorded answer", mentioned: false }],
      },
    });
  });
});
