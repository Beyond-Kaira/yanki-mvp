import { describe, expect, it } from 'vitest'
import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  evaluatePassword,
  normalizePassword,
  passwordScore,
} from '@/lib/password-policy'
import { validateNewPassword } from '@/lib/validation'

// The mirror of `backend/app/services/password_policy.py`.
//
// The server is the authority; this suite is what stops the two drifting apart
// without anybody noticing. Two properties matter more than the individual
// rules:
//
//   * the RULE IDS are the shared vocabulary — a 422 carries them, and a client
//     that keyed off 'common' would break silently if this file renamed it;
//   * the VERDICTS agree — a password this accepts must be one the server
//     accepts, or the form promises something the submit cannot deliver.
//
// The constants below are transcribed from the Python module. When one of these
// fails after a backend change, the fix is here, not in the assertion.

describe('password policy mirror', () => {
  it('agrees with the backend on the bounds', () => {
    expect(MIN_PASSWORD_LENGTH).toBe(12)
    expect(MAX_PASSWORD_LENGTH).toBe(128)
  })

  it('uses the rule ids the backend sends back on a 422', () => {
    const ids = [
      ...evaluatePassword('short').failures,
      ...evaluatePassword('password123456').failures,
      ...evaluatePassword('aaaaaaaaaaaa').failures,
      ...evaluatePassword('yanki-platform-1').failures,
    ].map((failure) => failure.rule)

    expect(new Set(ids)).toEqual(
      new Set([
        'too_short',
        'common',
        'sequential',
        'repetitive',
        'low_variety',
        'context',
      ]),
    )
  })
})

describe('length', () => {
  it('rejects anything under the minimum', () => {
    expect(evaluatePassword('elevenchars').failures[0].rule).toBe('too_short')
  })

  it('accepts the minimum itself', () => {
    expect('twelvechars!'.length).toBe(MIN_PASSWORD_LENGTH)
    expect(evaluatePassword('twelvechars!').ok).toBe(true)
  })

  it('rejects anything over the maximum', () => {
    expect(evaluatePassword('a'.repeat(129)).failures.map((f) => f.rule)).toContain(
      'too_long',
    )
  })
})

describe('the blocklist, and the decoration that does not save you', () => {
  it.each([
    ['password123456', 'a common word plus the most common suffix there is'],
    ['P@ssw0rd2026!', 'leet substitution, a year and a bang'],
    ['iloveyou12345', 'a phrase from the top of every corpus'],
    ['Galatasaray1905!', 'the Turkish half of the list'],
    ['m-o-n-k-e-y-2026', 'separators removed before lookup'],
  ])('rejects %s (%s)', (password) => {
    expect(evaluatePassword(password).failures.map((f) => f.rule)).toContain('common')
  })

  it("reaches the Turkish list however the user's keyboard spells it", () => {
    expect(evaluatePassword('Şifre1234!!!').failures.map((f) => f.rule)).toContain(
      'common',
    )
  })

  it('matches whole forms, not substrings', () => {
    // Substring matching would reject 'abrandnewpassword' for containing
    // 'password', and with it most of the passphrases the policy encourages.
    expect(evaluatePassword('a-brand-new-password').ok).toBe(true)
  })
})

describe('context', () => {
  it('rejects a password built from the email address', () => {
    const verdict = evaluatePassword('ahmetgizlisifre', {
      email: 'ahmet@yankiapp.com',
    })
    expect(verdict.failures.map((f) => f.rule)).toContain('context')
  })

  it('rejects a password built from the organization name', () => {
    const verdict = evaluatePassword('sirket-parolasi', {
      email: 'a@b.com',
      organizationName: 'Şirket Ltd',
    })
    expect(verdict.failures.map((f) => f.rule)).toContain('context')
  })

  it('treats the product name as context without being told', () => {
    expect(evaluatePassword('yanki-platform-1').failures.map((f) => f.rule)).toContain(
      'context',
    )
  })

  it('ignores local parts too short to be evidence', () => {
    // Banning 'ali' would tell that user their own name is forbidden.
    expect(evaluatePassword('aliminkorkulugu', { email: 'ali@example.com' }).ok).toBe(
      true,
    )
  })
})

describe('patterns', () => {
  it.each(['abcabcabcabc', 'aaaaaaaaaaaa', 'ababababababab'])(
    'rejects %s',
    (password) => {
      expect(evaluatePassword(password).failures.map((f) => f.rule)).toContain(
        'repetitive',
      )
    },
  )

  it('does not treat a doubled word as a repeated block', () => {
    expect(evaluatePassword('hunter2hunter2').ok).toBe(true)
  })

  it.each(['mysecret123456', 'alphabetabcdefg', 'secret654321x'])(
    'rejects the run in %s',
    (password) => {
      expect(evaluatePassword(password).failures.map((f) => f.rule)).toContain(
        'sequential',
      )
    },
  )
})

describe('what the policy must not do', () => {
  it('imposes no character-class requirement', () => {
    // All lowercase, no digit, no symbol — and correct. This is the test that
    // fails if somebody 'strengthens' the mirror into a composition rule.
    expect(evaluatePassword('korkuluksaat').ok).toBe(true)
    expect(evaluatePassword('bulutkahvemasa').ok).toBe(true)
  })

  it('never gates on the advisory score', () => {
    const verdict = evaluatePassword('korkuluksaat')
    expect(verdict.ok).toBe(true)
    expect(verdict.score).toBeLessThanOrEqual(2)
  })

  it('rewards length rather than variety alone', () => {
    // The meter has to point at the thing the policy actually wants.
    expect(passwordScore('bulutkahvemasadeniz')).toBeGreaterThanOrEqual(
      passwordScore('Ab1!Cd2@Ef3#'),
    )
  })

  it('scores a failing password zero', () => {
    expect(evaluatePassword('short').score).toBe(0)
  })
})

describe('normalization', () => {
  it('is the identity on ASCII', () => {
    expect(normalizePassword('correct-horse')).toBe('correct-horse')
  })

  it('folds the compatibility forms a keyboard may produce', () => {
    // Both spellings of 'şifre': precomposed U+015F, and 's' plus a
    // combining cedilla. The same password from two keyboards.
    const precomposed = 'şifre'
    const decomposed = 's\u0327ifre'
    expect(precomposed).not.toBe(decomposed)
    expect(normalizePassword(precomposed)).toBe(normalizePassword(decomposed))
  })
})

describe('validateNewPassword', () => {
  it('asks for a password before it judges one', () => {
    expect(validateNewPassword('')).toBe('Choose a password.')
  })

  it('returns the first broken rule, not all of them', () => {
    // A wall of red under one field reads as an argument rather than an
    // instruction; the meter is where the full picture lives.
    expect(validateNewPassword('short')).toBe('Use at least 12 characters.')
  })

  it('passes the context through', () => {
    expect(
      validateNewPassword('kahvemasa-2026', { email: 'kahvemasa@example.com' }),
    ).toMatch(/out of your email address/i)
  })

  it('is silent on an acceptable password', () => {
    expect(validateNewPassword('bulut-kahve-masa')).toBeNull()
  })
})
