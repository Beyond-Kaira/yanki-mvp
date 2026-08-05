'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  ApiError,
  fetchAuditEvents,
  fetchAuditIntegrity,
  fetchRecordHistory,
  type AuditQuery,
} from '@/lib/api'
import type { AuditEvent, AuditEventList, AuditIntegrity } from '@/lib/contracts'

const PAGE_SIZE = 25

const SORTABLE: { id: string; label: string }[] = [
  { id: 'occurred_at', label: 'Time' },
  { id: 'action', label: 'Action' },
  { id: 'actor_label', label: 'Actor' },
  { id: 'entity_type', label: 'Entity' },
  { id: 'outcome', label: 'Outcome' },
]

const OUTCOME_TONE: Record<string, string> = {
  success: 'bg-success-soft text-success-strong',
  denied: 'bg-warning-soft text-warning-strong',
  error: 'bg-danger-soft text-danger-strong',
}

function formatMoment(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** A `{from, to}` diff rendered as readable lines; `null` when there is none. */
function changeLines(event: AuditEvent): string[] {
  const changed = event.changed
  if (!changed || typeof changed !== 'object') return []
  return Object.entries(changed).map(([field, delta]) => {
    const pair = delta as { from?: unknown; to?: unknown } | null
    const from = pair && 'from' in pair ? JSON.stringify(pair.from) : '—'
    const to = pair && 'to' in pair ? JSON.stringify(pair.to) : '—'
    return `${field}: ${from} → ${to}`
  })
}

/**
 * The audit log.
 *
 * **Everything narrows the same query.** Filters, search, sort, and paging all
 * feed one request; the server does the work and reports the true total, so
 * "1–25 of 340" means what it says instead of counting the current page.
 *
 * **A record's history is the same screen, pre-filtered.** Arriving from a
 * member row's "History" link sets `entity_type`/`entity_id` from the URL, which
 * keeps one component rather than a second near-duplicate — and means the
 * filters stay available to widen from there.
 *
 * **Integrity is stated, not implied.** Each row shows whether it still hashes
 * to its stored digest, and the banner reports the sweep across the org. A log
 * that cannot say whether it was edited is a log you cannot cite.
 */
export default function AuditLogClient() {
  const params = useSearchParams()
  const entityType = params.get('entity_type') ?? ''
  const entityId = params.get('entity_id') ?? ''
  const scoped = Boolean(entityType && entityId)

  const [list, setList] = useState<AuditEventList | null>(null)
  const [integrity, setIntegrity] = useState<AuditIntegrity | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [action, setAction] = useState('')
  const [outcome, setOutcome] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [sort, setSort] = useState('occurred_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [offset, setOffset] = useState(0)

  const query = useMemo<AuditQuery>(
    () => ({
      q: search.trim() || undefined,
      action: action || undefined,
      outcome: outcome || undefined,
      occurred_from: from || undefined,
      // A date input gives a bare day; the log needs the END of that day or
      // "to: today" would exclude everything that happened today.
      occurred_to: to ? `${to}T23:59:59` : undefined,
      sort,
      order,
      limit: PAGE_SIZE,
      offset,
    }),
    [search, action, outcome, from, to, sort, order, offset],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = scoped
        ? await fetchRecordHistory(entityType, entityId)
        : await fetchAuditEvents(query)
      setList(page)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? 'You do not have permission to read the audit log. Ask an owner or admin.'
          : err instanceof Error
            ? err.message
            : 'We could not load the audit log.',
      )
    } finally {
      setLoading(false)
    }
  }, [query, scoped, entityType, entityId])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  useEffect(() => {
    // Best-effort: a failed integrity sweep must not hide the log itself.
    fetchAuditIntegrity()
      .then(setIntegrity)
      .catch(() => setIntegrity(null))
  }, [])

  const events = list?.events ?? []
  const actions = list?.actions ?? []
  const total = list?.total ?? 0
  const showingTo = Math.min(offset + PAGE_SIZE, total)

  return (
    <section aria-labelledby="audit-heading">
      <header className="mb-6">
        <h2 id="audit-heading" className="text-lg font-semibold tracking-tight">
          {scoped ? 'Change history' : 'Audit log'}
        </h2>
        <p className="mt-1 text-sm text-surface-subtle">
          {scoped
            ? `Everything that ever touched ${entityType} ${entityId}, oldest first.`
            : 'Every change made in this organization: who, what, when, and the values on both sides.'}
        </p>
      </header>

      {integrity ? (
        <p
          className={`mb-4 rounded-md border px-3 py-2 text-sm ${
            integrity.ok
              ? 'border-surface-border bg-surface-muted text-surface-subtle'
              : 'border-danger-border bg-danger-soft text-danger-strong'
          }`}
          role={integrity.ok ? undefined : 'alert'}
        >
          {integrity.ok ? (
            <>
              Integrity check: {integrity.intact} of {integrity.checked} recent entries verified
              against their stored hash
              {integrity.unverifiable > 0
                ? `, ${integrity.unverifiable} predate hashing and cannot be checked`
                : ''}
              .
            </>
          ) : (
            <>
              Integrity check failed: {integrity.altered} of {integrity.checked} recent entries no
              longer match their stored hash. Somebody changed the audit table outside the
              application.
            </>
          )}
        </p>
      ) : null}

      {scoped ? (
        <p className="mb-4 rounded-md border border-surface-border bg-surface-muted px-3 py-2 text-sm">
          Showing one record&apos;s history.{' '}
          <a
            href="/admin/audit"
            className="font-medium text-primary-strong underline underline-offset-2"
          >
            View the whole audit log
          </a>
          .
        </p>
      ) : (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Search</span>
            <input
              type="search"
              value={search}
              onChange={(event) => {
                setOffset(0)
                setSearch(event.target.value)
              }}
              placeholder="Action, actor or entity"
              className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium">Action</span>
            <select
              value={action}
              onChange={(event) => {
                setOffset(0)
                setAction(event.target.value)
              }}
              className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm"
            >
              <option value="">All actions</option>
              {actions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium">Outcome</span>
            <select
              value={outcome}
              onChange={(event) => {
                setOffset(0)
                setOutcome(event.target.value)
              }}
              className="h-11 w-full rounded-md border border-surface-border bg-surface px-3 text-sm"
            >
              <option value="">All outcomes</option>
              <option value="success">Success</option>
              <option value="denied">Denied</option>
              <option value="error">Error</option>
            </select>
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium">From</span>
              <input
                type="date"
                value={from}
                onChange={(event) => {
                  setOffset(0)
                  setFrom(event.target.value)
                }}
                className="h-11 w-full rounded-md border border-surface-border bg-surface px-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium">To</span>
              <input
                type="date"
                value={to}
                onChange={(event) => {
                  setOffset(0)
                  setTo(event.target.value)
                }}
                className="h-11 w-full rounded-md border border-surface-border bg-surface px-2 text-sm"
              />
            </label>
          </div>
        </div>
      )}

      {!scoped ? (
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Sort by</span>
            <select
              value={sort}
              onChange={(event) => {
                setOffset(0)
                setSort(event.target.value)
              }}
              className="h-11 rounded-md border border-surface-border bg-surface px-3 text-sm"
            >
              {SORTABLE.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              setOffset(0)
              setOrder((current) => (current === 'desc' ? 'asc' : 'desc'))
            }}
            aria-label={`Sort ${order === 'desc' ? 'ascending' : 'descending'}`}
            className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {order === 'desc' ? 'Newest first' : 'Oldest first'}
          </button>
        </div>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="mb-4 rounded-md border border-danger-border bg-danger-soft px-3 py-2 text-sm text-danger-strong"
        >
          {error}
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface">
        <table className="w-full min-w-[860px] text-left text-sm">
          <caption className="sr-only">
            Audit events for this organization, with actor, action and outcome
          </caption>
          <thead className="border-b border-surface-border text-xs uppercase tracking-wide text-surface-subtle">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">When</th>
              <th scope="col" className="px-4 py-3 font-medium">Actor</th>
              <th scope="col" className="px-4 py-3 font-medium">Action</th>
              <th scope="col" className="px-4 py-3 font-medium">Entity</th>
              <th scope="col" className="px-4 py-3 font-medium">Outcome</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {loading && events.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-surface-subtle">
                  Loading the audit log…
                </td>
              </tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-surface-subtle">
                  No entries match those filters.
                </td>
              </tr>
            ) : (
              events.map((event) => {
                const lines = changeLines(event)
                const open = expanded === event.id
                return (
                  <tr key={event.id} className="border-b border-surface-border align-top last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 text-surface-subtle">
                      {formatMoment(event.occurred_at)}
                      {event.integrity !== 'ok' ? (
                        <span
                          className={`mt-1 block text-xs font-medium ${
                            event.integrity === 'altered'
                              ? 'text-danger-strong'
                              : 'text-surface-subtle'
                          }`}
                        >
                          {event.integrity === 'altered' ? 'Altered' : 'Unverifiable'}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <span className="block">{event.actor_label ?? event.actor_type}</span>
                      <span className="text-xs text-surface-subtle">{event.actor_type}</span>
                    </td>
                    <td className="px-4 py-3 font-medium">{event.action}</td>
                    <td className="px-4 py-3 text-surface-subtle">
                      {event.entity_type ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          OUTCOME_TONE[event.outcome] ?? 'bg-surface-muted text-surface-subtle'
                        }`}
                      >
                        {event.outcome}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <button
                          type="button"
                          aria-expanded={open}
                          onClick={() => setExpanded(open ? null : event.id)}
                          className="inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-3 text-sm transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        >
                          {open ? 'Hide' : 'Show'}
                        </button>
                      </div>
                      {open ? (
                        <dl className="mt-3 space-y-2 text-xs">
                          {lines.length > 0 ? (
                            <div>
                              <dt className="font-medium">Changed</dt>
                              <dd>
                                <ul className="mt-1 space-y-0.5">
                                  {lines.map((line) => (
                                    <li key={line} className="font-mono">
                                      {line}
                                    </li>
                                  ))}
                                </ul>
                              </dd>
                            </div>
                          ) : null}
                          <div>
                            <dt className="font-medium">Request</dt>
                            <dd className="font-mono break-all">{event.request_id ?? '—'}</dd>
                          </div>
                          <div>
                            <dt className="font-medium">IP (hashed)</dt>
                            <dd className="font-mono break-all">
                              {event.ip_hash ? `${event.ip_hash.slice(0, 16)}…` : '—'}
                            </dd>
                          </div>
                          {event.before ? (
                            <div>
                              <dt className="font-medium">Before</dt>
                              <dd>
                                <pre className="mt-1 overflow-x-auto rounded bg-surface-muted p-2">
                                  {JSON.stringify(event.before, null, 2)}
                                </pre>
                              </dd>
                            </div>
                          ) : null}
                          {event.after ? (
                            <div>
                              <dt className="font-medium">After</dt>
                              <dd>
                                <pre className="mt-1 overflow-x-auto rounded bg-surface-muted p-2">
                                  {JSON.stringify(event.after, null, 2)}
                                </pre>
                              </dd>
                            </div>
                          ) : null}
                        </dl>
                      ) : null}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {!scoped && total > PAGE_SIZE ? (
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
