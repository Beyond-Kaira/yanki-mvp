import type { Metadata } from 'next'
import SiteAuditDashboard from '@/components/site-audit/dashboard/SiteAuditDashboard'

export const metadata: Metadata = {
  title: 'Site Audit — Yanki',
  description: 'View your Site Audit projects and their latest crawl status.',
}

export default function SiteAuditPage() {
  return <SiteAuditDashboard />
}
