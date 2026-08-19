// The password policy, mirrored for the browser.
//
// The authority is `backend/app/services/password_policy.py`. This file exists
// so the person choosing a password finds out while they are typing rather than
// after a round trip, and so the meter has something to measure. It decides
// nothing: every rule here is enforced again on the server, and a client that
// skipped this entirely would be rejected exactly the same way.
//
// **The rule ids are the contract between the two.** A 422 from the policy
// carries `rules: string[]` using these same identifiers, so a mismatch is
// visible rather than silent — `tests/password-policy.test.ts` pins them.
//
// **No dependency.** `zxcvbn` is the obvious library and it is ~800KB; this
// project ships three runtime dependencies (next, react, react-dom) and a
// password meter does not justify a fourth that would dwarf them. What is here
// is a deliberate small subset: the same rules, and a blocklist that is the
// head of the server's list rather than all of it. A weak password the client
// misses is caught on submit, which is the correct direction for a mirror to be
// wrong in.
//
// **Where the two deliberately differ.** The server stops at the length failure
// and reports it alone — nobody typing four characters needs to be told their
// password is also predictable. Here every rule runs every keystroke, because
// the checklist has to show the state of all of them at once.

export const MIN_PASSWORD_LENGTH = 12
export const MAX_PASSWORD_LENGTH = 128

export type PasswordRule =
  | 'too_short'
  | 'too_long'
  | 'common'
  | 'context'
  | 'repetitive'
  | 'low_variety'
  | 'sequential'

export interface PasswordFailure {
  rule: PasswordRule
  message: string
}

export interface PasswordContext {
  email?: string | null
  organizationName?: string | null
}

export interface PasswordVerdict {
  ok: boolean
  failures: PasswordFailure[]
  /** Advisory 0-4. Drives the meter and gates nothing — see the backend module
   * docstring for why a score threshold would be a composition rule in
   * disguise. */
  score: number
}

// --- Normalization ---------------------------------------------------------

/** NFKC, the same form the server hashes. */
export function normalizePassword(value: string): string {
  return value.normalize('NFKC')
}

const COMBINING = /[\u0300-\u036f]/g

// 'ş' and 'ğ' come apart under NFKD into a base letter plus a mark; dotless 'ı'
// and dotted 'İ' are letters in their own right and have to be named.
const TURKISH_FOLD: Record<string, string> = { ı: 'i', İ: 'i' }

function foldToAscii(value: string): string {
  const mapped = Array.from(value)
    .map((char) => TURKISH_FOLD[char] ?? char)
    .join('')
  return mapped.normalize('NFKD').replace(COMBINING, '')
}

// --- Canonical forms -------------------------------------------------------
//
// 'P@ssw0rd2026!' and 'password' are one password to anyone guessing, so they
// are one password here. Stripping the decoration off the ends happens BEFORE
// the leet fold: folding first turns the trailing '!' into an i and the year
// into letters, and the word underneath stops being recognisable.

const LEET_BASE: Record<string, string> = {
  '@': 'a',
  '4': 'a',
  '8': 'b',
  '(': 'c',
  '<': 'c',
  '3': 'e',
  '6': 'g',
  '9': 'g',
  '!': 'i',
  '|': 'i',
  '0': 'o',
  '5': 's',
  $: 's',
  '7': 't',
  '+': 't',
}

// '1' reads as both i and l often enough that picking one loses half the
// coverage, so both readings are generated.
const LEET_TABLES: Record<string, string>[] = [
  { ...LEET_BASE, '1': 'i' },
  { ...LEET_BASE, '1': 'l' },
]

const NON_ALNUM = /[^0-9a-z]/g
const NON_ALPHA = /[^a-z]/g
const EDGE_NOISE = /^[^a-z]+|[^a-z]+$/g

function applyLeet(value: string, table: Record<string, string>): string {
  return Array.from(value)
    .map((char) => table[char] ?? char)
    .join('')
}

function canonicalForms(password: string): Set<string> {
  const lowered = foldToAscii(normalizePassword(password).toLowerCase())
  const trimmed = lowered.replace(EDGE_NOISE, '')

  const forms = new Set<string>()
  for (const base of [lowered, trimmed]) {
    if (!base) continue

    const candidates: string[] = [base]
    for (const table of [null, ...LEET_TABLES]) {
      const folded = table === null ? base : applyLeet(base, table)
      candidates.push(folded)
      candidates.push(folded.replace(NON_ALNUM, ''))
      candidates.push(folded.replace(NON_ALPHA, ''))
    }

    // Below three characters a form collides with everything and means nothing.
    for (const candidate of candidates) {
      if (candidate.length >= 3) forms.add(candidate)
    }
  }
  return forms
}

// --- The client-side blocklist ---------------------------------------------
//
// The head of `backend/app/data/common_passwords.txt`, in the same canonical
// spelling. Kept short on purpose: this is here to give instant feedback on the
// passwords people actually type first, not to be a second copy of a list that
// has one home.

const COMMON_PASSWORDS = new Set([
  'password',
  'passwort',
  'letmein',
  'welcome',
  'admin',
  'administrator',
  'root',
  'login',
  'guest',
  'user',
  'username',
  'default',
  'changeme',
  'secret',
  'master',
  'access',
  'super',
  'system',
  'manager',
  'server',
  'backup',
  'test',
  'testing',
  'demo',
  'sample',
  'example',
  'dummy',
  'qwerty',
  'qwertz',
  'azerty',
  'qwertyuiop',
  'asdfgh',
  'asdfghjkl',
  'zxcvbn',
  'zxcvbnm',
  'qazwsx',
  'poiuytrewq',
  'lkjhgfdsa',
  'mnbvcxz',
  'qweasd',
  'asdasd',
  'qweqwe',
  '123456',
  '1234567',
  '12345678',
  '123456789',
  '1234567890',
  '123123',
  '121212',
  '111111',
  '000000',
  '654321',
  'abcdef',
  'abcdefg',
  'abcd',
  'iloveyou',
  'loveyou',
  'forever',
  'freedom',
  'whatever',
  'sunshine',
  'princess',
  'angel',
  'baby',
  'babygirl',
  'honey',
  'darling',
  'beautiful',
  'family',
  'mother',
  'father',
  'summer',
  'winter',
  'monkey',
  'dragon',
  'tiger',
  'lion',
  'eagle',
  'falcon',
  'wolf',
  'bear',
  'shark',
  'phoenix',
  'spiderman',
  'batman',
  'superman',
  'starwars',
  'pokemon',
  'mario',
  'minecraft',
  'gaming',
  'gamer',
  'player',
  'chocolate',
  'coffee',
  'cookie',
  'liverpool',
  'arsenal',
  'chelsea',
  'barcelona',
  'juventus',
  'london',
  'paris',
  'berlin',
  'newyork',
  'security',
  'secure',
  'private',
  'personal',
  'topsecret',
  'internet',
  'computer',
  'keyboard',
  'windows',
  'android',
  'iphone',
  'google',
  'facebook',
  'instagram',
  'netflix',
  'youtube',
  'money',
  'success',
  'awesome',
  // Turkish — the head of the list's Turkish section.
  'sifre',
  'sifrem',
  'parola',
  'parolam',
  'gizli',
  'kullanici',
  'yonetici',
  'merhaba',
  'selam',
  'turkiye',
  'turkey',
  'ataturk',
  'mustafakemal',
  'istanbul',
  'ankara',
  'izmir',
  'bursa',
  'antalya',
  'galatasaray',
  'fenerbahce',
  'besiktas',
  'trabzonspor',
  'cimbom',
  'aslan',
  'askim',
  'canim',
  'sevgilim',
  'bebegim',
  'bitanem',
  'birtanem',
  'hayatim',
  'melegim',
  'kalbim',
  'seniseviyorum',
  'seviyorum',
  'sevgi',
  'hayat',
  'guzel',
  'deniz',
  'yildiz',
  'gunes',
  'kartal',
  'bozkurt',
  'zeynep',
  'elif',
  'merve',
  'ayse',
  'fatma',
  'zehra',
  'melek',
  'mehmet',
  'mustafa',
  'ahmet',
  'huseyin',
  'hasan',
  'murat',
  'emre',
  'burak',
  'deneme',
])

// --- Rules -----------------------------------------------------------------

function checkLength(password: string): PasswordFailure | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return {
      rule: 'too_short',
      message: `Use at least ${MIN_PASSWORD_LENGTH} characters.`,
    }
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return {
      rule: 'too_long',
      message: `Use at most ${MAX_PASSWORD_LENGTH} characters.`,
    }
  }
  return null
}

function checkCommon(forms: Set<string>): PasswordFailure | null {
  for (const form of forms) {
    if (COMMON_PASSWORDS.has(form)) {
      return {
        rule: 'common',
        message:
          'This password is one of the ones people pick most often. Choose something else.',
      }
    }
  }
  return null
}

// Short tokens are dropped: a three-letter local part appears inside far too
// many legitimate passwords to be evidence of anything.
function contextTokens(context: PasswordContext | undefined): string[] {
  const words: string[] = ['yanki']

  if (context?.email) {
    const [local, domain] = foldToAscii(
      normalizePassword(context.email).toLowerCase(),
    ).split('@')
    words.push(...(local ?? '').split(/[^0-9a-z]+/))
    if (domain) words.push(domain.split('.')[0])
  }
  if (context?.organizationName) {
    const folded = foldToAscii(normalizePassword(context.organizationName).toLowerCase())
    words.push(...folded.split(/[^0-9a-z]+/))
  }

  return words.filter((word) => word.length >= 4)
}

function checkContext(forms: Set<string>, tokens: string[]): PasswordFailure | null {
  // Containment, not equality — unlike the blocklist. The user's own address is
  // doing the work wherever in the string it sits.
  for (const form of forms) {
    for (const token of tokens) {
      if (form.includes(token)) {
        return {
          rule: 'context',
          message:
            'Do not build your password out of your email address, your organization name, or the word Yanki.',
        }
      }
    }
  }
  return null
}

const MAX_REPEATED_UNIT = 4
const MIN_REPEATS = 3

function checkRepetition(password: string): PasswordFailure | null {
  const lowered = password.toLowerCase()
  for (let size = 1; size <= MAX_REPEATED_UNIT; size += 1) {
    if (lowered.length < size * MIN_REPEATS) break
    if (lowered.length % size !== 0) continue
    const unit = lowered.slice(0, size)
    if (unit.repeat(lowered.length / size) === lowered) {
      return {
        rule: 'repetitive',
        message: 'Avoid a password that is one short block repeated.',
      }
    }
  }
  return null
}

const MIN_DISTINCT_CHARACTERS = 4

function checkVariety(password: string): PasswordFailure | null {
  if (new Set(password.toLowerCase()).size < MIN_DISTINCT_CHARACTERS) {
    return {
      rule: 'low_variety',
      message: 'Use more than a couple of different characters.',
    }
  }
  return null
}

// The Turkish Q layout's tails are here for the same reason the blocklist has a
// Turkish section: 'qwertyuiopğü' is a keyboard walk to this product's users.
const SEQUENCES = [
  '0123456789',
  '1234567890',
  'abcdefghijklmnopqrstuvwxyz',
  'qwertyuiopğü',
  'asdfghjklşi',
  'zxcvbnmöç',
]

// Six, because '123456' and 'qwerty' are six characters long and are the two
// most common passwords ever recorded. Shorter windows match ordinary words.
const MAX_SEQUENCE_RUN = 6

const HAYSTACKS = [...SEQUENCES, ...SEQUENCES.map((row) => [...row].reverse().join(''))]

function checkSequences(password: string): PasswordFailure | null {
  const lowered = normalizePassword(password).toLowerCase()
  if (lowered.length < MAX_SEQUENCE_RUN) return null

  for (let start = 0; start <= lowered.length - MAX_SEQUENCE_RUN; start += 1) {
    const window = lowered.slice(start, start + MAX_SEQUENCE_RUN)
    if (HAYSTACKS.some((row) => row.includes(window))) {
      return {
        rule: 'sequential',
        message:
          'Avoid long runs off the keyboard or the alphabet, like 123456 or qwerty.',
      }
    }
  }
  return null
}

// --- The advisory score ----------------------------------------------------

const CLASS_PATTERNS: [RegExp, number][] = [
  [/[a-z]/, 26],
  [/[A-Z]/, 26],
  [/[0-9]/, 10],
  [/[\x20-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]/, 33],
]

const NON_ASCII = /[^\x00-\x7f]/
const NON_ASCII_POOL = 40

// Chosen so length alone reaches the top: sixteen lowercase characters score 3
// and twenty score 4, which is what makes the meter reward the thing the policy
// actually wants.
const SCORE_THRESHOLDS = [45, 60, 80]

export function passwordScore(password: string): number {
  if (!password) return 0

  let pool = CLASS_PATTERNS.reduce(
    (total, [pattern, size]) => (pattern.test(password) ? total + size : total),
    0,
  )
  if (NON_ASCII.test(password)) pool += NON_ASCII_POOL
  if (pool <= 1) return 0

  const bits = password.length * Math.log2(pool)
  return 1 + SCORE_THRESHOLDS.filter((threshold) => bits >= threshold).length
}

export const SCORE_LABELS = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong'] as const

// --- The policy ------------------------------------------------------------

export function evaluatePassword(
  value: string,
  context?: PasswordContext,
): PasswordVerdict {
  const password = normalizePassword(value)

  const lengthFailure = checkLength(password)
  const forms = canonicalForms(password)

  const failures = [
    lengthFailure,
    checkCommon(forms),
    checkContext(forms, contextTokens(context)),
    checkRepetition(password),
    checkVariety(password),
    checkSequences(password),
  ].filter((failure): failure is PasswordFailure => failure !== null)

  return {
    ok: failures.length === 0,
    failures,
    score: failures.length === 0 ? passwordScore(password) : 0,
  }
}
