'use client'

import AppShell from '@/components/shell/AppShell'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'

export default function HomePage() {
  return (
    <AppShell>
      <StartAnalysisPanel
        title="See how AI answers talk about your brand"
        description="Enter your company URL. We ask the AI engines what they say about you and measure how often you show up — with every raw answer one click away."
      />
    </AppShell>
  )
}
