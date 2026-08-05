import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import AdminPanelChrome from './AdminPanelChrome'

/**
 * A **server** component, and only so that `metadata` works.
 *
 * Next exports page metadata from server components only, and the Admin Panel's
 * chrome needs `usePathname` and `useAuth` — so the two cannot be the same file.
 * Splitting them is what makes the browser tab say "Admin Panel · Yanki" instead
 * of inheriting the root layout's marketing title, which is the string a user
 * scans when they have six tabs open.
 *
 * Everything else — the auth gate, the shell, the tabs — lives in the client
 * component this renders.
 */
export const metadata: Metadata = {
  title: 'Admin Panel · Yanki',
  description:
    'Members, roles, invitations and the audit trail for your organization.',
  // Nothing here should ever reach a search index: it is behind an auth gate
  // and it is somebody's member list.
  robots: { index: false, follow: false },
}

export default function AdminPanelLayout({ children }: { children: ReactNode }) {
  return <AdminPanelChrome>{children}</AdminPanelChrome>
}
