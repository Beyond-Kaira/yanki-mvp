'use client'

import AdminClient from './AdminClient'
import AppShell from '@/components/shell/AppShell'
import RequireAuth from '@/components/RequireAuth'

export default function AdminPage() {
  return (
    <RequireAuth>
      <AppShell>
        <AdminClient />
      </AppShell>
    </RequireAuth>
  )
}
