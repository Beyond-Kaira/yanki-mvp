'use client'

import { useState } from 'react'
import Button from '@/components/Button'

function validateDomain(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return 'Enter a domain to audit.'
  if (trimmed.length > 2048) return 'Use a domain shorter than 2,048 characters.'

  try {
    const parsed = new URL(trimmed.includes('://') ? trimmed : `https://${trimmed}`)
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) {
      return 'Enter a valid HTTP or HTTPS domain.'
    }
  } catch {
    return 'Enter a valid domain, such as example.com.'
  }

  return null
}

export default function SiteAuditProjectStart({
  onContinue,
  compact = false,
}: {
  onContinue: (domain: string) => void
  compact?: boolean
}) {
  const [domain, setDomain] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const validationError = validateDomain(domain)
    if (validationError) {
      setError(validationError)
      document.getElementById('site-audit-domain')?.focus()
      return
    }

    setError(null)
    onContinue(domain.trim())
  }

  return (
    <div className={compact ? 'space-y-6' : 'space-y-8'}>
      <section
        aria-labelledby="site-audit-start-heading"
        className={`rounded-xl border border-surface-border bg-surface shadow-sm ${
          compact ? 'p-6 sm:p-8' : 'px-6 py-7 sm:px-8 sm:py-8'
        }`}
      >
        <p className="font-mono text-xs font-medium uppercase tracking-[0.18em] text-primary-strong">
          New SEO project
        </p>
        <h2
          id="site-audit-start-heading"
          className={`mt-2 font-semibold tracking-tight text-surface-foreground ${
            compact ? 'text-2xl' : 'max-w-3xl text-3xl'
          }`}
        >
          Find the technical issues holding your website back
        </h2>
        <p
          className={`mt-3 text-sm leading-relaxed text-surface-subtle ${
            compact ? 'max-w-2xl' : 'max-w-2xl'
          }`}
        >
          Crawl your site, review source-level SEO findings, and track site health
          without mixing this audit into your GEO score.
        </p>

        <form
          onSubmit={handleSubmit}
          className={`mt-6 gap-3 ${compact ? 'max-w-3xl' : 'max-w-3xl'} sm:flex`}
        >
          <div className="flex-1 text-left">
            <label htmlFor="site-audit-domain" className="sr-only">
              Domain
            </label>
            <input
              id="site-audit-domain"
              type="text"
              inputMode="url"
              autoComplete="url"
              placeholder="example.com"
              value={domain}
              onChange={(event) => {
                setDomain(event.target.value)
                setError(null)
              }}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'site-audit-domain-error' : undefined}
              className={`min-h-[44px] w-full rounded-lg border bg-white px-4 text-base text-surface-foreground placeholder:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 ${
                error
                  ? 'border-danger focus-visible:ring-danger'
                  : 'border-surface-subtle focus-visible:ring-primary'
              }`}
            />
            {error ? (
              <p
                id="site-audit-domain-error"
                role="alert"
                className="mt-2 text-sm text-danger"
              >
                {error}
              </p>
            ) : null}
          </div>
          <Button type="submit" className="mt-3 w-full sm:mt-0 sm:w-auto">
            Configure audit
          </Button>
        </form>
      </section>

      {!compact ? (
        <section
          aria-labelledby="site-audit-how-heading"
          className="pt-1"
        >
          <h2
            id="site-audit-how-heading"
            className="text-xl font-semibold text-surface-foreground"
          >
            From domain to actionable audit
          </h2>
          <ol className="mt-4 grid gap-4 sm:grid-cols-3">
            {[
              ['Enter your domain', 'Add the root domain you want Yanki to crawl.'],
              [
                'Choose crawl settings',
                'Set the page limit, crawler profile, and JavaScript rendering.',
              ],
              [
                'Review real findings',
                'Follow crawl progress and inspect the issues returned by the backend.',
              ],
            ].map(([title, body], index) => (
              <li
                key={title}
                className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft font-mono text-xs font-medium text-primary-strong">
                  {index + 1}
                </span>
                <h3 className="mt-3 font-semibold text-surface-foreground">{title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-surface-subtle">
                  {body}
                </p>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  )
}
