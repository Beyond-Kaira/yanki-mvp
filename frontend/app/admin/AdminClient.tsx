'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import {
  ApiError,
  fetchMembers,
  fetchOrganization,
  updateMember,
  type MemberQuery,
} from '@/lib/api'
import type { AdminMember, AdminMemberList, AdminOrganization } from '@/lib/contracts'

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
 * Members and roles for the caller's organization.
 *
 * Two things shape this screen more than layout does.
 *
 * **The server owns the rules.** The role options come from
 * `assignable_roles` in the list response rather than a constant here, so the
 * picker can never offer something the API would refuse — including the
 * platform roles a customer must never be able to grant. Likewise the two
 * lockout guards (last owner, self-edit) live in the backend; this UI surfaces
 * their 409 as a readable message rather than trying to predict them.
 *
 * **A failed change must not look like a successful one.** Every row edit is
 * optimistic in appearance but reconciled against the server's response, and a
 * rejection restores the previous value and says why. Silently reverting is how
 * an admin comes to believe they disabled someone who is still logged in.
 */
export default function AdminClient() {
  const { user } = useAuth()
  const [org, setOrg] = useState<AdminOrganization | null>(null)
  const [list, setList] = useState<AdminMemberList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)

  const query = useMemo<MemberQuery>(
    () => ({
      q: search.trim() || undefined,
      role: roleFilter || undefined,
      status: statusFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [search, roleFilter, statusFilter, offset],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [organization, members] = await Promise.all([
        fetchOrganization().catch(() => null),
        fetchMembers(query),
      ])
      if (organization) setOrg(organization)
      setList(members)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? 'You do not have permission to manage members. Ask an owner or admin.'
          : err instanceof Error
            ? err.message
            : 'We could not load your members.',
      )
    } finally {
      setLoading(false)
    }
  }, [query])

  // Debounced so typing in the search box does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  async function applyChange(member: AdminMember, changes: { role?: string; status?: string }) {
    setSavingId(member.id)
    setNotice(null)
    setError(null)
    try {
      const updated = await updateMember(member.id, changes)
      setList((current) =>
        current
          ? {
              ...current,
              members: current.members.map((m) => (m.id === updated.id ? updated : m)),
            }
          : current,
      )
      setNotice(
        changes.status
          ? `${updated.email} is now ${updated.status}.`
          : `${updated.email} is now ${roleLabel(updated.role)}.`,
      )
    } catch (err) {
      // The server's own words: "an organization must keep at least one active
      // owner" is more useful than anything this component could invent.
      setError(err instanceof Error ? err.message : 'That change could not be saved.')
    } finally {
      setSavingId(null)
    }
  }

  const members = list?.members ?? []
  const roles = list?.assignable_roles ?? []
  const total = list?.total ?? 0
  const showingTo = Math.min(offset + PAGE_SIZE, total)

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Members &amp; roles
        </h1>
        {org ? (
          <p className="mt-1 text-sm text-surface-subtle">
            {org.name} · {org.kind === 'company' ? 'Organization' : 'Individual'} account ·{' '}
            {org.member_count} {org.member_count === 1 ? 'member' : 'members'}
          </p>
        ) : null}
      </header>

      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
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
          <span className="mb-1 block text-sm font-medium">Role</span>
          <select
            value={roleFilter}
            onChange={(event) => {
              setOffset(0)
              setRoleFilter(event.target.value)
            }}
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm sm:w-44"
          >
            <option value="">All roles</option>
            {roles.map((role) => (
              <option key={role} value={role}>
                {roleLabel(role)}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium">Status</span>
          <select
            value={statusFilter}
            onChange={(event) => {
              setOffset(0)
              setStatusFilter(event.target.value)
            }}
            className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm sm:w-36"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </select>
        </label>
      </div>

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

      {/* The table scrolls inside its own container rather than pushing the
          page sideways — the classic mobile overflow. */}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface">
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="sr-only">
            Members of this organization, with their role and account status
          </caption>
          <thead className="border-b border-surface-border text-xs uppercase tracking-wide text-surface-subtle">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">Member</th>
              <th scope="col" className="px-4 py-3 font-medium">Role</th>
              <th scope="col" className="px-4 py-3 font-medium">Status</th>
              <th scope="col" className="px-4 py-3 font-medium">Joined</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && members.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-surface-subtle">
                  Loading members…
                </td>
              </tr>
            ) : members.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-surface-subtle">
                  {search || roleFilter || statusFilter
                    ? 'No members match those filters.'
                    : 'No members yet.'}
                </td>
              </tr>
            ) : (
              members.map((member) => {
                const isSelf = member.id === user?.id
                const busy = savingId === member.id
                return (
                  <tr key={member.id} className="border-b border-surface-border last:border-0">
                    <td className="px-4 py-3">
                      <span className="block font-medium">{member.email}</span>
                      {isSelf ? (
                        <span className="text-xs text-surface-subtle">That&apos;s you</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <label className="sr-only" htmlFor={`role-${member.id}`}>
                        Role for {member.email}
                      </label>
                      <select
                        id={`role-${member.id}`}
                        value={member.role}
                        disabled={busy || isSelf}
                        onChange={(event) =>
                          applyChange(member, { role: event.target.value })
                        }
                        className="h-11 rounded-md border border-surface-border bg-surface px-2 text-sm disabled:opacity-60"
                      >
                        {roles.map((role) => (
                          <option key={role} value={role}>
                            {roleLabel(role)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          member.status === 'active'
                            ? 'bg-success-soft text-success-strong'
                            : 'bg-surface-muted text-surface-subtle'
                        }`}
                      >
                        {member.status === 'active' ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-surface-subtle">
                      {formatDate(member.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        disabled={busy || isSelf}
                        onClick={() =>
                          applyChange(member, {
                            status: member.status === 'active' ? 'disabled' : 'active',
                          })
                        }
                        className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm font-medium transition-colors hover:border-primary hover:text-primary disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        {busy
                          ? 'Saving…'
                          : member.status === 'active'
                            ? 'Disable'
                            : 'Enable'}
                      </button>
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
    </div>
  )
}
