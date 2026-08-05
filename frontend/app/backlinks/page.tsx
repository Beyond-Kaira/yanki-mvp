import type { Metadata } from 'next'
import BacklinksDashboard from '@/components/backlinks/BacklinksDashboard'

export const metadata: Metadata = {
  title: 'Backlinks — Yanki',
  description: 'Choose a project to review its backlink profile.',
}

export default function BacklinksPage() {
  return <BacklinksDashboard />
}
