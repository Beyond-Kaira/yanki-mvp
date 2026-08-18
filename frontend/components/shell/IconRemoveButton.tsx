'use client'

import type { MouseEvent } from 'react'

/** Icon-only remove control — matches the admin members table (✕). */
export default function IconRemoveButton({
  label,
  title,
  disabled = false,
  busy = false,
  onClick,
}: {
  label: string
  title?: string
  disabled?: boolean
  busy?: boolean
  onClick: (event: MouseEvent<HTMLButtonElement>) => void
}) {
  return (
    <button
      type="button"
      disabled={disabled || busy}
      aria-label={label}
      title={busy ? 'Working…' : title ?? label}
      onClick={onClick}
      className="inline-flex h-11 w-11 items-center justify-center rounded-md text-lg font-semibold leading-none text-surface-subtle transition-colors hover:bg-danger-soft hover:text-danger-strong disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-border"
    >
      ✕
    </button>
  )
}
