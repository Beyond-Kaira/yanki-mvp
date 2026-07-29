// Field validators for the auth forms. Each takes the raw input value and
// returns the message to show under that field, or null when it passes.
//
// Deliberately plain functions rather than a schema library: the project ships
// with no runtime dependencies beyond React, and two forms do not justify one.
// Swapping to a schema later means replacing these call sites, nothing else.

// Mirrors the backend's conservative shape check (api/schemas.py `_EMAIL_RE`),
// which `EmailGate` already follows, so all three agree on what to reject.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export const MIN_PASSWORD_LENGTH = 8

export function validateName(value: string): string | null {
  if (!value.trim()) return 'Enter your name.'
  return null
}

export function validateEmail(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return 'Enter your email address.'
  if (!EMAIL_RE.test(trimmed)) return 'Enter a valid email address.'
  return null
}

// Sign-up only. A length rule belongs where a password is being CHOSEN.
export function validateNewPassword(value: string): string | null {
  if (!value) return 'Choose a password.'
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`
  }
  return null
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

export function validateTermsAccepted(accepted: boolean): string | null {
  if (!accepted) return 'Accept the terms to continue.'
  return null
}
