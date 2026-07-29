'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Button from '@/components/Button'
import Checkbox from '@/components/Checkbox'
import FormError from '@/components/FormError'
import FormField from '@/components/FormField'
import PasswordField from '@/components/PasswordField'
import { login } from '@/lib/auth'
import { validateEmail, validateExistingPassword } from '@/lib/validation'

const FORM_ERROR_ID = 'login-error'

interface FieldErrors {
  email?: string | null
  password?: string | null
}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const errors: FieldErrors = {
      email: validateEmail(email),
      password: validateExistingPassword(password),
    }
    setFieldErrors(errors)
    if (errors.email || errors.password) return

    // Button disables itself while `loading`, so a second click cannot fire a
    // second request; this flag is what drives it.
    setSubmitting(true)
    try {
      await login({ email: email.trim(), password, remember })
      // TODO(auth): there is no signed-in destination yet, so this returns to
      // the home page. Point it at the account view once one exists.
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
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
              setFieldErrors((current) => ({ ...current, password: null }))
            }}
            disabled={submitting}
            error={fieldErrors.password}
          />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Checkbox
              id="remember"
              name="remember"
              label="Remember me"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
              disabled={submitting}
            />
            {/* TODO(auth): /forgot-password has no page yet. */}
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
