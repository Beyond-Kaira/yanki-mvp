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
import { signup } from '@/lib/auth'
import {
  MIN_PASSWORD_LENGTH,
  validateEmail,
  validateName,
  validateNewPassword,
  validatePasswordConfirmation,
  validateTermsAccepted,
} from '@/lib/validation'

const FORM_ERROR_ID = 'signup-error'

interface FieldErrors {
  name?: string | null
  email?: string | null
  password?: string | null
  confirmPassword?: string | null
  terms?: string | null
}

export default function SignupPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const errors: FieldErrors = {
      name: validateName(name),
      email: validateEmail(email),
      password: validateNewPassword(password),
      confirmPassword: validatePasswordConfirmation(confirmPassword, password),
      terms: validateTermsAccepted(acceptedTerms),
    }
    setFieldErrors(errors)
    if (Object.values(errors).some(Boolean)) return

    // Button disables itself while `loading`, so a second click cannot fire a
    // second request; this flag is what drives it.
    setSubmitting(true)
    try {
      await signup({ name: name.trim(), email: email.trim(), password })
      // TODO(auth): whether sign-up signs the person in or sends them to log in
      // depends on the endpoint's response; returning home until that is known.
      router.push('/')
    } catch (err) {
      setSubmitting(false)
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
          <FormField
            id="name"
            name="name"
            type="text"
            label="Full name"
            autoComplete="name"
            placeholder="Ada Lovelace"
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setFieldErrors((current) => ({ ...current, name: null }))
            }}
            disabled={submitting}
            error={fieldErrors.name}
          />

          <FormField
            id="email"
            name="email"
            type="email"
            label="Work email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value)
              setFieldErrors((current) => ({ ...current, email: null }))
            }}
            disabled={submitting}
            error={fieldErrors.email}
          />

          <PasswordField
            id="password"
            name="password"
            label="Password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
              setFieldErrors((current) => ({ ...current, password: null }))
            }}
            disabled={submitting}
            error={fieldErrors.password}
            hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          />

          <PasswordField
            id="confirm-password"
            name="confirmPassword"
            label="Confirm password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => {
              setConfirmPassword(event.target.value)
              setFieldErrors((current) => ({ ...current, confirmPassword: null }))
            }}
            disabled={submitting}
            error={fieldErrors.confirmPassword}
          />

          <Checkbox
            id="terms"
            name="terms"
            checked={acceptedTerms}
            onChange={(event) => {
              setAcceptedTerms(event.target.checked)
              setFieldErrors((current) => ({ ...current, terms: null }))
            }}
            disabled={submitting}
            error={fieldErrors.terms}
            label={
              <>
                I agree to the{' '}
                {/* TODO(auth): /terms and /privacy have no pages yet. */}
                <Link
                  href="/terms"
                  className="rounded font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  terms and conditions
                </Link>
              </>
            }
          />

          {formError ? (
            <FormError id={FORM_ERROR_ID}>{formError}</FormError>
          ) : null}

          <Button type="submit" loading={submitting} className="w-full">
            Sign up
          </Button>
        </form>

        <p className="text-sm text-surface-subtle">
          {'Already have an account? '}
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
