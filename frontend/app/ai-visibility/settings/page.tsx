'use client'

import AiSubpage from '@/components/ai-visibility/AiSubpage'
import Link from 'next/link'

export default function SettingsPage() {
  return (
    <AiSubpage title="Settings">
      <p className="text-sm text-surface-subtle">
        Account settings are marked N/A until workspace features land. You can still{' '}
        <Link href="/login" className="text-primary hover:text-primary-hover">
          sign in
        </Link>{' '}
        from the marketing header on public pages.
      </p>
    </AiSubpage>
  )
}
