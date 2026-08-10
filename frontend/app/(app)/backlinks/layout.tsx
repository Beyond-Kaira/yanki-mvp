'use client'

import type { ReactNode } from 'react'
import AppShell from '@/components/shell/AppShell'

/** Backlinks renders inside the shell; the `(app)` group gates it. */
export default function Layout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>
}
