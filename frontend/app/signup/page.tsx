'use client'

import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Button from '@/components/Button'
import CustomFormError from '@/components/CustomFormError'
import CustomFormField, { customFieldErrorId } from '@/components/CustomFormField'
import CustomPasswordField from '@/components/CustomPasswordField'
import PasswordStrengthMeter from '@/components/PasswordStrengthMeter'
import SocialSignIn from '@/components/SocialSignIn'
import { useAuth } from '@/components/AuthProvider'
import { SignedUpButNotSignedInError } from '@/lib/auth'
import {
  validateEmail,
  validateNewPassword,
  validatePasswordConfirmation,
} from '@/lib/validation'

// No terms checkbox. There are no terms: asking someone to agree to a document
// that has not been written is a consent that means nothing, and a required one
// at that. The checkbox and the page it pointed at come back together with the
// real text — see docs/tech-debt.md.

const FORM_ERROR_ID = 'signup-error'
const PASSWORD_METER_ID = 'password-strength'

interface FieldErrors {
  organizationName?: string | null
  email?: string | null
  password?: string | null
  confirmPassword?: string | null
}

export default function SignupPage() {
  const router = useRouter()
  const { signUp, status } = useAuth()
  const [accountType, setAccountType] = useState<'individual' | 'organization'>(
    'individual',
  )
  const [organizationName, setOrganizationName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Someone already signed in has no business on this form.
  useEffect(() => {
    if (status === 'authenticated') router.replace('/dashboard')
  }, [status, router])

  // Memoized because it is a prop on the meter, which re-evaluates the policy
  // whenever it changes; a fresh object literal every render would defeat that.
  const passwordContext = useMemo(
    () => ({
      email,
      organizationName: accountType === 'organization' ? organizationName : null,
    }),
    [email, accountType, organizationName],
  )

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const errors: FieldErrors = {
      email: validateEmail(email),
      // The context is what lets the policy reject a password assembled from
      // the address and organization name typed on this same form — the server
      // applies exactly this rule with exactly these two values.
      password: validateNewPassword(password, passwordContext),
      confirmPassword: validatePasswordConfirmation(confirmPassword, password),
      organizationName:
        accountType === 'organization' && !organizationName.trim()
          ? 'Enter your organization name.'
          : null,
    }
    setFieldErrors(errors)
    const order = ['organization-name', 'email', 'password', 'confirm-password'] as const
    const keys = ['organizationName', 'email', 'password', 'confirmPassword'] as const
    const firstInvalid = order.find((_, i) => errors[keys[i]])
    if (firstInvalid) {
      // Moving focus is what announces the failure: a screen reader reads the
      // label, the invalid state, and the message wired up by aria-describedby.
      // Without it, submitting an empty form is silent.
      document.getElementById(firstInvalid)?.focus()
      return
    }

    // Button disables itself while `loading`, so a second click cannot fire a
    // second request; this flag is what drives it.
    setSubmitting(true)
    try {
      // The signup endpoint returns no session, so `signUp` creates the account
      // and spends the same credentials on a login rather than asking for them
      // twice. Either request failing lands in the catch below.
      await signUp(email.trim(), password, {
        accountType,
        organizationName:
          accountType === 'organization' ? organizationName.trim() : undefined,
      })
      router.push('/dashboard')
    } catch (err) {
      setSubmitting(false)
      if (err instanceof SignedUpButNotSignedInError) {
        setFormError(
          'Your account was created, but we could not sign you in. Try logging in.',
        )
        return
      }
      setFormError(
        err instanceof Error
          ? err.message
          : "We couldn't create your account. Try again.",
      )
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-8">
      <div className="space-y-8">
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Create your account
          </h1>
          <p className="text-sm text-surface-subtle">
            Track how AI answers talk about your brand over time.
          </p>
        </header>

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-surface-foreground">
              Account type
            </legend>
            <p className="text-sm text-surface-subtle">
              Both get their own organization. An individual account is a team of
              one — you can name it and invite people later without moving any
              data.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {(
                [
                  ['individual', 'Individual', 'Just me for now'],
                  ['organization', 'Organization', 'A team with a shared account'],
                ] as const
              ).map(([value, label, hint]) => (
                <label
                  key={value}
                  className={`flex min-h-[44px] cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${
                    accountType === value
                      ? 'border-primary bg-primary/5'
                      : 'border-surface-border hover:border-primary/50'
                  }`}
                >
                  <input
                    type="radio"
                    name="account-type"
                    value={value}
                    checked={accountType === value}
                    onChange={() => setAccountType(value)}
                    className="mt-1 h-4 w-4 shrink-0 accent-[color:var(--color-primary,#2563eb)]"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{label}</span>
                    <span className="block text-xs text-surface-subtle">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {accountType === 'organization' ? (
            <CustomFormField
              id="organization-name"
              name="organizationName"
              type="text"
              label="Organization name"
              autoComplete="organization"
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              error={fieldErrors.organizationName ?? null}
              required
            />
          ) : null}

          <CustomFormField
            id="email"
            name="email"
            type="email"
            label="Work email"
            autoComplete="email"
            maxLength={254}
            placeholder="you@company.com"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value)
              setFieldErrors((current) => ({ ...current, email: null }))
            }}
            disabled={submitting}
            error={fieldErrors.email}
          />

          <CustomPasswordField
            id="password"
            name="password"
            label="Password"
            autoComplete="new-password"
            maxLength={128}
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
              setFieldErrors((current) => ({ ...current, password: null }))
            }}
            disabled={submitting}
            error={fieldErrors.password}
            // No hint: the meter below states every rule, and a static "at
            // least N characters" line under a live checklist saying the same
            // thing is one of them lying the day the policy moves. Error first
            // when there is one, matching what CustomFieldShell does for a
            // hint — the reason a field was rejected must not be buried behind
            // a rule the reader has already broken.
            aria-describedby={
              fieldErrors.password ? customFieldErrorId('password') : PASSWORD_METER_ID
            }
          />

          <PasswordStrengthMeter
            id={PASSWORD_METER_ID}
            value={password}
            context={passwordContext}
          />

          <CustomPasswordField
            id="confirm-password"
            name="confirmPassword"
            label="Confirm password"
            autoComplete="new-password"
            maxLength={128}
            value={confirmPassword}
            onChange={(event) => {
              setConfirmPassword(event.target.value)
              setFieldErrors((current) => ({ ...current, confirmPassword: null }))
            }}
            disabled={submitting}
            error={fieldErrors.confirmPassword}
          />

          {formError ? (
            <CustomFormError id={FORM_ERROR_ID}>{formError}</CustomFormError>
          ) : null}

          <Button type="submit" loading={submitting} className="w-full">
            Sign up
          </Button>
        </form>

        {/* The account-type choice above rides along: it is what decides whether
            a brand new provider account gets a personal org or a named company
            one, and it is ignored for somebody who already has an account. */}
        <SocialSignIn
          accountType={accountType}
          organizationName={
            accountType === 'organization' ? organizationName.trim() || null : null
          }
          onSignedIn={() => router.push('/dashboard')}
          disabled={submitting}
        />

        <p className="text-sm text-surface-subtle">
          {'Already have an account? '}
          <Link
            href="/login"
            className="rounded font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Login
          </Link>
        </p>
      </div>
    </main>
  )
}
