'use client'

import { useState } from 'react'
import { ApiError } from '@/lib/api'
import type { DownloadedFile } from '@/lib/api'

/** Download a file that needs the caller's bearer token.
 *
 * Not an `<a href>`: the access token lives in memory rather than a cookie, so a
 * link navigation would 401 and show the customer a raw error page. Fetching it
 * keeps the failure inside the app, which matters because the most likely
 * failure is a *permission* one — `export:data` is deliberately not implied by
 * read access, so a Viewer clicking this needs a sentence, not a blank tab.
 */
export default function ExportButton({
  label,
  download,
  onError,
}: {
  label: string
  download: () => Promise<DownloadedFile>
  onError?: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const file = await download()
      const url = URL.createObjectURL(file.blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = file.filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      // Released on the next tick rather than immediately: revoking synchronously
      // can cancel the download in some browsers before it has started reading.
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (caught) {
      const message =
        caught instanceof ApiError ? caught.message : 'The export failed.'
      setError(message)
      onError?.(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="inline-flex flex-col">
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="inline-flex min-h-[44px] items-center justify-center rounded-md border border-surface-border px-4 text-sm font-medium text-surface-foreground hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
      >
        {busy ? 'Preparing…' : label}
      </button>
      {error ? (
        <span role="alert" className="mt-1 max-w-xs text-xs text-danger-strong">
          {error}
        </span>
      ) : null}
    </span>
  )
}
