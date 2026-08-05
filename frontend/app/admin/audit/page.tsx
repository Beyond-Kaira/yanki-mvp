'use client'

import { Suspense } from 'react'
import AuditLogClient from './AuditLogClient'

/**
 * Admin Panel → Audit log.
 *
 * The Suspense boundary is required, not decorative: `useSearchParams` opts its
 * subtree out of static prerendering unless one wraps it, and the record-history
 * view reads `entity_type`/`entity_id` from the query string.
 */
export default function AdminPanelAuditPage() {
  return (
    <Suspense
      fallback={<p className="text-sm text-surface-subtle">Loading the audit log…</p>}
    >
      <AuditLogClient />
    </Suspense>
  )
}
