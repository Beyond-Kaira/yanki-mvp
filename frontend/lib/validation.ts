// Field validators for the auth forms. Each takes the raw input value and
// returns the message to show under that field, or null when it passes.
//
// Deliberately plain functions rather than a schema library: the project ships
// with no runtime dependencies beyond React, and two forms do not justify one.
// Swapping to a schema later means replacing these call sites, nothing else.

import { evaluatePassword } from './password-policy'
import type { PasswordContext } from './password-policy'

// Mirrors the backend's conservative shape check (api/schemas.py `_EMAIL_RE`),
// which `EmailGate` already follows, so all three agree on what to reject.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export function validateEmail(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return 'Enter your email address.'
  if (!EMAIL_RE.test(trimmed)) return 'Enter a valid email address.'
  return null
}

// Sign-up only. A password policy belongs where a password is being CHOSEN.
//
// Delegates to `password-policy`, which mirrors the server's rules; this
// function's job is to turn a verdict into the one sentence that goes under the
// field on submit. The meter shows the full picture while typing — here, the
// first broken rule is the one to fix, because a wall of red under one field
// reads as an argument rather than an instruction.
//
// `context` is what lets it reject a password built from the address the user
// typed two fields up. Optional, because a caller that has no context (or has
// not collected it yet) should still get the rest of the rules.
export function validateNewPassword(
  value: string,
  context?: PasswordContext,
): string | null {
  if (!value) return 'Choose a password.'
  return evaluatePassword(value, context).failures[0]?.message ?? null
}

// Sign-in only: presence, never a length rule. Telling a returning visitor that
// the password they already have is "too short" is both wrong and a hint about
// the policy to anyone guessing.
export function validateExistingPassword(value: string): string | null {
  if (!value) return 'Enter your password.'
  return null
}

export function validatePasswordConfirmation(
  value: string,
  password: string,
): string | null {
  if (!value) return 'Re-enter your password.'
  if (value !== password) return 'Passwords do not match.'
  return null
}
