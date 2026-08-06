"use client";

import AnalysisBoundSubpage from "@/components/ai-visibility/AnalysisBoundSubpage";
import EntityCoverage from "@/components/insights/EntityCoverage";
import EntityLandscape from "@/components/insights/EntityLandscape";

export default function EntitiesClient() {
  return (
    <AnalysisBoundSubpage title="Entities">
      {(analysis) => {
        const insights = analysis.result.insights;

        if (!insights) {
          return (
            <p className="rounded-xl border border-dashed border-surface-border px-4 py-10 text-center text-sm text-surface-subtle">
              This run does not have enough scored answers to calculate entity
              coverage yet.
            </p>
          );
        }

        return (
          <>
            <p className="text-sm text-surface-subtle">
              Entity coverage and the industry landscape calculated from the
              same scored answers as Overview.
            </p>
            <EntityCoverage
              coverage={insights.entityCoverage}
              brand={insights.brand}
              scoredAnswers={insights.scoredAnswers}
            />
            <EntityLandscape
              landscape={insights.entityLandscape}
              scoredAnswers={insights.scoredAnswers}
            />
          </>
        );
      }}
    </AnalysisBoundSubpage>
  );
}
