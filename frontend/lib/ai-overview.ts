import type { Analysis } from "@/lib/contracts";
import { citationsFromAnalysis } from "@/lib/ai-visibility-data";
import { modelSlugLabel, responseModelId } from "@/lib/engines";
import type { Insights } from "@/lib/insights";
import { groupByQuestion } from "@/lib/results";

export interface CitationDomainRow {
  domain: string;
  count: number;
}

export interface InterventionRow {
  title: string;
}

export interface AnswerEvidence {
  questionCount: number;
  answerCount: number;
  scoredCount: number;
  mentionedCount: number;
  example: {
    question: string;
    outcomes: { label: string; mentioned: boolean | null }[];
  } | null;
}

export interface AiOverviewModel {
  domain: string;
  geoScore: number | null;
  citeRate: number | null;
  reliability: number | null;
  citations: CitationDomainRow[];
  interventions: InterventionRow[];
  isSample: boolean;
  analysisId: string | null;
  evidence: AnswerEvidence | null;
  insights?: Insights | null;
}

const SAMPLE: AiOverviewModel = {
  domain: "trendyol.com",
  geoScore: 42,
  citeRate: 0.18,
  reliability: 0.77,
  citations: [
    { domain: "f6s.com", count: 23 },
    { domain: "reddit.com", count: 17 },
    { domain: "medium.com", count: 14 },
    { domain: "linkedin.com", count: 12 },
    { domain: "wikipedia.org", count: 9 },
    { domain: "finance.yahoo.com", count: 8 },
  ],
  interventions: [
    { title: "Strengthen brand mentions on high-authority sources" },
    { title: "Create in-depth content for top-cited topics" },
    { title: "Improve entity consistency across owned pages" },
    { title: "Earn citations from comparison roundups" },
    { title: "Build topical authority around category prompts" },
  ],
  isSample: true,
  analysisId: null,
  evidence: null,
  insights: null,
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function collectInterventions(analysis: Analysis): InterventionRow[] {
  const raw = (analysis.result as { interventions?: unknown }).interventions;
  if (!Array.isArray(raw)) return [];
  const rows: InterventionRow[] = [];
  for (const item of raw) {
    const rec = asRecord(item);
    if (!rec) continue;
    const title =
      (typeof rec.title === "string" && rec.title) ||
      (typeof rec.name === "string" && rec.name) ||
      (typeof rec.label === "string" && rec.label) ||
      null;
    if (title) rows.push({ title });
  }
  return rows.slice(0, 6);
}

function normalizeGeoScore(score: number | null | undefined): number | null {
  if (score == null || Number.isNaN(score)) return null;
  // Legacy mention-rate fraction vs composite 0–100.
  if (score >= 0 && score <= 1) return Math.round(score * 100);
  return Math.round(Math.max(0, Math.min(100, score)));
}

function answerEvidence(analysis: Analysis): AnswerEvidence | null {
  const { prompts, responses, geo_records: geoRecords } = analysis.result;
  const savedResponses = responses.filter((response) => response.raw_text.trim());

  if (prompts.length > 0 && savedResponses.length > 0) {
    const groups = groupByQuestion(prompts, savedResponses);
    const exampleGroup =
      groups.find(
        (group) =>
          group.responses.some((response) => response.footprint === true) &&
          group.responses.some((response) => response.footprint === false),
      ) ?? groups.find((group) => group.responses.length > 0) ?? null;
    const outcomes = new Map<string, boolean | null>();
    for (const response of exampleGroup?.responses ?? []) {
      const modelId = responseModelId(response);
      if (!outcomes.has(modelId)) outcomes.set(modelId, response.footprint);
    }
    return {
      questionCount: prompts.length,
      answerCount: savedResponses.length,
      scoredCount: savedResponses.filter((response) => response.footprint != null).length,
      mentionedCount: savedResponses.filter((response) => response.footprint === true).length,
      example: exampleGroup
        ? {
            question: exampleGroup.prompt.text,
            outcomes: [...outcomes].slice(0, 3).map(([id, mentioned]) => ({
              label: modelSlugLabel(id),
              mentioned,
            })),
          }
        : null,
    };
  }

  const savedGeoRecords = (geoRecords ?? []).filter(
    (record) =>
      record.grounded_answer?.trim() ||
      record.simulated_answer?.trim() ||
      record.answer_summary?.trim(),
  );
  if (geoRecords?.length && savedGeoRecords.length > 0) {
    const questionCount = new Set(
      geoRecords.map((record) => record.prompt.trim()).filter(Boolean),
    ).size;
    const example =
      savedGeoRecords.find((record) => record.mentioned === false) ??
      savedGeoRecords[0];
    return {
      questionCount,
      answerCount: savedGeoRecords.length,
      scoredCount: savedGeoRecords.filter((record) => record.mentioned != null).length,
      mentionedCount: savedGeoRecords.filter((record) => record.mentioned === true).length,
      example: {
        question: example.prompt,
        outcomes: [{ label: "Recorded answer", mentioned: example.mentioned ?? null }],
      },
    };
  }

  if (prompts.length > 0 || geoRecords?.length) {
    return {
      questionCount:
        prompts.length ||
        new Set(geoRecords.map((record) => record.prompt.trim()).filter(Boolean))
          .size,
      answerCount: 0,
      scoredCount: 0,
      mentionedCount: 0,
      example: null,
    };
  }
  return null;
}

export function sampleOverview(): AiOverviewModel {
  return SAMPLE;
}

export function overviewFromAnalysis(analysis: Analysis): AiOverviewModel {
  const result = analysis.result;
  const citationsPage = citationsFromAnalysis(analysis);
  const total = result.total_responses ?? result.responses.length;
  const hits =
    result.footprint_count ??
    result.responses.filter((response) => response.footprint).length;
  // Prefer measured citation_summary cite_rate when present.
  const citeRate =
    citationsPage.summary.citeRate ?? (total > 0 ? hits / total : null);
  const reliability = (result as { reliability_score?: number | null })
    .reliability_score;

  return {
    domain: citationsPage.domain,
    geoScore: normalizeGeoScore(result.geo_score),
    citeRate,
    reliability: typeof reliability === "number" ? reliability : null,
    citations: citationsPage.domains.slice(0, 8).map(({ domain, count }) => ({
      domain,
      count,
    })),
    interventions: collectInterventions(analysis),
    isSample: false,
    analysisId: analysis.id,
    evidence: answerEvidence(analysis),
    insights: result.insights ?? null,
  };
}
