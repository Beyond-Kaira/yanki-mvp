'use client'

import type { ReactNode } from 'react'
import AppShell from '@/components/shell/AppShell'
import Link from 'next/link'

export default function AiSubpage({
  title,
  children,
}: {
  title: string
  children?: ReactNode
}) {
  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-8 sm:px-8">
        <p className="text-sm text-surface-subtle">
          <Link href="/ai-visibility" className="text-primary hover:text-primary-hover">
            AI Visibility
          </Link>
          <span className="mx-1.5">/</span>
          {title}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
        <div className="mt-6 rounded-2xl border border-surface-border bg-surface p-6 shadow-sm">
          {children ?? (
            <p className="text-sm text-surface-subtle">
              This view is wired in the shell. Open a finished analysis from{' '}
              <Link href="/" className="text-primary hover:text-primary-hover">
                Home
              </Link>{' '}
              or pass <code className="font-mono text-xs">?analysis=&lt;id&gt;</code> on
              Overview to load live GEO data.
            </p>
          )}
        </div>
      </div>
    </AppShell>
  )
}
