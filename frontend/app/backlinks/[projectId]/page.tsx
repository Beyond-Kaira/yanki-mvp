import type { Metadata } from 'next'
import BacklinkProfileDetail from '@/components/backlinks/detail/BacklinkProfileDetail'

export const metadata: Metadata = {
  title: 'Backlink profile — Yanki',
  description:
    'Review backlinks, referring domains, anchors, link changes and outreach opportunities.',
}

export default function BacklinkProfilePage() {
  return <BacklinkProfileDetail />
}
