// A single labelled n/m bar. The fill never carries the value alone — the
// ratio text sits next to it, so nothing here needs colour to be read.
interface RatioBarProps {
  label: string
  mentioned: number
  total: number
  // Compact wording for tight rows (engine grids); default is "n/m answers".
  compact?: boolean
}

export default function RatioBar({ label, mentioned, total, compact }: RatioBarProps) {
  const pct = total > 0 ? Math.round((mentioned / total) * 100) : 0

  return (
    <div className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_auto] items-center gap-3">
      <span className="truncate text-sm text-surface-subtle">{label}</span>
      <div
        className="h-5 overflow-hidden rounded bg-surface-muted"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: mentioned in ${mentioned} of ${total} answers`}
      >
        <div className="h-full rounded bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <span className="whitespace-nowrap text-xs tabular-nums text-surface-subtle">
        {mentioned}/{total}
        {compact ? '' : ` · ${pct}%`}
      </span>
    </div>
  )
}
