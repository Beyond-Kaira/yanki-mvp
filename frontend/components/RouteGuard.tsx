'use client'

import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'
import RequireAuth from '@/components/RequireAuth'
import { isPublicPath } from '@/lib/route-access'

/**
 * The single gate. Mounted once in the root layout, it decides per route
 * whether `RequireAuth` stands between the visitor and the page, so no page
 * carries a logged-in check of its own.
 */
export default function RouteGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  if (isPublicPath(pathname)) return <>{children}</>
  return <RequireAuth>{children}</RequireAuth>
}
