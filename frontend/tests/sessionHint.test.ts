import { beforeEach, describe, expect, it } from 'vitest'
import {
  SESSION_HINT_COOKIE,
  clearSessionHint,
  writeSessionHint,
} from '@/lib/session-hint'

function cookieNames(): string[] {
  return document.cookie
    .split(';')
    .map((part) => part.trim().split('=')[0])
    .filter(Boolean)
}

describe('session hint', () => {
  beforeEach(() => {
    clearSessionHint()
  })

  it('is absent until something writes it', () => {
    expect(cookieNames()).not.toContain(SESSION_HINT_COOKIE)
  })

  it('is readable by the server, so it carries no secret', () => {
    writeSessionHint()

    expect(document.cookie).toContain(`${SESSION_HINT_COOKIE}=1`)
  })

  it('goes away again on clear', () => {
    writeSessionHint()
    clearSessionHint()

    expect(cookieNames()).not.toContain(SESSION_HINT_COOKIE)
  })

  it('survives a browser that refuses to hand over document.cookie', () => {
    const original = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get() {
        throw new DOMException('The operation is insecure.', 'SecurityError')
      },
      set() {
        throw new DOMException('The operation is insecure.', 'SecurityError')
      },
    })

    try {
      expect(() => writeSessionHint()).not.toThrow()
      expect(() => clearSessionHint()).not.toThrow()
    } finally {
      delete (document as unknown as Record<string, unknown>).cookie
      if (original) Object.defineProperty(Document.prototype, 'cookie', original)
    }
  })
})
