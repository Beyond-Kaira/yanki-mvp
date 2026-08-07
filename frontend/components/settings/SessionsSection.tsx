'use client'

import { useCallback, useEffect, useState } from 'react'
import { ApiError, fetchSessions, revokeAllSessions, revokeSession } from '@/lib/api'
import type { AuthSession } from '@/lib/contracts'

/**
 * "Devices & sessions" in `/settings`.
 *
 * Lists the caller's own active sessions, marks the one they are on, lets them
 * revoke another, and signs out everywhere else behind an explicit two-step
 * confirmation — the last is a lock-yourself-out-of-your-other-devices action,
 * so it does not fire on a single click. The current session is not offered a
 * "revoke" button: ending it here would be a surprise sign-out, and "Log out"
 * already does that on purpose.
 */
export default function SessionsSection() {
  const [sessions, setSessions] = useState<AuthSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmingAll, setConfirmingAll] = useState(false)
  const [signingOutAll, setSigningOutAll] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const result = await fetchSessions()
      setSessions(result.sessions)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'We could not load your sessions. Try again.',
      )
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onRevoke(sessionId: string) {
    setBusyId(sessionId)
    setNotice(null)
    try {
      await revokeSession(sessionId)
      await load()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'We could not revoke that session.',
      )
    } finally {
      setBusyId(null)
    }
  }

  async function onSignOutAll() {
    setSigningOutAll(true)
    setNotice(null)
    try {
      const result = await revokeAllSessions()
      setConfirmingAll(false)
      // `kept_current` is false when the server could not identify which family
      // this request came from — so it revoked every one, including ours. The
      // count alone would read as "your other sessions ended", which is the one
      // thing that is not true here: this device is signed out too, and saying
      // so is the difference between a confusing logout and an expected one.
      setNotice(
        result.kept_current === false
          ? 'Signed out of every session, including this device. You will need to sign in again.'
          : result.revoked === 0
            ? 'There were no other sessions to sign out.'
            : `Signed out ${result.revoked} other ${
                result.revoked === 1 ? 'session' : 'sessions'
              }.`,
      )
      await load()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'We could not sign out your other sessions.',
      )
    } finally {
      setSigningOutAll(false)
    }
  }

  const otherCount = (sessions ?? []).filter((session) => !session.current).length

  return (
    <section className="rounded-lg border border-surface-border bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Devices &amp; sessions</h2>
          <p className="mt-1 text-sm text-surface-subtle">
            Where you are signed in. Revoke a session you do not recognise.
          </p>
        </div>
        {otherCount > 0 ? (
          confirmingAll ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-surface-subtle" role="status">
                Sign out {otherCount} other {otherCount === 1 ? 'session' : 'sessions'}?
              </span>
              <button
                type="button"
                onClick={onSignOutAll}
                disabled={signingOutAll}
                className="inline-flex min-h-[36px] items-center rounded-md bg-danger px-3 text-sm font-medium text-white transition-colors hover:bg-danger-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-60"
              >
                {signingOutAll ? 'Signing out…' : 'Confirm'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmingAll(false)}
                disabled={signingOutAll}
                className="inline-flex min-h-[36px] items-center rounded-md px-2 text-sm font-medium text-surface-subtle hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setNotice(null)
                setConfirmingAll(true)
              }}
              className="inline-flex min-h-[36px] items-center rounded-md border border-surface-border px-3 text-sm font-medium transition-colors hover:border-danger hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
            >
              Sign out other sessions
            </button>
          )
        ) : null}
      </div>

      {notice ? (
        <p className="mt-3 text-sm text-success-strong" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      {sessions === null && !error ? (
        <p className="mt-4 text-sm text-surface-subtle" role="status">
          Loading your sessions…
        </p>
      ) : null}

      {sessions !== null ? (
        sessions.length === 0 ? (
          <p className="mt-4 text-sm text-surface-subtle">No active sessions.</p>
        ) : (
          <ul className="mt-4 divide-y divide-surface-border">
            {sessions.map((session) => (
              <li
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-medium">
                    {session.current ? 'This device' : 'Session'}
                    {session.current ? (
                      <span className="rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success-strong">
                        Current
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-0.5 text-xs text-surface-subtle">
                    Started {formatDate(session.created_at)} · Last active{' '}
                    {formatDate(session.last_active_at)} · Expires{' '}
                    {formatDate(session.expires_at)}
                  </p>
                </div>
                {session.current ? null : (
                  <button
                    type="button"
                    onClick={() => onRevoke(session.id)}
                    disabled={busyId === session.id}
                    className="inline-flex min-h-[36px] items-center rounded-md border border-surface-border px-3 text-sm font-medium transition-colors hover:border-danger hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-60"
                  >
                    {busyId === session.id ? 'Revoking…' : 'Revoke'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  )
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'unknown'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
