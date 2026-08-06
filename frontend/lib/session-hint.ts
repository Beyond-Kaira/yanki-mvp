export const SESSION_HINT_COOKIE = 'yanki_signed_in'

const MAX_AGE_SECONDS = 60 * 60 * 24 * 30

function attributes(maxAge: number): string {
  const secure =
    typeof location !== 'undefined' && location.protocol === 'https:' ? '; Secure' : ''
  return `Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`
}

function write(value: string, maxAge: number): void {
  if (typeof document === 'undefined') return
  try {
    document.cookie = `${SESSION_HINT_COOKIE}=${value}; ${attributes(maxAge)}`
  } catch {
    return
  }
}

export function writeSessionHint(): void {
  write('1', MAX_AGE_SECONDS)
}

export function clearSessionHint(): void {
  write('', 0)
}
