'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  createInvitation,
  fetchInvitations,
  resendInvitation,
  revokeInvitation,
  type InvitationQuery,
} from '@/lib/api'
import type { AdminInvitation, AdminInvitationList } from '@/lib/contracts'

const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner',
  admin: 'Admin',
  billing_admin: 'Billing admin',
  manager: 'Manager',
  editor: 'Editor',
  analyst: 'Analyst',
  viewer: 'Viewer',
  guest: 'Guest (client)',
}

const PAGE_SIZE = 25

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * The effective state of an invitation, which is NOT the same as its stored
 * status: expiry is derived from the clock, so a row can be `pending` in the
 * database and expired in reality. The backend computes `expired` for exactly
 * this reason; this function just picks the label.
 */
function stateOf(invitation: AdminInvitation): { label: string; tone: string } {
  if (invitation.status === 'accepted') {
    return { label: 'Accepted', tone: 'bg-success-soft text-success-strong' }
  }
  if (invitation.status === 'revoked') {
    return { label: 'Revoked', tone: 'bg-surface-muted text-surface-subtle' }
  }
  if (invitation.expired) {
    return { label: 'Expired', tone: 'bg-warning-soft text-warning-strong' }
  }
  return { label: 'Pending', tone: 'bg-primary-soft text-primary-strong' }
}

/**
 * Invitations: invite someone, see who is outstanding, resend or withdraw.
 *
 * Two things drive the design.
 *
 * **The link is shown, not just emailed.** Transactional email is off by
 * default in every environment, and an admin panel that says "invitation sent"
 * when nothing left the process is lying to the person who will then wait for
 * a reply. So the response reports whether the email actually went, and the
 * one-time link is surfaced for copying when it did not — the only place in the
 * app that ever displays an invitation token, shown once and never refetched.
 *
 * **Resending is a token rotation, and the copy says so.** Someone who forwards
 * a link to the wrong address needs to know that pressing resend fixes it,
 * because the alternative — assuming the old link still works — is the reason
 * they would file a support ticket instead.
 */
export default function InvitationsClient() {
  const [list, setList] = useState<AdminInvitationList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const [email, setEmail] = useState('')
  const [role, setRole] = useState('')
  const [inviting, setInviting] = useState(false)
  const [lastLink, setLastLink] = useState<{ email: string; url: string } | null>(null)

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)

  const query = useMemo<InvitationQuery>(
    () => ({
      q: search.trim() || undefined,
      status: statusFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [search, statusFilter, offset],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await fetchInvitations(query)
      setList(page)
      // The role picker is populated from the server's assignable list, so it
      // can never offer a role the API would refuse — including the platform
      // roles a customer must not be able to grant.
      setRole((current) => current || page.assignable_roles.find((r) => r === 'analyst') || page.assignable_roles[0] || '')
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? 'You do not have permission to manage invitations. Ask an owner or admin.'
          : err instanceof Error
            ? err.message
            : 'We could not load your invitations.',
      )
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  async function submitInvite(event: React.FormEvent) {
    event.preventDefault()
    setInviting(true)
    setError(null)
    setNotice(null)
    setLastLink(null)
    try {
      const created = await createInvitation(email.trim(), role)
      setEmail('')
      setNotice(
        created.email_sent
          ? `Invitation emailed to ${created.invitation.email}.`
          : `Invitation created for ${created.invitation.email}. Email is not configured on this deployment, so send them the link below.`,
      )
      if (!created.email_sent) {
        setLastLink({ email: created.invitation.email, url: created.accept_url })
      }
      setOffset(0)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That invitation could not be created.')
    } finally {
      setInviting(false)
    }
  }

  async function onResend(invitation: AdminInvitation) {
    setBusyId(invitation.id)
    setError(null)
    setNotice(null)
    try {
      const created = await resendInvitation(invitation.id)
      setNotice(
        created.email_sent
          ? `A new invitation was emailed to ${invitation.email}. The previous link no longer works.`
          : `A new link was created for ${invitation.email}. The previous link no longer works.`,
      )
      if (!created.email_sent) {
        setLastLink({ email: invitation.email, url: created.accept_url })
      }
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That invitation could not be resent.')
    } finally {
      setBusyId(null)
    }
  }

  async function onRevoke(invitation: AdminInvitation) {
    setBusyId(invitation.id)
    setError(null)
    setNotice(null)
    try {
      const updated = await revokeInvitation(invitation.id)
      setList((current) =>
        current
          ? {
              ...current,
              invitations: current.invitations.map((i) => (i.id === updated.id ? updated : i)),
            }
          : current,
      )
      setNotice(`The invitation for ${invitation.email} was withdrawn. Its link no longer works.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That invitation could not be withdrawn.')
    } finally {
      setBusyId(null)
    }
  }

  const invitations = list?.invitations ?? []
  const roles = list?.assignable_roles ?? []
  const total = list?.total ?? 0
  const showingTo = Math.min(offset + PAGE_SIZE, total)

  return (
    <section aria-labelledby="invitations-heading">
      <header className="mb-6">
        <h2 id="invitations-heading" className="text-lg font-semibold tracking-tight">
          Invitations
        </h2>
        <p className="mt-1 text-sm text-surface-subtle">
          Invite someone by email. The link works once and expires — resending
          issues a new one and immediately retires the old.
        </p>
      </header>

      <form
        onSubmit={submitInvite}
        className="mb-6 grid gap-3 rounded-lg border border-surface-border bg-surface p-4 sm:grid-cols-[1fr_auto_auto]"
      >
        <label className="block">
          <span className="mb-1 block text-sm font-medium">Email address</span>
          <input
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="colleague@example.com"
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium">Role</span>
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm sm:w-48"
          >
            {roles.map((option) => (
              <option key={option} value={option}>
                {roleLabel(option)}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-end">
          <button
            type="submit"
            disabled={inviting || !email.trim() || !role}
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary-strong disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:w-auto"
          >
            {inviting ? 'Inviting…' : 'Send invitation'}
          </button>
        </div>
      </form>

      {error ? (
        <p
          role="alert"
          className="mb-4 rounded-md border border-danger-border bg-danger-soft px-3 py-2 text-sm text-danger-strong"
        >
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="mb-4 rounded-md border border-success-border bg-success-soft px-3 py-2 text-sm text-success-strong"
        >
          {notice}
        </p>
      ) : null}

      {lastLink ? (
        <div className="mb-4 rounded-md border border-surface-border bg-surface-muted px-3 py-3">
          <p className="text-sm font-medium">Invitation link for {lastLink.email}</p>
          <p className="mt-1 text-xs text-surface-subtle">
            Shown once. Send it to them over a channel you trust — anyone holding
            it can take the seat.
          </p>
          <code className="mt-2 block overflow-x-auto rounded border border-surface-border bg-surface px-2 py-1 text-xs">
            {lastLink.url}
          </code>
        </div>
      ) : null}

      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="block">
          <span className="mb-1 block text-sm font-medium">Search</span>
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setOffset(0)
              setSearch(event.target.value)
            }}
            placeholder="Filter by email"
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium">Status</span>
          <select
            value={statusFilter}
            onChange={(event) => {
              setOffset(0)
              setStatusFilter(event.target.value)
            }}
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm sm:w-44"
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="revoked">Revoked</option>
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface">
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="sr-only">
            Invitations to this organization, with their role and state
          </caption>
          <thead className="border-b border-surface-border text-xs uppercase tracking-wide text-surface-subtle">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">Invitee</th>
              <th scope="col" className="px-4 py-3 font-medium">Role</th>
              <th scope="col" className="px-4 py-3 font-medium">State</th>
              <th scope="col" className="px-4 py-3 font-medium">Expires</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && invitations.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-surface-subtle">
                  Loading invitations…
                </td>
              </tr>
            ) : invitations.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-surface-subtle">
                  {search || statusFilter
                    ? 'No invitations match those filters.'
                    : 'Nobody has been invited yet.'}
                </td>
              </tr>
            ) : (
              invitations.map((invitation) => {
                const state = stateOf(invitation)
                const busy = busyId === invitation.id
                const settled = invitation.status === 'accepted'
                return (
                  <tr key={invitation.id} className="border-b border-surface-border last:border-0">
                    <td className="px-4 py-3">
                      <span className="block font-medium">{invitation.email}</span>
                      {invitation.invited_by_email ? (
                        <span className="text-xs text-surface-subtle">
                          Invited by {invitation.invited_by_email}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">{roleLabel(invitation.role)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${state.tone}`}
                      >
                        {state.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-surface-subtle">
                      {formatDate(invitation.expires_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <button
                          type="button"
                          disabled={busy || settled}
                          onClick={() => onResend(invitation)}
                          className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm font-medium transition-colors hover:border-primary hover:text-primary disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        >
                          {busy ? 'Working…' : 'Resend'}
                        </button>
                        <button
                          type="button"
                          disabled={busy || settled || invitation.status === 'revoked'}
                          onClick={() => onRevoke(invitation)}
                          className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm font-medium text-danger-strong transition-colors hover:border-danger-border hover:bg-danger-soft disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        >
                          Withdraw
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE ? (
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-sm text-surface-subtle">
            Showing {offset + 1}–{showingTo} of {total}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={showingTo >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
