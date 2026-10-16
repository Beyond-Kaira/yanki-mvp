import Link from "next/link";
import type { AiOverviewModel } from "@/lib/ai-overview";
import { IconChevron } from "@/components/shell/icons";

export default function OverviewEvidenceCard({
  model,
}: {
  model: AiOverviewModel;
}) {
  const { evidence } = model;
  const href = model.analysisId
    ? `/ai-visibility/prompts?analysis=${encodeURIComponent(model.analysisId)}`
    : "/ai-visibility/prompts";

  return (
    <section
      aria-labelledby="answer-evidence-heading"
      className="mb-4 flex flex-col gap-4 rounded-2xl border border-primary/20 bg-primary-soft/60 p-5 shadow-sm lg:flex-row lg:items-end lg:justify-between lg:gap-6"
    >
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary-strong">
          Explore the evidence
        </p>
        <h2
          id="answer-evidence-heading"
          className="mt-1 text-lg font-semibold tracking-tight text-surface-foreground sm:text-xl"
        >
          What did AI actually say about {model.domain}?
        </h2>
        {evidence ? (
          <p className="mt-1 text-sm leading-6 text-surface-subtle">
            {evidence.questionCount}{" "}
            {evidence.questionCount === 1 ? "question" : "questions"} ·{" "}
            {evidence.answerCount} recorded{" "}
            {evidence.answerCount === 1 ? "answer" : "answers"}
            {evidence.scoredCount > 0
              ? ` · your brand appeared in ${evidence.mentionedCount} of ${evidence.scoredCount} scored answers`
              : ""}
          </p>
        ) : (
          <p className="mt-1 text-sm leading-6 text-surface-subtle">
            No question or answer records are available for this run.
          </p>
        )}

        {evidence?.example ? (
          <div className="mt-3 border-l-[3px] border-primary pl-3">
            <p className="text-xs text-surface-subtle">
              Example question from this run
            </p>
            <p className="mt-1 text-sm font-medium leading-5 text-surface-foreground">
              {evidence.example.question}
            </p>
            {evidence.example.outcomes.length > 0 ? (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {evidence.example.outcomes.map((outcome) => (
                  <li
                    key={outcome.label}
                    className={`rounded-md bg-surface px-2 py-1 text-xs ${
                      outcome.mentioned === true
                        ? "text-success-strong"
                        : "text-surface-subtle"
                    }`}
                  >
                    {outcome.mentioned === true
                      ? "✓"
                      : outcome.mentioned === false
                        ? "×"
                        : "–"}{" "}
                    {outcome.label} ·{" "}
                    {outcome.mentioned === true
                      ? "mentioned"
                      : outcome.mentioned === false
                        ? "not mentioned"
                        : "not scored"}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>

      <Link
        href={href}
        className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 self-start rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 lg:self-auto"
      >
        Explore prompts &amp; answers
        <IconChevron className="h-4 w-4" />
      </Link>
    </section>
  );
}
