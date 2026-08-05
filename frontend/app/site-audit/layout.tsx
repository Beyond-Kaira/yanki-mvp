'use client'

import type { ReactNode } from 'react'
import AppShell from '@/components/shell/AppShell'
import RequireAuth from '@/components/RequireAuth'

/** Site Audit is a signed-in product surface and now renders inside the shell. */
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  )
}
