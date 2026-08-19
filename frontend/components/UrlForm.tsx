'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Button from '@/components/Button'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import { createAnalysis } from '@/lib/api'
import { analysisSubmitLandingHref } from '@/lib/analysis-route'
import { notifyAnalysisQuotaChanged } from '@/lib/analysis-quota-events'
import type { RunMode } from '@/lib/contracts'

function looksLikeUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim())
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

const ERROR_ID = 'url-error'

export default function UrlForm() {
  const router = useRouter()
  const pathname = usePathname()
  const { setAnalysisId } = useAnalysisSession()
  const [url, setUrl] = useState('')
  const [mode, setMode] = useState<RunMode>('quick')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const trimmed = url.trim()
    if (!trimmed) {
      setError('Enter a URL to analyze.')
      return
    }
    if (!looksLikeUrl(trimmed)) {
      setError('Enter a valid URL that starts with http:// or https://.')
      return
    }

    setSubmitting(true)
    try {
      const { id } = await createAnalysis(trimmed, { mode })
      notifyAnalysisQuotaChanged()
      setAnalysisId(id)
      router.push(analysisSubmitLandingHref(id, { mode, pathname }))
    } catch (err) {
      setSubmitting(false)
      setError(
        err instanceof Error
          ? err.message
          : "We couldn't start the analysis. Try again.",
      )
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="w-full space-y-4">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-surface-foreground">
          Run mode
        </legend>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex cursor-pointer gap-3 rounded-xl border border-surface-border bg-surface-muted/40 p-3 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/40">
            <input
              type="radio"
              name="run-mode"
              value="quick"
              checked={mode === 'quick'}
              onChange={() => setMode('quick')}
              disabled={submitting}
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium">Quick</span>
              <span className="block text-xs text-surface-subtle">
                Run all six steps automatically.
              </span>
            </span>
          </label>
          <label className="flex cursor-pointer gap-3 rounded-xl border border-surface-border bg-surface-muted/40 p-3 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/40">
            <input
              type="radio"
              name="run-mode"
              value="guided"
              checked={mode === 'guided'}
              onChange={() => setMode('guided')}
              disabled={submitting}
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium">Guided</span>
              <span className="block text-xs text-surface-subtle">
                Review profile and prompts before measuring.
              </span>
            </span>
          </label>
        </div>
      </fieldset>
      <label htmlFor="url" className="sr-only">
        Company website URL
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="url"
          name="url"
          type="url"
          inputMode="url"
          autoComplete="url"
          placeholder="https://your-company.com"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={submitting}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? ERROR_ID : undefined}
          className="w-full rounded-lg border border-surface-subtle bg-white px-4 py-3 text-base text-surface-foreground placeholder:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
        />
        <Button type="submit" loading={submitting} className="shrink-0">
          {mode === 'guided' ? 'Start guided run' : 'Run analysis'}
        </Button>
      </div>
      {error ? (
        <p id={ERROR_ID} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </form>
  )
}
