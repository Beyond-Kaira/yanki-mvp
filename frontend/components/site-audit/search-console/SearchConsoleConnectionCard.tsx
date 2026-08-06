'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import Button from '@/components/Button'
import SearchConsolePerformanceSummary from '@/components/site-audit/search-console/SearchConsolePerformanceSummary'
import SearchConsolePropertyPickerDialog from '@/components/site-audit/search-console/SearchConsolePropertyPickerDialog'
import { useSearchConsoleConnection } from '@/components/site-audit/hooks/useSearchConsoleConnection'
import { startSearchConsoleConnect, unlinkSearchConsoleProperty } from '@/lib/api'
import type { SearchConsoleConnection } from '@/lib/contracts'
import { redirectToExternal } from '@/lib/navigation'

/**
 * The Search Console connection, on the Site Audit project page.
 *
 * Three things here are decisions rather than layout.
 *
 * **The callback message is looked up, never printed.** Google sends the browser
 * back to `?gsc=error&reason=…`, and `reason` arrives in a URL a user can edit.
 * It is used only as a key into `CALLBACK_MESSAGES`; an unrecognised value falls
 * back to a generic sentence, so nothing from the address bar is ever rendered.
 *
 * **The query is read from `location`, not `useSearchParams`.** `page.tsx` is a
 * server component that exports `metadata`, so the hook cannot go there, and
 * calling it here would force a Suspense boundary on the whole route to keep
 * prerendering — the same trade `RequireAuth` documents when it reads
 * `window.location` directly. It is read once on mount and cleared with
 * `router.replace`, so a refresh does not re-announce a connection.
 *
 * **Disconnect confirms inline rather than in a modal.** It removes one link on
 * one project; a second focus-trapping overlay for a two-button question is
 * heavier than the question. The confirmation states plainly that the Google
 * account stays connected, because "disconnect" is exactly the word a user will
 * read as "sign out of Google everywhere".
 */

const CALLBACK_MESSAGES: Record<string, { tone: 'success' | 'error'; message: string }> = {
  connected: {
    tone: 'success',
    message: 'Google account connected. Choose a Search Console property to finish.',
  },
  access_denied: {
    tone: 'error',
    message: 'You cancelled the Google sign-in, so nothing was connected.',
  },
  invalid_state: {
    tone: 'error',
    message: 'That connection link is no longer valid. Start the connection again.',
  },
  expired_state: {
    tone: 'error',
    message: 'The connection attempt timed out. Start the connection again.',
  },
  provider_error: {
    tone: 'error',
    message: 'Google could not complete the connection. Try again shortly.',
  },
  invalid_identity: {
    tone: 'error',
    message: 'Google could not verify that account. Try connecting again.',
  },
  missing_refresh_token: {
    tone: 'error',
    message: 'Google did not grant lasting access. Connect again and approve all steps.',
  },
}

const GENERIC_CALLBACK_ERROR = {
  tone: 'error' as const,
  message: 'The Google connection did not complete. Try again.',
}

type Notice = { tone: 'success' | 'error'; message: string }

export default function SearchConsoleConnectionCard({
  projectId,
  enabled,
}: {
  projectId: string
  enabled: boolean
}) {
  const router = useRouter()
  const pathname = usePathname()
  const { state, performance, reload } = useSearchConsoleConnection(projectId, enabled)

  const [notice, setNotice] = useState<Notice | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pickerConnectionId, setPickerConnectionId] = useState<string | null>(null)
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const outcome = params.get('gsc')
    if (!outcome) return

    if (outcome === 'connected') {
      setNotice(CALLBACK_MESSAGES.connected)
    } else {
      const reason = params.get('reason') ?? ''
      setNotice(CALLBACK_MESSAGES[reason] ?? GENERIC_CALLBACK_ERROR)
    }

    // Cleared so a refresh does not replay the message.
    router.replace(pathname)
  }, [pathname, router])

  async function connect() {
    setConnecting(true)
    setActionError(null)
    try {
      const { authorization_url } = await startSearchConsoleConnect(projectId)
      redirectToExternal(authorization_url)
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : 'The Google connection could not be started.',
      )
      setConnecting(false)
    }
  }

  async function disconnect() {
    setDisconnecting(true)
    setActionError(null)
    try {
      await unlinkSearchConsoleProperty(projectId)
      setConfirmingDisconnect(false)
      setNotice({
        tone: 'success',
        message: 'Property disconnected. The Google account is still connected.',
      })
      reload()
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : 'The property could not be disconnected.',
      )
    } finally {
      setDisconnecting(false)
    }
  }

  // Switched off at the backend. The kill switch answers 404 precisely so the
  // feature reads as absent; a card explaining its own absence would defeat it.
  if (state.kind === 'unavailable') return null

  return (
    <section
      aria-labelledby="gsc-card-title"
      className="mt-6 rounded-xl border border-surface-border bg-surface p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2
            id="gsc-card-title"
            className="text-lg font-semibold text-surface-foreground"
          >
            Google Search Console
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            Connect a property to see clicks, impressions and average position for this
            site.
          </p>
        </div>
        <StatusBadge state={state} />
      </div>

      {notice ? (
        <p
          role={notice.tone === 'error' ? 'alert' : 'status'}
          className={`mt-4 rounded-lg p-3 text-sm ${
            notice.tone === 'error'
              ? 'bg-danger-soft text-danger-strong'
              : 'bg-surface-muted text-surface-foreground'
          }`}
        >
          {notice.message}
        </p>
      ) : null}

      {actionError ? (
        <p role="alert" className="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger-strong">
          {actionError}
        </p>
      ) : null}

      {state.kind === 'loading' ? (
        <p role="status" className="mt-4 text-sm text-surface-subtle">
          Loading Google connections…
        </p>
      ) : null}

      {state.kind === 'error' ? (
        <div className="mt-4">
          <p role="alert" className="rounded-lg bg-danger-soft p-3 text-sm text-danger-strong">
            {state.message}
          </p>
          <Button className="mt-3" variant="secondary" onClick={reload}>
            Try again
          </Button>
        </div>
      ) : null}

      {state.kind === 'loaded' ? (
        <LoadedBody
          connections={state.connections.connections}
          projectStatus={state.connections.project_status}
          connecting={connecting}
          onConnect={connect}
          onChoose={setPickerConnectionId}
          confirmingDisconnect={confirmingDisconnect}
          disconnecting={disconnecting}
          onStartDisconnect={() => {
            setActionError(null)
            setConfirmingDisconnect(true)
          }}
          onCancelDisconnect={() => setConfirmingDisconnect(false)}
          onConfirmDisconnect={disconnect}
          performance={performance}
        />
      ) : null}

      {pickerConnectionId ? (
        <SearchConsolePropertyPickerDialog
          projectId={projectId}
          connectionId={pickerConnectionId}
          accountEmail={
            state.kind === 'loaded'
              ? (state.connections.connections.find((c) => c.id === pickerConnectionId)
                  ?.google_account_email ?? '')
              : ''
          }
          onClose={() => setPickerConnectionId(null)}
          onLinked={(siteUrl) => {
            setPickerConnectionId(null)
            setNotice({ tone: 'success', message: `Connected to ${siteUrl}.` })
            reload()
          }}
        />
      ) : null}
    </section>
  )
}

function StatusBadge({
  state,
}: {
  state: ReturnType<typeof useSearchConsoleConnection>['state']
}) {
  if (state.kind !== 'loaded') return null

  const tone: Record<string, string> = {
    no_connection: 'bg-surface-muted text-surface-subtle',
    no_property_selected: 'bg-warning-soft text-warning-strong',
    connected: 'bg-success-soft text-success-strong',
    reauth_required: 'bg-danger-soft text-danger-strong',
  }
  const label: Record<string, string> = {
    no_connection: 'Not connected',
    no_property_selected: 'No property selected',
    connected: 'Connected',
    reauth_required: 'Reconnect needed',
  }
  const status = state.connections.project_status

  return (
    <span
      className={`inline-flex w-fit rounded-full px-2.5 py-1 text-xs font-medium ${tone[status]}`}
    >
      {label[status]}
    </span>
  )
}

function LoadedBody({
  connections,
  projectStatus,
  connecting,
  onConnect,
  onChoose,
  confirmingDisconnect,
  disconnecting,
  onStartDisconnect,
  onCancelDisconnect,
  onConfirmDisconnect,
  performance,
}: {
  connections: SearchConsoleConnection[]
  projectStatus: string
  connecting: boolean
  onConnect: () => void
  onChoose: (connectionId: string) => void
  confirmingDisconnect: boolean
  disconnecting: boolean
  onStartDisconnect: () => void
  onCancelDisconnect: () => void
  onConfirmDisconnect: () => void
  performance: ReturnType<typeof useSearchConsoleConnection>['performance']
}) {
  if (connections.length === 0) {
    return (
      <div className="mt-4">
        <Button onClick={onConnect} loading={connecting}>
          {connecting ? 'Opening Google' : 'Connect Google Search Console'}
        </Button>
      </div>
    )
  }

  const selected = connections.find((connection) => connection.selected_for_project)

  return (
    <div className="mt-4">
      <ul className="space-y-2">
        {connections.map((connection) => (
          <li
            key={connection.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-white p-3"
          >
            <div className="min-w-0">
              <p className="break-all text-sm font-medium text-surface-foreground">
                {connection.google_account_email}
              </p>
              {connection.selected_for_project && connection.selected_site_url ? (
                <p className="mt-0.5 break-all text-xs text-surface-subtle">
                  {connection.selected_site_url}
                </p>
              ) : null}
              {connection.status === 'reauth_required' ? (
                <p className="mt-0.5 text-xs font-medium text-danger-strong">
                  Needs reconnecting
                </p>
              ) : null}
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onChoose(connection.id)}
            >
              {connection.selected_for_project ? 'Change property' : 'Choose property'}
            </Button>
          </li>
        ))}
      </ul>

      <div className="mt-3 flex flex-wrap gap-3">
        <Button variant="ghost" size="sm" onClick={onConnect} loading={connecting}>
          {connecting ? 'Opening Google' : 'Add another Google account'}
        </Button>
        {projectStatus === 'reauth_required' ? (
          <Button variant="secondary" size="sm" onClick={onConnect} loading={connecting}>
            Reconnect this account
          </Button>
        ) : null}
        {selected && !confirmingDisconnect ? (
          <Button variant="ghost" size="sm" onClick={onStartDisconnect}>
            Disconnect property
          </Button>
        ) : null}
      </div>

      {confirmingDisconnect ? (
        <div
          role="group"
          aria-label="Confirm disconnecting the property"
          className="mt-3 rounded-lg border border-surface-border bg-surface-muted p-4"
        >
          <p className="text-sm text-surface-foreground">
            Stop reporting Search Console data for this project? The Google account stays
            connected and other projects are not affected.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={onConfirmDisconnect}
              loading={disconnecting}
            >
              {disconnecting ? 'Disconnecting' : 'Disconnect property'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onCancelDisconnect}
              disabled={disconnecting}
            >
              Keep it connected
            </Button>
          </div>
        </div>
      ) : null}

      {projectStatus === 'no_property_selected' ? (
        <p className="mt-3 text-sm text-surface-subtle">
          Choose a Search Console property to start seeing performance for this project.
        </p>
      ) : null}

      <SearchConsolePerformanceSummary state={performance} />
    </div>
  )
}
