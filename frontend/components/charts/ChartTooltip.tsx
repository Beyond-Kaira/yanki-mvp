'use client'

import { useId, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

interface ChartTooltipProps {
  // The evidence sentence — always the same fact shown visually, spelled out.
  content: string
  children: ReactNode
  // Applied to the OUTER wrapper, not a nested span, so a percentage-width
  // child (a stacked-share segment) resolves against the real flex row
  // instead of against an auto-sized wrapper two levels up.
  style?: CSSProperties
  className?: string
}

// Reachable by hover AND keyboard focus (brandkit v2 §7: nothing here may
// depend on a mouse). Wraps a chart cell/bar; the tooltip text is also always
// present for a screen reader via aria-describedby, whether or not it is
// visible.
export default function ChartTooltip({ content, children, style, className }: ChartTooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()

  return (
    <span
      className={`relative inline-flex ${className ?? ''}`}
      style={style}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={id} tabIndex={0} className="flex w-full outline-none">
        {children}
      </span>
      <span
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute -top-2 left-1/2 z-10 w-max max-w-[16rem] -translate-x-1/2 -translate-y-full rounded-md bg-ink px-2.5 py-1.5 text-xs text-ink-foreground shadow-sm transition-opacity ${
          open ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {content}
      </span>
    </span>
  )
}
