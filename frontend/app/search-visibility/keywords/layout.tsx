'use client'

import KeywordsSessionProvider from '@/components/keywords/KeywordsSessionProvider'
import { KeywordsShell } from '@/components/keywords/KeywordsChrome'

export default function KeywordsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <KeywordsSessionProvider>
      <KeywordsShell>{children}</KeywordsShell>
    </KeywordsSessionProvider>
  )
}
