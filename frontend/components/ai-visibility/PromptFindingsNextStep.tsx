import AnalysisNextStep from "@/components/ai-visibility/AnalysisNextStep";

export default function PromptFindingsNextStep({
  analysisId,
}: {
  analysisId: string;
}) {
  return (
    <AnalysisNextStep
      id="prompt-findings-next-step"
      eyebrow="Explore the findings"
      title="Explore the findings behind these answers"
      description="Review your brand’s visibility across question types, along with the strengths and search & content gaps identified in this run."
      href={`/ai-visibility/drivers?analysis=${encodeURIComponent(analysisId)}`}
      linkLabel="Explore drivers & gaps"
      nextStepLabel="Drivers & Gaps"
    />
  );
}
