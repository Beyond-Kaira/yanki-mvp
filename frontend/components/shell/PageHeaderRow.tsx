import type { ReactNode } from 'react'

/** Title block plus an optional action that stacks cleanly on small screens. */
export default function PageHeaderRow({
  children,
  action,
  className = 'mb-8',
}: {
  children: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4 ${className}`.trimEnd()}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {action ? <div className="w-full shrink-0 sm:w-auto">{action}</div> : null}
    </div>
  )
}
