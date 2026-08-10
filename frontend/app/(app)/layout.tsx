import type { ReactNode } from 'react'
import RequireAuth from '@/components/RequireAuth'

/**
 * The single gate for the signed-in product surface.
 *
 * Every protected route lives under this group, so adding one is a matter of
 * putting the file here rather than remembering to wrap it. Nothing below this
 * layout carries an auth check of its own. Route groups leave the URL alone —
 * `app/(app)/dashboard/page.tsx` is still `/dashboard`.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>
}
