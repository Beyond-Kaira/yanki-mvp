import type { ReactNode } from 'react'

/**
 * The content column inside the product shell.
 *
 * One width for every screen a reader moves between, because they do move
 * between them mid-run: the analysis flow had drifted to `max-w-3xl` while a
 * run was in progress, `max-w-5xl` on the sibling tabs and `max-w-6xl` once
 * results landed, so the page slid sideways on every tab switch and again the
 * moment the run finished. `6xl` is the widest of those and the one the
 * finished dashboards already use, so nothing has to reflow to show results.
 *
 * `className` is for what a screen legitimately varies — vertical rhythm,
 * mostly. Passing a `max-w-*` through it defeats the point; change the width
 * here instead, for everyone.
 */
export default function PageContainer({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`mx-auto max-w-6xl px-6 py-8 sm:px-8 ${className}`.trimEnd()}>
      {children}
    </div>
  )
}
