'use client'

import { useEffect, useRef, useState } from 'react'
import Button from '@/components/Button'
import { linkSearchConsoleProperty, listSearchConsoleProperties } from '@/lib/api'
import type { SearchConsoleProperties, SearchConsoleProperty } from '@/lib/contracts'

/**
 * Choose which Search Console property this project reports on.
 *
 * The dialog machinery — focus trap, Escape, body scroll lock, restoring focus
 * on close, the bottom-sheet-on-mobile layout — is lifted from
 * `SiteAuditSettingsDialog`, which is the repo's one worked example. Copied
 * rather than extracted: two dialogs is not yet a pattern, and factoring one out
 * of two would guess at the shape the third needs.
 *
 * **Nothing is preselected.** The backend flags the property whose host matches
 * the project and sorts it first, and this renders that as a "Recommended"
 * badge. Auto-selecting it would make a silent choice about which numbers a
 * customer is about to read — and the flag is a host match, not a promise.
 */
export default function SearchConsolePropertyPickerDialog({
  projectId,
  connectionId,
  accountEmail,
  onClose,
  onLinked,
}: {
  projectId: string
  connectionId: string
  accountEmail: string
  onClose: () => void
  onLinked: (siteUrl: string) => void
}) {
  const [data, setData] = useState<SearchConsoleProperties | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    async function load() {
      try {
        const result = await listSearchConsoleProperties(
          projectId,
          connectionId,
          controller.signal,
        )
        if (cancelled) return
        setData(result)
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) return
        setLoadError(
          error instanceof Error
            ? error.message
            : 'Search Console properties could not be loaded.',
        )
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [connectionId, projectId])

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

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
    if (!selected) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      await linkSearchConsoleProperty(projectId, {
        google_connection_id: connectionId,
        site_url: selected,
      })
      onLinked(selected)
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : 'That property could not be connected.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  const properties = data?.properties ?? []

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
        aria-labelledby="gsc-property-title"
        aria-describedby="gsc-property-account"
        className="max-h-[calc(100dvh-1rem)] w-full overflow-y-auto rounded-t-2xl bg-surface shadow-2xl sm:max-h-[80vh] sm:max-w-2xl sm:rounded-2xl"
      >
        <form onSubmit={handleSubmit}>
          <header className="flex items-start justify-between gap-4 border-b border-surface-border px-6 py-4 sm:px-7 sm:py-5">
            <div className="min-w-0">
              <p className="font-mono text-xs font-medium uppercase tracking-[0.16em] text-primary-strong">
                Search Console
              </p>
              <h2
                id="gsc-property-title"
                className="mt-1.5 text-2xl font-semibold tracking-tight text-surface-foreground"
              >
                Choose a property
              </h2>
              <p
                id="gsc-property-account"
                className="mt-1 break-all text-sm text-surface-subtle"
              >
                {accountEmail}
              </p>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              disabled={submitting}
              aria-label="Close property picker"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xl text-surface-subtle hover:bg-surface-muted hover:text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
            >
              ×
            </button>
          </header>

          <div className="px-6 py-5 sm:px-7 sm:py-6">
            {loadError ? (
              <p
                role="alert"
                className="rounded-lg bg-danger-soft p-3 text-sm text-danger-strong"
              >
                {loadError}
              </p>
            ) : !data ? (
              <p role="status" className="text-sm text-surface-subtle">
                Loading properties…
              </p>
            ) : properties.length === 0 ? (
              <div>
                <h3 className="text-sm font-semibold text-surface-foreground">
                  No properties available
                </h3>
                <p className="mt-2 text-sm text-surface-subtle">
                  This Google account has no verified Search Console properties. Verify
                  the site in Search Console, or connect a different Google account.
                </p>
              </div>
            ) : (
              <fieldset disabled={submitting}>
                <legend className="sr-only">Search Console properties</legend>
                <ul className="space-y-2">
                  {properties.map((property) => (
                    <li key={property.site_url}>
                      <PropertyOption
                        property={property}
                        checked={selected === property.site_url}
                        onSelect={() => setSelected(property.site_url)}
                      />
                    </li>
                  ))}
                </ul>
              </fieldset>
            )}

            {submitError ? (
              <p
                role="alert"
                className="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger-strong"
              >
                {submitError}
              </p>
            ) : null}
          </div>

          <footer className="flex justify-end gap-3 border-t border-surface-border px-6 py-4 sm:px-7">
            <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" loading={submitting} disabled={!selected}>
              {submitting ? 'Connecting' : 'Connect property'}
            </Button>
          </footer>
        </form>
      </div>
    </div>
  )
}

function PropertyOption({
  property,
  checked,
  onSelect,
}: {
  property: SearchConsoleProperty
  checked: boolean
  onSelect: () => void
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors ${
        checked
          ? 'border-primary bg-primary-soft'
          : 'border-surface-border bg-white hover:border-surface-subtle'
      }`}
    >
      <input
        type="radio"
        name="gsc-property"
        value={property.site_url}
        checked={checked}
        onChange={onSelect}
        className="mt-1 h-4 w-4 shrink-0 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      />
      <span className="min-w-0">
        <span className="block break-all text-sm font-semibold text-surface-foreground">
          {property.site_url}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-2">
          {/* Every badge carries a word. Colour alone would leave "recommended"
              and "connected" indistinguishable to anyone who cannot see it. */}
          {property.matches_project_domain ? (
            <span className="rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success-strong">
              Recommended
            </span>
          ) : null}
          {property.currently_selected ? (
            <span className="rounded-full bg-primary-soft px-2.5 py-1 text-xs font-medium text-primary-strong">
              Connected
            </span>
          ) : null}
          <span className="rounded-full bg-surface-muted px-2.5 py-1 text-xs font-medium text-surface-subtle">
            {property.property_type === 'domain' ? 'Domain property' : 'URL prefix'}
          </span>
          <span className="text-xs text-surface-subtle">{property.permission_level}</span>
        </span>
      </span>
    </label>
  )
}
