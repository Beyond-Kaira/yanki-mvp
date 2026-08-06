import { Fragment } from 'react'
import { engineLabel } from '@/lib/engines'
import { GROUP_CATEGORIES, INTENT_GROUPS } from '@/lib/insights'
import type { EngineInsight } from '@/lib/insights'
import ChartTooltip from './ChartTooltip'

interface IntentHeatmapProps {
  engines: EngineInsight[]
}

// Four steps between "no answers" and "all answers", tuned so a single-answer
// swing (the whole range a cell can move) never jumps more than one step —
// see design §1.2: a cell here is a handful of answers, not a population.
const FILL_STEPS = ['bg-surface-muted', 'bg-primary-soft', 'bg-primary/40', 'bg-primary/70', 'bg-primary']

function fillClass(mentioned: number, total: number): string {
  if (total === 0) return FILL_STEPS[0]
  const ratio = mentioned / total
  const step = Math.min(FILL_STEPS.length - 1, Math.round(ratio * (FILL_STEPS.length - 1)))
  return FILL_STEPS[step]
}

// Engine x intent-group grid. Every cell renders its n/m as text — the fill is
// a redundant, not the only, signal — and every cell is a tooltip target so
// the same fact is reachable by hover or keyboard focus.
export default function IntentHeatmap({ engines }: IntentHeatmapProps) {
  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-[28rem] gap-1"
        style={{ gridTemplateColumns: `7rem repeat(${INTENT_GROUPS.length}, minmax(0,1fr))` }}
      >
        <div />
        {INTENT_GROUPS.map((group) => (
          <div key={group} className="px-1 text-center text-xs text-surface-subtle">
            {group}
            <br />
            <span className="text-[10px]">({GROUP_CATEGORIES[group].join(', ')})</span>
          </div>
        ))}
        {engines.map((engine) => (
          <Fragment key={engine.engine}>
            <div className="flex items-center text-sm text-surface-subtle">
              {engineLabel(engine.engine)}
            </div>
            {INTENT_GROUPS.map((group) => {
              const stat = engine.groups.find((g) => g.group === group)
              const mentioned = stat?.mentioned ?? 0
              const total = stat?.total ?? 0
              return (
                <ChartTooltip
                  key={`${engine.engine}-${group}`}
                  content={`${engineLabel(engine.engine)} · ${group}: named the brand in ${mentioned} of ${total} answers`}
                >
                  <div
                    className={`flex h-11 w-full items-center justify-center rounded text-xs tabular-nums text-surface-foreground ${fillClass(
                      mentioned,
                      total,
                    )}`}
                  >
                    {mentioned}/{total}
                  </div>
                </ChartTooltip>
              )
            })}
          </Fragment>
        ))}
      </div>
    </div>
  )
}
