'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import Link from 'next/link'
import Button from '@/components/Button'
import FormError from '@/components/FormError'
import FormField from '@/components/FormField'
import { requestPasswordReset } from '@/lib/auth'
import { validateEmail } from '@/lib/validation'

const FORM_ERROR_ID = 'forgot-password-error'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const error = validateEmail(email)
    setFieldError(error)
    if (error) {
      // Moving focus is what announces the failure to a screen reader.
      document.getElementById('email')?.focus()
      return
    }

    setSubmitting(true)
    try {
      await requestPasswordReset(email.trim())
      setSent(true)
    } catch (err) {
      setSubmitting(false)
      setFormError(
        err instanceof Error
          ? err.message
          : "We couldn't send the reset link. Try again.",
      )
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-8">
      <div className="space-y-8">
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Reset your password
          </h1>
          <p className="text-sm text-surface-subtle">
            Enter the email you signed up with and we&apos;ll send you a link to
            set a new password.
          </p>
        </header>

        {sent ? (
          // Deliberately says nothing about whether that address has an account:
          // a different message for a known and an unknown email would turn this
          // form into a way to test which addresses are registered.
          <div
            role="status"
            className="space-y-3 rounded-xl border border-surface-border bg-white p-6"
          >
            <h2 className="text-base font-semibold text-surface-foreground">
              Check your inbox
            </h2>
            <p className="text-sm text-surface-subtle">
              If an account exists for {email.trim()}, a reset link is on its
              way. The link expires shortly, so use it soon.
            </p>
            <Link
              href="/login"
              className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              Back to log in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <FormField
              id="email"
              name="email"
              type="email"
              label="Email"
              autoComplete="email"
              maxLength={254}
              placeholder="you@company.com"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value)
                setFieldError(null)
              }}
              disabled={submitting}
              error={fieldError}
            />

            {formError ? (
              <FormError id={FORM_ERROR_ID}>{formError}</FormError>
            ) : null}

            <Button type="submit" loading={submitting} className="w-full">
              Send reset link
            </Button>
          </form>
        )}

        <p className="text-sm text-surface-subtle">
          {'Remembered it? '}
          <Link
            href="/login"
            className="rounded font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Log in
          </Link>
        </p>
      </div>
    </main>
  )
}
