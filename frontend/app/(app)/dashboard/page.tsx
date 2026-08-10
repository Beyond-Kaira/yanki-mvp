'use client'

import AppShell from '@/components/shell/AppShell'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'

/**
 * The signed-in home. This is what used to live at `/` — moved behind auth so
 * the front door can be a landing page instead of a bare URL box.
 */
export default function DashboardPage() {
  return (
    <AppShell>
      <StartAnalysisPanel
        title="See how AI answers talk about your brand"
        description="Enter your company URL. We ask the AI engines what they say about you and measure how often you show up — with every raw answer one click away."
      />
    </AppShell>
  )
}
