'use client'

import { useEffect, useRef, useState } from 'react'
import Button from '@/components/Button'
import type { CreateSeoProjectInput } from '@/lib/contracts'

export type SiteAuditSettings = Pick<
  CreateSeoProjectInput,
  'page_limit' | 'profile_id' | 'js_rendering'
>

const PROFILE_OPTIONS: Array<{
  id: SiteAuditSettings['profile_id']
  label: string
  description: string
}> = [
  {
    id: 'site_audit_mobile',
    label: 'Mobile crawler',
    description: 'Uses a mobile viewport and touch-enabled browser settings.',
  },
  {
    id: 'site_audit_desktop',
    label: 'Desktop crawler',
    description: 'Uses a desktop viewport for desktop-specific layouts.',
  },
]

export default function SiteAuditSettingsDialog({
  domain,
  submitting,
  submitError,
  onClose,
  onStart,
}: {
  domain: string
  submitting: boolean
  submitError: string | null
  onClose: () => void
  onStart: (settings: SiteAuditSettings) => Promise<void>
}) {
  const [pageLimit, setPageLimit] = useState('10')
  const [profileId, setProfileId] = useState<SiteAuditSettings['profile_id']>(
    'site_audit_mobile',
  )
  const [jsRendering, setJsRendering] = useState(true)
  const [limitError, setLimitError] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.getElementById('site-audit-page-limit')?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !submitting) {
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [href]',
        ),
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
      previouslyFocused?.focus()
    }
  }, [onClose, submitting])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsedLimit = Number(pageLimit)
    if (!Number.isInteger(parsedLimit) || parsedLimit < 1 || parsedLimit > 500) {
      setLimitError('Enter a whole number between 1 and 500.')
      document.getElementById('site-audit-page-limit')?.focus()
      return
    }

    setLimitError(null)
    await onStart({
      page_limit: parsedLimit,
      profile_id: profileId,
      js_rendering: jsRendering,
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/60 p-0 backdrop-blur-[2px] sm:items-center sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="site-audit-settings-title"
        aria-describedby="site-audit-settings-domain"
        className="max-h-[calc(100dvh-1rem)] w-full overflow-y-auto rounded-t-2xl bg-surface shadow-2xl sm:max-h-none sm:max-w-3xl sm:overflow-visible sm:rounded-2xl"
      >
        <form onSubmit={handleSubmit}>
          <header className="flex items-start justify-between gap-4 border-b border-surface-border px-6 py-4 sm:px-7 sm:py-5">
            <div className="min-w-0">
              <p className="font-mono text-xs font-medium uppercase tracking-[0.16em] text-primary-strong">
                Audit settings
              </p>
              <h2
                id="site-audit-settings-title"
                className="mt-1.5 text-2xl font-semibold tracking-tight text-surface-foreground"
              >
                Configure your crawl
              </h2>
              <p
                id="site-audit-settings-domain"
                className="mt-1 truncate text-sm text-surface-subtle"
              >
                {domain}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              aria-label="Close audit settings"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xl text-surface-subtle hover:bg-surface-muted hover:text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
            >
              ×
            </button>
          </header>

          <div className="space-y-5 px-6 py-5 sm:px-7 sm:py-6">
            <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-start sm:gap-5">
              <label
                htmlFor="site-audit-page-limit"
                className="text-sm font-medium text-surface-foreground sm:pt-2.5"
              >
                Limit per audit
              </label>
              <div>
                <div className="flex items-center gap-3">
                  <input
                    id="site-audit-page-limit"
                    type="number"
                    min="1"
                    max="500"
                    step="1"
                    value={pageLimit}
                    onChange={(event) => {
                      setPageLimit(event.target.value)
                      setLimitError(null)
                    }}
                    disabled={submitting}
                    aria-invalid={limitError ? true : undefined}
                    aria-describedby={
                      limitError ? 'site-audit-limit-error' : 'site-audit-limit-hint'
                    }
                    className={`h-11 w-28 rounded-lg border bg-white px-3 text-surface-foreground focus-visible:outline-none focus-visible:ring-2 ${
                      limitError
                        ? 'border-danger focus-visible:ring-danger'
                        : 'border-surface-subtle focus-visible:ring-primary'
                    }`}
                  />
                  <span className="text-sm text-surface-subtle">pages</span>
                </div>
                {limitError ? (
                  <p
                    id="site-audit-limit-error"
                    role="alert"
                    className="mt-2 text-sm text-danger"
                  >
                    {limitError}
                  </p>
                ) : (
                  <p id="site-audit-limit-hint" className="mt-2 text-xs text-surface-subtle">
                    The crawler stops after this many pages. Maximum 500.
                  </p>
                )}
              </div>
            </div>

            <fieldset>
              <legend className="text-sm font-medium text-surface-foreground">
                Crawler profile
              </legend>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                {PROFILE_OPTIONS.map((profile) => (
                  <label
                    key={profile.id}
                    className={`flex min-h-[112px] cursor-pointer gap-3 rounded-xl border p-4 transition-colors ${
                      profileId === profile.id
                        ? 'border-primary bg-primary-soft'
                        : 'border-surface-border bg-white hover:border-surface-subtle'
                    }`}
                  >
                    <input
                      type="radio"
                      name="site-audit-profile"
                      value={profile.id}
                      checked={profileId === profile.id}
                      onChange={() => setProfileId(profile.id)}
                      disabled={submitting}
                      className="mt-1 h-4 w-4 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    />
                    <span>
                      <span className="block text-sm font-semibold text-surface-foreground">
                        {profile.label}
                      </span>
                      <span className="mt-1 block text-xs leading-relaxed text-surface-subtle">
                        {profile.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-2 sm:grid-cols-[160px_1fr] sm:items-center sm:gap-5">
              <div>
                <p className="text-sm font-medium text-surface-foreground">
                  JavaScript rendering
                </p>
                <p id="site-audit-js-hint" className="mt-1 text-xs text-surface-subtle">
                  Discover client-rendered content and links.
                </p>
              </div>
              <label className="inline-flex min-h-[44px] cursor-pointer items-center gap-3 self-start sm:self-center">
                <input
                  type="checkbox"
                  checked={jsRendering}
                  onChange={(event) => setJsRendering(event.target.checked)}
                  disabled={submitting}
                  aria-describedby="site-audit-js-hint"
                  className="peer sr-only"
                />
                <span className="relative h-6 w-11 rounded-full bg-surface-border transition-colors after:absolute after:left-1 after:top-1 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow-sm after:transition-transform peer-checked:bg-primary peer-checked:after:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2" />
                <span className="text-sm font-medium text-surface-foreground">
                  {jsRendering ? 'Enabled' : 'Disabled'}
                </span>
              </label>
            </div>

            {submitError ? (
              <p role="alert" className="rounded-lg bg-danger-soft p-3 text-sm text-danger-strong">
                {submitError}
              </p>
            ) : null}
          </div>

          <footer className="flex justify-end gap-3 border-t border-surface-border px-6 py-4 sm:px-7">
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" loading={submitting}>
              {submitting ? 'Starting audit' : 'Start audit'}
            </Button>
          </footer>
        </form>
      </div>
    </div>
  )
}
