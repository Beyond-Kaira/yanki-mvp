'use client'

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Button from '@/components/Button'
import FormError from '@/components/FormError'
import FormField from '@/components/FormField'
import PasswordField from '@/components/PasswordField'
import { useAuth } from '@/components/AuthProvider'
import { validateEmail, validateExistingPassword } from '@/lib/validation'

const FORM_ERROR_ID = 'login-error'

interface FieldErrors {
  email?: string | null
  password?: string | null
}

export default function LoginPage() {
  const router = useRouter()
  const { signIn, status } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Someone already signed in has no business on this form.
  useEffect(() => {
    if (status === 'authenticated') router.replace('/')
  }, [status, router])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const errors: FieldErrors = {
      email: validateEmail(email),
      password: validateExistingPassword(password),
    }
    setFieldErrors(errors)
    const firstInvalid = errors.email ? 'email' : errors.password ? 'password' : null
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
      await signIn(email.trim(), password)
      // TODO(auth): no signed-in destination exists yet, so this returns to the
      // home page, where the header now shows the account. Point it at an
      // account view once there is one.
      router.push('/')
    } catch (err) {
      setSubmitting(false)
      setFormError(
        err instanceof Error
          ? err.message
          : "We couldn't sign you in. Try again.",
      )
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-8">
      <div className="space-y-8">
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Log in
          </h1>
          <p className="text-sm text-surface-subtle">
            Welcome back. Pick up where your last analysis left off.
          </p>
        </header>

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
              // Clear this field's message as it is corrected; the form-level
              // error stays until the next submit actually resolves.
              setFieldErrors((current) => ({ ...current, email: null }))
            }}
            disabled={submitting}
            error={fieldErrors.email}
          />

          <PasswordField
            id="password"
            name="password"
            label="Password"
            autoComplete="current-password"
            maxLength={128}
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
              setFieldErrors((current) => ({ ...current, password: null }))
            }}
            disabled={submitting}
            error={fieldErrors.password}
          />

          <div className="flex flex-wrap items-center justify-end gap-3">
            <Link
              href="/forgot-password"
              className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              Forgot password?
            </Link>
          </div>

          {formError ? (
            <FormError id={FORM_ERROR_ID}>{formError}</FormError>
          ) : null}

          <Button type="submit" loading={submitting} className="w-full">
            Log in
          </Button>
        </form>

        <p className="text-sm text-surface-subtle">
          {"Don't have an account? "}
          <Link
            href="/signup"
            className="rounded font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Sign up
          </Link>
        </p>
      </div>
    </main>
  )
}
