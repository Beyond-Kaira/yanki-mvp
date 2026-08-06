import { engineLabel } from '@/lib/engines'
import type { EngineInsight } from '@/lib/insights'
import RatioBar from '@/components/charts/RatioBar'
import IntentHeatmap from '@/components/charts/IntentHeatmap'

interface MultiLlmComparisonProps {
  engines: EngineInsight[]
}

// The core engine-vs-engine read: overall visibility and question-type
// coverage, once per panel engine. Mention share and naming order are
// separate components on the same page (MentionShare / NamingOrder) — they
// answer "who else showed up," a different question from "did this engine
// name you." Every figure here is a count of ANSWERS out of the engine's
// scored total (design §1.2 and §3.1).
export default function MultiLlmComparison({ engines }: MultiLlmComparisonProps) {
  // Each engine answers the whole question set once, so an engine's `total`
  // IS the question count — never the pooled answer count. It is read from the
  // run rather than hard-coded because the set is not a fixed size: the checker
  // asks 12, an MVP crawl asks `prompt_count` (10 by default, configurable).
  // Engines disagree when one of them failed part of a run, and naming a single
  // number would then be wrong for at least one row, so the copy drops the
  // number instead of picking a winner.
  const totals = new Set(engines.map((engine) => engine.total))
  const questionCount = totals.size === 1 ? [...totals][0] : null

  return (
    <section className="space-y-5 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="mlc-heading">
      <div>
        <h2 id="mlc-heading" className="text-lg font-semibold text-surface-foreground">
          Multi-LLM comparison
        </h2>
        <p className="text-sm text-surface-subtle">
          {questionCount === null
            ? 'The same question set, answered separately by each engine on the panel.'
            : `The same ${questionCount} questions, answered separately by each engine on the panel.`}
        </p>
      </div>

      <div className="space-y-2">
        {engines.map((engine) => (
          <RatioBar
            key={engine.engine}
            label={engineLabel(engine.engine)}
            mentioned={engine.mentioned}
            total={engine.total}
          />
        ))}
      </div>

      <div>
        <p className="mb-2 text-xs font-medium uppercase text-surface-subtle">
          Visibility by question type
        </p>
        <IntentHeatmap engines={engines} />
      </div>
    </section>
  )
}
