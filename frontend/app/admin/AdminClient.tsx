'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import {
  ApiError,
  fetchMembers,
  fetchOrganization,
  removeMember,
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

function historyHref(memberId: string): string {
  return `/admin/audit?entity_type=user&entity_id=${encodeURIComponent(memberId)}`
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
 * The list is a reading surface: a row shows who someone is and what they may
 * do, and clicking it opens that member's history. The only edit left in the
 * table is removal, and it asks first.
 *
 * The server owns the rules. The role filter's options come from
 * `assignable_roles` in the list response rather than a constant here, so the
 * screen can never name a role the API does not recognize — including the
 * platform roles a customer must never see. The lockout guards (last owner,
 * self-edit) live in the backend; this UI surfaces their 409 as a readable
 * message rather than trying to predict them.
 */
export default function AdminClient() {
  const { user } = useAuth()
  const router = useRouter()
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

  // Removal is the one irreversible action on this screen — the seat and its
  // role are gone, and getting the person back means inviting them again. It
  // therefore asks first, which nothing else here does.
  async function confirmRemove(member: AdminMember) {
    const ok = window.confirm(
      `Remove ${member.email} from this organization?\n\n` +
        'They keep their account and their own data. To let them back in you ' +
        'will have to invite them again.',
    )
    if (!ok) return

    setSavingId(member.id)
    setNotice(null)
    setError(null)
    try {
      await removeMember(member.id)
      setList((current) =>
        current
          ? {
              ...current,
              total: Math.max(0, current.total - 1),
              members: current.members.filter((m) => m.id !== member.id),
            }
          : current,
      )
      setNotice(`${member.email} no longer has a seat in this organization.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That member could not be removed.')
    } finally {
      setSavingId(null)
    }
  }

  const members = list?.members ?? []
  const roles = list?.assignable_roles ?? []
  const total = list?.total ?? 0
  const showingTo = Math.min(offset + PAGE_SIZE, total)

  return (
    <section aria-labelledby="members-heading">
      <header className="mb-6">
        <h2 id="members-heading" className="text-lg font-semibold tracking-tight">
          Members &amp; roles
        </h2>
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
                  <tr
                    key={member.id}
                    onClick={() => router.push(historyHref(member.id))}
                    className="cursor-pointer border-b border-surface-border transition-colors last:border-0 hover:bg-surface-muted"
                  >
                    <td className="px-4 py-3">
                      {/* The whole row is clickable for the mouse; this link is
                          what makes the same destination reachable by keyboard
                          and announced by a screen reader. */}
                      <Link
                        href={historyHref(member.id)}
                        onClick={(event) => event.stopPropagation()}
                        className="block font-medium underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        {member.email}
                      </Link>
                      {isSelf ? (
                        <span className="text-xs text-surface-subtle">That&apos;s you</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">{roleLabel(member.role)}</td>
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
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end">
                        <button
                          type="button"
                          disabled={busy || isSelf}
                          aria-label={`Remove ${member.email}`}
                          // An icon-only button that silently does nothing reads
                          // as broken; the tooltip says which of the two reasons
                          // it is.
                          title={
                            isSelf
                              ? 'You cannot remove your own seat'
                              : busy
                                ? 'Working…'
                                : 'Remove'
                          }
                          onClick={(event) => {
                            event.stopPropagation()
                            confirmRemove(member)
                          }}
                          className="inline-flex h-11 w-11 items-center justify-center rounded-md text-lg font-semibold leading-none text-surface-subtle transition-colors hover:bg-danger-soft hover:text-danger-strong disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-border"
                        >
                          ✕
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
