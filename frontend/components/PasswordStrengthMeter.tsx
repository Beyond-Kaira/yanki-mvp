'use client'

import { useMemo } from 'react'
import {
  MIN_PASSWORD_LENGTH,
  SCORE_LABELS,
  evaluatePassword,
} from '@/lib/password-policy'
import type { PasswordContext, PasswordRule } from '@/lib/password-policy'

interface PasswordStrengthMeterProps {
  id: string
  value: string
  context?: PasswordContext
}

// The four things this form promises to check, in the order somebody fixes
// them. Deliberately fewer items than there are rules: 'repetitive',
// 'low_variety' and 'sequential' are three ways of saying one thing to the
// person typing — the password is a pattern — and three separate red lines for
// one mistake reads as a system arguing with itself.
const CHECKS: { label: string; rules: PasswordRule[] }[] = [
  {
    label: `At least ${MIN_PASSWORD_LENGTH} characters`,
    rules: ['too_short', 'too_long'],
  },
  { label: 'Not a commonly used password', rules: ['common'] },
  { label: 'Not built from your email or organization', rules: ['context'] },
  {
    label: 'Not an obvious pattern or keyboard run',
    rules: ['repetitive', 'low_variety', 'sequential'],
  },
]

const BAR_TONES = [
  'bg-danger',
  'bg-danger',
  'bg-warning',
  'bg-success',
  'bg-success',
] as const

/**
 * What the password is worth, while it is being typed.
 *
 * **The checklist is the useful half.** A bar alone tells somebody they are
 * doing badly without telling them what to change, which is how people end up
 * appending an exclamation mark. Each row here names a rule the server actually
 * enforces, so satisfying the list means the submit will go through.
 *
 * **The score is advisory and says so by never blocking anything.** The policy
 * accepts a long all-lowercase passphrase, and the meter shows it as "Fair"
 * rather than red — see `lib/password-policy.ts` for why a score threshold
 * would quietly become the composition rule the policy refuses to have.
 *
 * **It announces politely, and only when there is something to say.** The live
 * region is `polite` and carries the summary, not the checklist: a screen reader
 * reading four rows on every keystroke is unusable, and the field's own error
 * message still carries the reason a submit failed.
 */
export default function PasswordStrengthMeter({
  id,
  value,
  context,
}: PasswordStrengthMeterProps) {
  const verdict = useMemo(() => evaluatePassword(value, context), [value, context])

  // Nothing typed yet: an empty field is not a failing one, and four red
  // crosses as a greeting is a hostile way to open a form.
  if (!value) return null

  const broken = new Set(verdict.failures.map((failure) => failure.rule))
  const label = SCORE_LABELS[verdict.score] ?? SCORE_LABELS[0]

  return (
    <div id={id} className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex h-1.5 flex-1 gap-1" role="presentation">
          {[0, 1, 2, 3].map((segment) => (
            <span
              key={segment}
              className={`h-full flex-1 rounded-full ${
                segment < verdict.score ? BAR_TONES[verdict.score] : 'bg-surface-border'
              }`}
            />
          ))}
        </div>
        <span className="text-xs font-medium text-surface-subtle">{label}</span>
      </div>

      {/* The summary only. See the component docstring for why the rows below
          are not in the live region. */}
      <p aria-live="polite" className="sr-only">
        {verdict.ok
          ? `Password strength: ${label}.`
          : `Password not accepted yet: ${verdict.failures[0].message}`}
      </p>

      <ul className="space-y-1">
        {CHECKS.map((check) => {
          const met = !check.rules.some((rule) => broken.has(rule))
          return (
            <li
              key={check.label}
              className={`flex items-start gap-1.5 text-xs ${
                met ? 'text-success-strong' : 'text-surface-subtle'
              }`}
            >
              <span aria-hidden="true" className="leading-4">
                {met ? '✓' : '•'}
              </span>
              <span>{check.label}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
