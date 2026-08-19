'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Button from '@/components/Button'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import { createAnalysis, type AnalysisSource } from '@/lib/api'
import { notifyAnalysisQuotaChanged } from '@/lib/analysis-quota-events'

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

    // Both product areas mount this same form, so the path is the only thing
    // that knows which one the user is standing in — the audit log has no other
    // way to tell two identical "analysis:create" rows apart.
    const source: AnalysisSource | undefined = pathname.startsWith('/search-visibility')
      ? 'search_visibility'
      : pathname.startsWith('/ai-visibility')
        ? 'ai_visibility'
        : undefined

    setSubmitting(true)
    try {
      const { id } = await createAnalysis(trimmed, source)
      notifyAnalysisQuotaChanged()
      // One shared analysis for the whole AI Visibility shell (and later tabs).
      setAnalysisId(id)
      if (source) {
        router.push(`/${source.replace('_', '-')}?analysis=${id}`)
      } else {
        router.push(`/analyses/${id}`)
      }
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
    <form onSubmit={handleSubmit} noValidate className="w-full space-y-2">
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
          Run analysis
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
