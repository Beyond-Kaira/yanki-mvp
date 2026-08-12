'use client'

import type { ReactNode } from 'react'
import AppShell from '@/components/shell/AppShell'

/** Backlinks is a signed-in product surface and renders inside the shell. */
export default function Layout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>
}
