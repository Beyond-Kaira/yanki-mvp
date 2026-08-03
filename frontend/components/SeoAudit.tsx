'use client'

import { useState } from 'react'
import type { SeoAudit as SeoAuditData, SeoCheck } from '@/lib/contracts'

interface SeoAuditProps {
  seo: SeoAuditData
}

// Why the audit produced no grade, in the user's words. Same discipline as the
// SERP panel: we never draw a grade for a measurement we did not take.
const STATUS_NOTES: Record<string, string> = {
  no_crawl:
    'There was no crawl to audit for this run, so the AI-readiness checks did not run.',
  error: 'The AI-readiness audit could not be completed for this run.',
}

// Grade bands, mirrored from the backend (`_GRADE_BANDS` in
// `backend/app/pipeline/seo_audit.py`). Reconstructing the raw band from the
// score is the only way the UI can tell whether the published grade was lowered
// by a critical failure, versus being that letter on its own merits — which is
// exactly the "why" the headline has to explain.
const GRADE_BANDS: ReadonlyArray<readonly [number, string]> = [
  [90, 'A'],
  [75, 'B'],
  [60, 'C'],
  [40, 'D'],
]

function bandFromScore(score: number): string {
  for (const [threshold, letter] of GRADE_BANDS) {
    if (score >= threshold) return letter
  }
  return 'F'
}

type Tone = 'success' | 'warning' | 'danger'

// A/B are healthy, F is fatal, C/D sit in between. The grade tile colour is
// always backed by the letter itself, never colour alone.
function gradeTone(grade: string): Tone {
  if (grade === 'A' || grade === 'B') return 'success'
  if (grade === 'F') return 'danger'
  return 'warning'
}

const GRADE_TILE_CLASS: Record<Tone, string> = {
  success: 'bg-success-soft text-success-strong',
  warning: 'bg-warning-soft text-warning-strong',
  danger: 'bg-danger-soft text-danger-strong',
}

// Per-check status. The last two are excluded from the score and mean different
// things — "we could not read the input" versus "this does not apply here" — so
// they carry distinct labels and are never rendered as a failure.
const STATUS_META: Record<string, { label: string; badge: string }> = {
  pass: { label: 'Passed', badge: 'bg-success-soft text-success-strong' },
  warn: { label: 'Warning', badge: 'bg-warning-soft text-warning-strong' },
  fail: { label: 'Failed', badge: 'bg-danger-soft text-danger-strong' },
  not_measured: {
    label: 'Not measured',
    badge: 'bg-surface-muted text-surface-subtle',
  },
  not_applicable: {
    label: 'Not applicable',
    badge: 'bg-surface-muted text-surface-subtle',
  },
}

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'Critical',
  important: 'Important',
  minor: 'Minor',
}

// Within the failing bucket, the fatal ones come first — that is the order a
// reader should fix them in.
const SEVERITY_RANK: Record<string, number> = {
  critical: 0,
  important: 1,
  minor: 2,
}

function cappedMessage(grade: string, criticalFailures: number): string {
  if (criticalFailures <= 0) {
    return `Capped at ${grade} by a critical failure, which limits the grade regardless of the score.`
  }
  const subject =
    criticalFailures === 1
      ? 'one critical check is failing'
      : `${criticalFailures} critical checks are failing`
  return `Capped at ${grade}: ${subject}, which limits the grade no matter how many others pass.`
}

// The audit that explains the GEO and SERP scores above: whether an answer
// engine can read this site at all, and if not, why. The grade — not the score —
// is the headline, because a weighted average can average a fatal problem away;
// the failing checks are the actionable part, so they lead.
export default function SeoAudit({ seo }: SeoAuditProps) {
  const checks = seo.checks
  const failed = checks
    .filter((check) => check.status === 'fail')
    .slice()
    .sort(
      (a, b) =>
        (SEVERITY_RANK[a.severity] ?? 99) - (SEVERITY_RANK[b.severity] ?? 99),
    )
  const warnings = checks.filter((check) => check.status === 'warn')
  const passed = checks.filter((check) => check.status === 'pass')
  // "We could not read the input" and "does not apply here" are both excluded
  // from the score; grouped here so they are never mistaken for failures.
  const notScored = checks.filter(
    (check) =>
      check.status === 'not_measured' || check.status === 'not_applicable',
  )
  const scoredCount = failed.length + warnings.length + passed.length

  const graded = seo.grade !== null && seo.score !== null
  const criticalFailures = failed.filter(
    (check) => check.severity === 'critical',
  ).length
  const capped =
    graded && seo.grade !== bandFromScore(seo.score as number)

  return (
    <section className="space-y-3" aria-labelledby="seo-audit-heading">
      <div className="space-y-1">
        <h2
          id="seo-audit-heading"
          className="text-xl font-semibold text-surface-foreground"
        >
          AI readiness audit
        </h2>
        <p className="max-w-2xl text-sm text-surface-subtle">
          Whether an answer engine can read this site at all — the checks behind
          the scores above, with what blocks AI visibility first.
        </p>
      </div>

      {checks.length === 0 ? (
        <p className="text-sm text-surface-subtle">
          {STATUS_NOTES[seo.status] ??
            'The AI-readiness audit was not run for this analysis.'}
        </p>
      ) : (
        <>
          {graded ? (
            <div className="rounded-xl border border-surface-border bg-white p-5">
              <div className="flex flex-wrap items-center gap-4">
                <div
                  className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-xl text-4xl font-bold ${GRADE_TILE_CLASS[gradeTone(seo.grade as string)]}`}
                >
                  {seo.grade}
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-surface-foreground">
                    AI readiness grade
                  </p>
                  <p className="text-sm text-surface-subtle">
                    Weighted score {seo.score} / 100 across {scoredCount}{' '}
                    scored {scoredCount === 1 ? 'check' : 'checks'}.
                  </p>
                  {capped ? (
                    <p className="text-sm font-medium text-warning-strong">
                      {cappedMessage(seo.grade as string, criticalFailures)}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-surface-subtle">
              None of this run&apos;s checks could be scored, so there is no
              grade. The individual checks are listed below.
            </p>
          )}

          {failed.length > 0 ? (
            <CheckGroup
              title={`Failing checks (${failed.length})`}
              description="Fix these first. Critical failures cap the grade no matter what else passes."
              checks={failed}
            />
          ) : null}

          {warnings.length > 0 ? (
            <CheckGroup
              title={`Warnings (${warnings.length})`}
              description="Not fatal, but each one costs some visibility."
              checks={warnings}
            />
          ) : null}

          {passed.length > 0 ? (
            <CheckDisclosure
              id="passed"
              title={`Passing checks (${passed.length})`}
              checks={passed}
            />
          ) : null}

          {notScored.length > 0 ? (
            <CheckDisclosure
              id="not-scored"
              title={`Not scored (${notScored.length})`}
              note="These checks are left out of the score — either we could not read the input (not measured) or the check does not apply to this site (not applicable)."
              checks={notScored}
            />
          ) : null}
        </>
      )}
    </section>
  )
}

function CheckGroup({
  title,
  description,
  checks,
}: {
  title: string
  description?: string
  checks: SeoCheck[]
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-surface-foreground">{title}</h3>
      {description ? (
        <p className="text-sm text-surface-subtle">{description}</p>
      ) : null}
      <ul className="space-y-2">
        {checks.map((check) => (
          <CheckRow key={check.id} check={check} />
        ))}
      </ul>
    </div>
  )
}

function CheckDisclosure({
  id,
  title,
  note,
  checks,
}: {
  id: string
  title: string
  note?: string
  checks: SeoCheck[]
}) {
  const [open, setOpen] = useState(false)
  const regionId = `seo-audit-${id}`

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={regionId}
        className="inline-flex min-h-[32px] items-center gap-1 rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <Chevron open={open} />
        {open ? `Hide ${title.toLowerCase()}` : `Show ${title.toLowerCase()}`}
      </button>
      {open ? (
        <div id={regionId} className="space-y-2">
          {note ? (
            <p className="text-sm text-surface-subtle">{note}</p>
          ) : null}
          <ul className="space-y-2">
            {checks.map((check) => (
              <CheckRow key={check.id} check={check} />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function CheckRow({ check }: { check: SeoCheck }) {
  const status = STATUS_META[check.status] ?? {
    label: check.status,
    badge: 'bg-surface-muted text-surface-subtle',
  }
  const severity = SEVERITY_LABEL[check.severity] ?? check.severity

  return (
    <li className="rounded-lg border border-surface-border bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-surface-foreground">
          {check.title}
        </span>
        <span className="inline-flex items-center rounded-full border border-surface-border px-2 py-0.5 text-xs text-surface-subtle">
          {severity}
        </span>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${status.badge}`}
        >
          {status.label}
        </span>
      </div>
      {check.detail ? (
        <p className="mt-1 text-sm text-surface-subtle">{check.detail}</p>
      ) : null}
      {check.status === 'not_measured' ? (
        <p className="mt-1 text-xs text-surface-subtle">
          Left out of the score — we could not read the input.
        </p>
      ) : null}
      {check.status === 'not_applicable' ? (
        <p className="mt-1 text-xs text-surface-subtle">
          Left out of the score — this check does not apply here.
        </p>
      ) : null}
      {check.evidence ? (
        <p className="mt-2 whitespace-pre-wrap break-words rounded bg-surface-muted px-2 py-1 font-mono text-xs text-surface-subtle">
          {check.evidence}
        </p>
      ) : null}
    </li>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`h-3 w-3 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  )
}
