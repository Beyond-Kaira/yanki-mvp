'use client'

import { useState } from 'react'
import type { AnalysisEnvelope } from '@/lib/contracts'
import RecentAnalysesPanel from '@/components/ai-visibility/RecentAnalysesPanel'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'
import PageContainer from '@/components/shell/PageContainer'

function mockRun(): AnalysisEnvelope {
  const now = Date.now()
  return {
    id: `local-preview-${now}`,
    url: 'https://preview.example/',
    status: 'running',
    progress: 45,
    current_step: 'execute',
    run_mode: 'quick',
    geo_score: null,
    error: null,
    created_at: new Date(now - 134_000).toISOString(),
    updated_at: new Date(now).toISOString(),
  }
}

/** Development-only fixture: uses the real card/history without creating a job. */
export default function ProgressPreview() {
  const [analysis, setAnalysis] = useState(mockRun)
  return (
    <>
      <StartAnalysisPanel
        title="AI Visibility"
        description="Enter a domain to start a measured GEO analysis. Overview and every AI Visibility tab will use this same run."
        disabled
      />
      <PageContainer className="pb-12 pt-0">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/20 bg-primary-soft/40 px-4 py-3 text-sm">
          <p>Yerel mock: preview.example · %45 Executing. Gerçek analiz başlatılmaz.</p>
          <button
            type="button"
            onClick={() => setAnalysis(mockRun())}
            className="min-h-9 rounded-lg border border-surface-border bg-surface px-3 font-medium text-primary-strong hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Mock’u yeniden başlat
          </button>
        </div>
        <RecentAnalysesPanel activeAnalysis={analysis} />
      </PageContainer>
    </>
  )
}
