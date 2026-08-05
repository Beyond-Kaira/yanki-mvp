'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Button from '@/components/Button'
import CustomFormError from '@/components/CustomFormError'
import CustomPasswordField from '@/components/CustomPasswordField'
import { useAuth } from '@/components/AuthProvider'
import { ApiError, previewInvitation } from '@/lib/api'
import type { InvitationPreview } from '@/lib/contracts'
import {
  MIN_PASSWORD_LENGTH,
  validateNewPassword,
  validatePasswordConfirmation,
} from '@/lib/validation'

const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner',
  admin: 'Admin',
  billing_admin: 'Billing admin',
  manager: 'Manager',
  editor: 'Editor',
  analyst: 'Analyst',
  viewer: 'Viewer',
  guest: 'Guest',
}

const FORM_ERROR_ID = 'invite-error'

const NOT_VALID = 'That invitation link is not valid.'

/**
 * What to tell somebody whose link did not open.
 *
 * The API's own words are almost always the right ones — "this expired on
 * Tuesday" is the whole reason it distinguishes its failures. The exception is
 * **422**, which is the framework rejecting a malformed path parameter before
 * any route runs, and whose message is Pydantic's: *"String should have at
 * least 16 characters"*. That is a sentence about our validator, shown to
 * somebody who only knows they clicked a link, so it is replaced with the same
 * message a genuinely unknown token gets — which is also what it is.
 */
function inviteFailureMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 422) return NOT_VALID
    if (err.status === 0) {
      return "We couldn't reach the server. Check your connection and try again."
    }
    return err.message
  }
  return 'We could not open that invitation. Check the link and try again.'
}

/**
 * The screen an invited person lands on.
 *
 * **A dead link must still explain itself.** Three of the four ways this page
 * can fail — expired, withdrawn, already used — are recoverable if the person
 * knows which one happened, and the API distinguishes them precisely because a
 * 256-bit token is not enumerable. So the failure state renders the server's
 * own sentence rather than a generic "something went wrong".
 *
 * **The email is not a field.** It comes from the invitation and is shown
 * read-only. Making it editable would turn an invitation addressed to one
 * person into a way to create an account as another, with the role the first
 * was granted.
 *
 * **Someone already signed in is not asked for a password.** They are joining a
 * second organization, not creating an account, and the API ignores the
 * password in that case — so the form does not pretend otherwise.
 */
export default function InviteClient({ token }: { token: string }) {
  const router = useRouter()
  const { acceptInvite, status, user } = useAuth()

  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{
    password?: string | null
    confirmPassword?: string | null
  }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    previewInvitation(token)
      .then((body) => {
        if (!cancelled) setPreview(body)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(inviteFailureMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const alreadySignedInAsInvitee =
    status === 'authenticated' && Boolean(preview) && user?.email === preview!.email
  const signedInAsSomeoneElse =
    status === 'authenticated' && Boolean(preview) && user?.email !== preview!.email

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    if (!alreadySignedInAsInvitee) {
      const errors = {
        password: validateNewPassword(password),
        confirmPassword: validatePasswordConfirmation(confirmPassword, password),
      }
      setFieldErrors(errors)
      if (errors.password) {
        document.getElementById('password')?.focus()
        return
      }
      if (errors.confirmPassword) {
        document.getElementById('confirm-password')?.focus()
        return
      }
    }

    setSubmitting(true)
    try {
      // A signed-in invitee is seated without creating anything, and the API
      // ignores the password — but the schema requires the field, so send
      // something that satisfies it and means nothing.
      await acceptInvite(token, alreadySignedInAsInvitee ? 'already-signed-in-placeholder' : password)
      router.push('/dashboard')
    } catch (err) {
      setSubmitting(false)
      setFormError(inviteFailureMessage(err))
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-md px-4 py-12 sm:px-8">
        <p role="status" className="text-sm text-surface-subtle">
          Opening your invitation…
        </p>
      </main>
    )
  }

  if (loadError || !preview) {
    return (
      <main className="mx-auto max-w-md px-4 py-12 sm:px-8">
        <div className="space-y-4">
          <h1 className="text-2xl font-semibold tracking-tight text-surface-foreground">
            This invitation can&apos;t be used
          </h1>
          <p role="alert" className="text-sm text-surface-subtle">
            {loadError}
          </p>
          <p className="text-sm text-surface-subtle">
            Already have an account?{' '}
            <Link
              href="/login"
              className="font-medium text-primary-strong underline underline-offset-2"
            >
              Sign in
            </Link>
            .
          </p>
        </div>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-8">
      <div className="space-y-8">
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Join {preview.organization_name}
          </h1>
          <p className="text-sm text-surface-subtle">
            You&apos;ve been invited as{' '}
            <strong className="font-medium text-surface-foreground">
              {ROLE_LABELS[preview.role] ?? preview.role}
            </strong>
            . This link expires on{' '}
            {new Date(preview.expires_at).toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
            .
          </p>
        </header>

        <div className="rounded-md border border-surface-border bg-surface-muted px-3 py-2">
          <p className="text-xs font-medium uppercase tracking-wide text-surface-subtle">
            Invitation for
          </p>
          <p className="text-sm font-medium">{preview.email}</p>
        </div>

        {signedInAsSomeoneElse ? (
          <p
            role="alert"
            className="rounded-md border border-warning-soft bg-warning-soft px-3 py-2 text-sm text-warning-strong"
          >
            You&apos;re signed in as {user?.email}, but this invitation is for{' '}
            {preview.email}. Sign out first, or open the link in a private window.
          </p>
        ) : null}

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {alreadySignedInAsInvitee ? (
            <p className="text-sm text-surface-subtle">
              You&apos;re already signed in as {preview.email}. Accepting adds this
              organization to your account — your password is unchanged.
            </p>
          ) : (
            <>
              <CustomPasswordField
                id="password"
                name="password"
                label="Choose a password"
                autoComplete="new-password"
                maxLength={128}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value)
                  setFieldErrors((current) => ({ ...current, password: null }))
                }}
                disabled={submitting}
                error={fieldErrors.password}
                hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
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
            </>
          )}

          {formError ? (
            <CustomFormError id={FORM_ERROR_ID}>{formError}</CustomFormError>
          ) : null}

          <Button
            type="submit"
            loading={submitting}
            disabled={submitting || signedInAsSomeoneElse}
            aria-describedby={formError ? FORM_ERROR_ID : undefined}
            className="w-full"
          >
            {alreadySignedInAsInvitee ? 'Join organization' : 'Create account and join'}
          </Button>
        </form>
      </div>
    </main>
  )
}
