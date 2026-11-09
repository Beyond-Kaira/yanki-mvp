'use client'

import { FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  createAiVisibilityRun,
  createKycProfile,
  getBackgroundJob,
} from '@/lib/moduleRunsApi'

/** Module-first flow (mod-9): profile → GEO run → poll background job. */
export default function ModuleWizardPage() {
  const router = useRouter()
  const [sourceUrl, setSourceUrl] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setStatus('Creating brand profile…')
    try {
      const profile = await createKycProfile({ source_url: sourceUrl.trim() })
      setStatus('Starting AI visibility run…')
      const run = await createAiVisibilityRun({
        brand_context_id: profile.id,
        mode: 'simulated',
        prompts: [{ text: `What is ${profile.brand}?`, category: 'brand' }],
      })
      setStatus('Waiting for worker…')
      for (let i = 0; i < 60; i++) {
        const job = await getBackgroundJob(run.id)
        if (job.status === 'done' && job.linked_analysis_id) {
          router.push(`/ai-visibility?analysis=${job.linked_analysis_id}`)
          return
        }
        if (job.status === 'failed') {
          setStatus(job.error ?? 'Run failed')
          return
        }
        await new Promise((r) => setTimeout(r, 2000))
      }
      setStatus('Timed out — check background job in admin tools.')
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main style={{ maxWidth: 480, margin: '2rem auto', padding: '0 1rem' }}>
      <h1>Module wizard</h1>
      <p>Create a KYC profile and a standalone GEO run (two API calls, one form).</p>
      <form onSubmit={onSubmit}>
        <label>
          Site URL
          <input
            type="url"
            required
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://example.com"
            style={{ display: 'block', width: '100%', marginTop: 8 }}
          />
        </label>
        <button type="submit" disabled={busy} style={{ marginTop: 16 }}>
          {busy ? 'Running…' : 'Start'}
        </button>
      </form>
      {status ? <p style={{ marginTop: 16 }}>{status}</p> : null}
    </main>
  )
}
