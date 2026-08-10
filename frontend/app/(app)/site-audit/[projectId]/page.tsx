import type { Metadata } from 'next'
import SiteAuditProjectDetail from '@/components/site-audit/detail/SiteAuditProjectDetail'

export const metadata: Metadata = {
  title: 'Site Audit project — Yanki',
  description: 'Review crawl progress, pages, issues, and schema findings.',
}

export default function SiteAuditProjectPage() {
  return <SiteAuditProjectDetail />
}
